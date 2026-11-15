"""常驻实时监控：文件落地并稳定后按规则归档。

四道防线：
1. 稳定窗口：大小 + 修改时间连续稳定 N 秒才处理，避免搬走写了一半的文件。
2. 临时扩展名与占用检测：crdownload/part/tmp 一律跳过；被别的程序打开的文件不搬。
3. 归档根强制排除：防止自己搬进去的文件再次触发事件，形成无限循环。
4. 只读预演：dry_run = true 时只写日志，不碰任何文件。

实时监控只处理「文件」，不处理新建目录——解压中的文件夹可能还没写完，
整体搬走风险太高；目录归档交给 organize 手动批次完成。
"""
from __future__ import annotations

import queue
import sys
import time
from datetime import datetime
from pathlib import Path

from .cli import new_batch
from .config import Config
from .rules import exclusion_reason, target_for
from .safefile import MoveLog, StabilityTracker, plan_or_move

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # 让 rules / scan 在没有 watchdog 时也能跑
    Observer = None
    FileSystemEventHandler = object


class _EntryHandler(FileSystemEventHandler):
    def __init__(self, pending: "queue.Queue[str]", cfg: Config):
        self.pending = pending
        self.cfg = cfg

    def _submit(self, raw: str) -> None:
        path = Path(raw)
        try:
            if not path.exists() or path.is_dir():
                return
            if exclusion_reason(path, self.cfg):
                return
        except OSError:
            return
        self.pending.put(str(path))

    def on_created(self, event) -> None:
        self._submit(event.src_path)

    def on_modified(self, event) -> None:
        self._submit(event.src_path)

    def on_moved(self, event) -> None:
        self._submit(getattr(event, "dest_path", event.src_path))


def run_watch(cfg: Config) -> int:
    if Observer is None:
        print("缺少 watchdog。请先执行：.venv\\Scripts\\pip.exe install -r requirements.txt")
        return 1
    if not cfg.entry_dirs:
        print("规则表里没有有效的入口目录，监控未启动。")
        return 1

    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    log = MoveLog(cfg)
    tracker = StabilityTracker(cfg.stable_window)
    pending: "queue.Queue[str]" = queue.Queue()
    handler = _EntryHandler(pending, cfg)
    observer = Observer()
    for source, directory in cfg.entry_dirs.items():
        observer.schedule(handler, str(directory), recursive=cfg.recursive)
        print(f"监听 {source}: {directory}")

    def note(message: str) -> None:
        line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {message}"
        with open(cfg.log_dir / "watch.log", "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, flush=True)

    batch = new_batch()
    candidates: set[str] = set()
    note(f"启动，批次 {batch}，模式：{'只读预演（不移动）' if cfg.dry_run else '真实移动'}")
    observer.start()
    try:
        while True:
            while True:
                try:
                    candidates.add(pending.get_nowait())
                except queue.Empty:
                    break

            for raw in list(candidates):
                path = Path(raw)
                if not path.exists():
                    candidates.discard(raw)
                    tracker.forget(path)
                    continue
                if exclusion_reason(path, cfg):
                    candidates.discard(raw)
                    tracker.forget(path)
                    continue
                if not tracker.ready(path):
                    continue

                rule = target_for(path, cfg)[1]
                result = plan_or_move(path, cfg, rule, log, batch)
                if result.ok and not result.note:
                    note(f"已归档 {path.name} → {result.dst.parent.name}")
                elif result.note.startswith("只读预演"):
                    note(f"[预演] 将归档 {path.name} → {result.dst.parent.name}")
                else:
                    note(f"跳过 {path.name}：{result.note}")
                candidates.discard(raw)

            time.sleep(cfg.poll_interval)
    except KeyboardInterrupt:
        note("收到中断，正在退出")
    finally:
        observer.stop()
        observer.join(timeout=5)
    return 0
