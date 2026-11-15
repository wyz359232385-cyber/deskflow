"""文件系统安全层：稳定检测、占用检测、安全移动、JSONL 操作日志、回滚。

三条硬规则：
1. 只移动，绝不删除。
2. 目标已存在时自动加序号，绝不覆盖。
3. 每次真实移动都写日志，可整批撤销。
"""
from __future__ import annotations

import ctypes
import itertools
import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import Config
from .rules import target_for


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns
    except OSError:
        return None


class StabilityTracker:
    """文件大小与修改时间连续稳定 window 秒后，才允许处理。

    防止把「才写了一半」的文件搬走；下载中、另存为中间态都会被挡住。
    """

    def __init__(self, window: float):
        self.window = max(0.0, window)
        self._seen: dict[str, tuple[float, tuple[int, int]]] = {}

    def ready(self, path: Path) -> bool:
        current = signature(path)
        if current is None:
            self._seen.pop(str(path), None)
            return False
        key = str(path)
        now = time.monotonic()
        previous = self._seen.get(key)
        if previous is None:
            self._seen[key] = (now, current)
            return False
        first_at, first_signature = previous
        if current != first_signature:
            self._seen[key] = (now, current)
            return False
        if now - first_at >= self.window:
            self._seen.pop(key, None)
            return True
        return False

    def forget(self, path: Path) -> None:
        self._seen.pop(str(path), None)


def is_locked(path: Path) -> bool:
    """Windows 上以「不共享」方式试开文件；打不开即视为被占用。

    拿不准时一律返回 True（宁可不搬，也不能破坏正在编辑的文档）。
    """
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = ctypes.c_void_p
        handle = kernel32.CreateFileW(
            str(path),
            0x80000000,  # GENERIC_READ
            0,           # dwShareMode = 0：不允许其他句柄共享
            None,
            3,           # OPEN_EXISTING
            0x80,        # FILE_ATTRIBUTE_NORMAL
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        if handle is None or handle == invalid:
            return True
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    except Exception:
        return True


def unique_target(target: Path) -> Path:
    """目标已存在时追加 -1、-2 …，绝不覆盖既有文件。"""
    if not target.exists():
        return target
    for index in itertools.count(1):
        candidate = target.parent / f"{target.stem}-{index}{target.suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("unreachable")


class MoveLog:
    def __init__(self, cfg: Config, path: Path | None = None):
        # 允许测试指定临时日志路径，避免写进项目 logs/
        self.path = path or cfg.move_log_path

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        output = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                output.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return output

    def batches(self) -> list[str]:
        batches: list[str] = []
        for record in self.records():
            if record.get("action") == "move":
                batch = str(record.get("batch", ""))
                if batch and batch not in batches:
                    batches.append(batch)
        return batches


@dataclass
class MoveResult:
    ok: bool
    src: Path
    dst: Path
    rule: str
    note: str = ""


def plan_or_move(
    src: Path,
    cfg: Config,
    rule: str,
    log: MoveLog,
    batch: str,
    dry_run: bool | None = None,
) -> MoveResult:
    """只读预演时仅记录计划；否则执行安全移动。"""
    if dry_run is None:
        dry_run = cfg.dry_run
    destination = unique_target(target_for(src, cfg)[0])
    record = {
        "ts": _now(),
        "batch": batch,
        "src": str(src),
        "dst": str(destination),
        "rule": rule,
        "source": "cli",
    }

    if dry_run:
        log.append({**record, "action": "plan"})
        return MoveResult(True, src, destination, rule, "只读预演：未移动")

    try:
        if is_locked(src):
            # 被占用是预期情况，记为「跳过」而不是「失败」，不触发整批停止
            return MoveResult(True, src, destination, rule, "文件被占用，已跳过")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(destination))
        log.append({**record, "action": "move"})
        return MoveResult(True, src, destination, rule, "")
    except Exception as exc:  # 失败即由调用方停止本批
        return MoveResult(False, src, destination, rule, f"{type(exc).__name__}: {exc}")


def undo_batch(log: MoveLog, batch: str) -> tuple[int, list[str]]:
    """把某一批移动整体还原；遇到原位置已被占用则跳过并报告，绝不覆盖。"""
    records = log.records()
    already_undone = {
        str(record.get("dst"))
        for record in records
        if record.get("action") == "undo"
    }
    moves = [
        record
        for record in records
        if record.get("action") == "move" and str(record.get("batch", "")) == batch
    ]
    restored = 0
    problems: list[str] = []
    for record in reversed(moves):
        src = Path(record["src"])
        dst = Path(record["dst"])
        if str(dst) in already_undone:
            continue
        if not dst.exists():
            problems.append(f"文件已不在归档位置，跳过：{dst}")
            continue
        if src.exists():
            problems.append(f"原位置已被占用，跳过以免覆盖：{src}")
            continue
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            log.append(
                {
                    "ts": _now(),
                    "action": "undo",
                    "batch": batch,
                    "src": record["src"],
                    "dst": record["dst"],
                }
            )
            restored += 1
        except Exception as exc:
            problems.append(f"还原失败 {dst}: {type(exc).__name__}: {exc}")
    return restored, problems
