"""DeskFlow 统一命令行入口。

    python -m deskflow.cli rules               查看当前生效配置
    python -m deskflow.cli scan                只读预演，生成报告（不动文件）
    python -m deskflow.cli organize --yes      真正执行搬运（受 dry_run 开关约束）
    python -m deskflow.cli undo --last         撤销最近一批移动
    python -m deskflow.cli watch               常驻实时监控
    python -m deskflow.cli timeline            生成时间线 HTML 索引
    python -m deskflow.cli service install    安装登录自启
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import Config
from .rules import exclusion_reason, iter_entries, target_for
from .safefile import MoveLog, plan_or_move, undo_batch

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

BATCH_SIZE = 10  # 每批最多搬 10 个，出错立即停


def new_batch() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def build_plan(cfg: Config) -> tuple[list[dict], list[dict]]:
    planned: list[dict] = []
    skipped: list[dict] = []
    for path, source in iter_entries(cfg):
        reason = exclusion_reason(path, cfg)
        if reason:
            skipped.append({"path": str(path), "reason": reason})
            continue
        destination, rule = target_for(path, cfg)
        planned.append(
            {
                "src": str(path),
                "dst": str(destination),
                "rule": rule,
                "source": source,
                "is_dir": path.is_dir(),
            }
        )
    return planned, skipped


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_report(cfg: Config, planned: list[dict], skipped: list[dict]) -> str:
    by_software = Counter(Path(item["dst"]).parent.name for item in planned)
    lines = [
        "# DeskFlow 归档预演报告",
        "",
        f"- 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 模式：**{'只读预演，未移动任何文件' if cfg.dry_run else '真实移动已开启'}**",
        f"- 归档根：`{cfg.archive_root}`",
        f"- 待处理：{len(planned)} 项；跳过：{len(skipped)} 项",
        "",
        "## 按软件分组",
        "",
    ]
    if by_software:
        lines += ["| 目标文件夹 | 数量 |", "| --- | ---: |"]
        lines += [f"| {_cell(name)} | {count} |" for name, count in by_software.most_common()]
    else:
        lines.append("（入口目录当前没有可归档的条目）")
    lines += ["", "## 逐项计划", "", "| 原位置 | 目标位置 | 依据 |", "| --- | --- | --- |"]
    lines += [
        f"| `{_cell(item['src'])}` | `{_cell(item['dst'])}` | {_cell(item['rule'])} |"
        for item in planned
    ]
    lines += ["", "## 跳过项", ""]
    if skipped:
        lines += ["| 路径 | 原因 |", "| --- | --- |"]
        lines += [f"| `{_cell(item['path'])}` | {_cell(item['reason'])} |" for item in skipped]
    else:
        lines.append("（无）")
    lines += [
        "",
        "---",
        "",
        "确认无误后：把 `config/rules.toml` 的 `dry_run` 改为 `false`，",
        "再执行 `python -m deskflow.cli organize --yes`。",
        "后悔了执行 `python -m deskflow.cli undo --last`。",
        "",
    ]
    return "\n".join(lines)


def cmd_scan(cfg: Config, args: argparse.Namespace) -> int:
    planned, skipped = build_plan(cfg)
    cfg.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown = cfg.report_dir / f"预演_{stamp}.md"
    json_path = cfg.report_dir / f"预演_{stamp}.json"
    markdown.write_text(render_report(cfg, planned, skipped), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "dry_run": cfg.dry_run,
                "archive_root": str(cfg.archive_root),
                "planned": planned,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"待处理 {len(planned)} 项，跳过 {len(skipped)} 项")
    print(f"Markdown 报告：{markdown}")
    print(f"JSON 明细：{json_path}")
    if planned:
        counts = Counter(Path(item["dst"]).parent.name for item in planned)
        print("目标分布：" + "、".join(f"{name} {n}" for name, n in counts.most_common()))
    print("本命令只读，没有移动任何文件。")
    return 0


def _chunks(items: list[dict], size: int) -> Iterable[list[dict]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def cmd_organize(cfg: Config, args: argparse.Namespace) -> int:
    planned, skipped = build_plan(cfg)
    if args.limit:
        planned = planned[: args.limit]

    if cfg.dry_run:
        print("当前是只读预演模式（dry_run = true），不会移动任何文件。")
        log = MoveLog(cfg)
        batch = new_batch()
        for item in planned:
            plan_or_move(Path(item["src"]), cfg, item["rule"], log, batch, dry_run=True)
        return cmd_scan(cfg, args)

    if not args.yes:
        print("即将真实移动文件。确认请加 --yes；想先看报告请执行 scan。")
        return 1

    log = MoveLog(cfg)
    batch = new_batch()
    moved = 0
    problems: list[str] = []
    for chunk in _chunks(planned, BATCH_SIZE):
        for item in chunk:
            result = plan_or_move(Path(item["src"]), cfg, item["rule"], log, batch)
            if result.ok and not result.note:
                moved += 1
            elif not result.ok:
                problems.append(f"{item['src']}: {result.note}")
                print(f"本批出错，立即停止：{result.note}")
                break
        else:
            continue
        break
    print(f"批次 {batch}：成功移动 {moved} 项，跳过 {len(skipped)} 项，问题 {len(problems)} 条")
    print(f"后悔了执行：python -m deskflow.cli undo --batch {batch}")
    return 1 if problems else 0


def cmd_undo(cfg: Config, args: argparse.Namespace) -> int:
    log = MoveLog(cfg)
    batches = log.batches()
    if args.last:
        if not batches:
            print("没有可撤销的批次（日志里没有真实移动记录）。")
            return 0
        batch = batches[-1]
    else:
        batch = args.batch
    restored, problems = undo_batch(log, batch)
    print(f"批次 {batch}：还原 {restored} 项")
    for problem in problems:
        print("  ! " + problem)
    return 1 if problems else 0


def cmd_rules(cfg: Config, args: argparse.Namespace) -> int:
    print(cfg.summary())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deskflow", description="按软件自动归档桌面/下载/文档的本地工具"
    )
    parser.add_argument("--config", help="指定规则表路径，默认 config/rules.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("rules", help="查看当前生效配置")
    subparsers.add_parser("scan", help="只读预演并生成报告")

    organize = subparsers.add_parser("organize", help="执行归档（受 dry_run 约束）")
    organize.add_argument("--yes", action="store_true", help="确认真实移动")
    organize.add_argument("--limit", type=int, help="最多处理多少项")

    undo = subparsers.add_parser("undo", help="撤销某一批移动")
    group = undo.add_mutually_exclusive_group(required=True)
    group.add_argument("--last", action="store_true", help="撤销最近一批")
    group.add_argument("--batch", help="指定批次号")

    subparsers.add_parser("watch", help="常驻实时监控")
    timeline = subparsers.add_parser("timeline", help="生成时间线 HTML 索引")
    timeline.add_argument("--output", help="输出路径，默认归档根/_时间线.html")

    service = subparsers.add_parser("service", help="管理登录自启")
    service.add_argument("action", choices=["install", "uninstall", "status", "print"])

    args = parser.parse_args(argv)
    cfg = Config.load(args.config)

    handlers = {
        "rules": cmd_rules,
        "scan": cmd_scan,
        "organize": cmd_organize,
        "undo": cmd_undo,
    }
    if args.command in handlers:
        return handlers[args.command](cfg, args)
    if args.command == "watch":
        from .watch import run_watch

        return run_watch(cfg)
    if args.command == "timeline":
        from .timeline import build_timeline

        return build_timeline(cfg, args.output)
    if args.command == "service":
        from .service import service_command

        return service_command(cfg, args.action)
    parser.error("未知命令")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
