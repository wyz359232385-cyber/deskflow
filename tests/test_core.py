"""核心逻辑单元测试：只用临时目录，绝不触碰真实桌面或归档根。"""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from deskflow.config import Config
from deskflow.rules import exclusion_reason, target_for
from deskflow.safefile import (
    MoveLog,
    StabilityTracker,
    plan_or_move,
    undo_batch,
    unique_target,
)
from deskflow.timeline import collect, render


def make_config(root: Path, dry_run: bool) -> Config:
    desktop = root / "桌面"
    desktop.mkdir(exist_ok=True)
    raw = {
        "settings": {
            "archive_root": str(root / "归档"),
            "dry_run": dry_run,
            "stable_window_seconds": 0.05,
            "settle_poll_seconds": 0.01,
            "recursive": False,
        },
        "entry_dirs": {"desktop": str(desktop)},
        "exclude": {
            "names": ["desktop.ini"],
            "extensions": [".tmp", ".crdownload", ".dl_"],
            "suffixes": ["~"],
            "dirs": ["node_modules"],
        },
        "desktop_intake": {"folder": "文件夹归档"},
        "timeline": {"filename": "_时间线.html"},
        "extensions": {".docx": "Microsoft Word", ".lnk": "快捷方式", ".png": "图片"},
    }
    return Config(raw, Path("rules.toml"))


class RulesTests(unittest.TestCase):
    def test_target_for_file_and_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_config(Path(tmp), True)
            doc = cfg.entry_dirs["desktop"] / "报告.docx"
            doc.write_text("x", encoding="utf-8")
            self.assertEqual(
                target_for(doc, cfg)[0], cfg.archive_root / "Microsoft Word" / "报告.docx"
            )
            unknown = cfg.entry_dirs["desktop"] / "奇怪.xyz"
            unknown.write_text("x", encoding="utf-8")
            self.assertEqual(target_for(unknown, cfg)[0].parent.name, "未分类")

    def test_target_for_directory_is_kept_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_config(Path(tmp), True)
            folder = cfg.entry_dirs["desktop"] / "steam"
            folder.mkdir()
            self.assertEqual(
                target_for(folder, cfg)[0], cfg.archive_root / "文件夹归档" / "steam"
            )

    def test_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = make_config(root, True)
            desktop = cfg.entry_dirs["desktop"]
            self.assertEqual(exclusion_reason(desktop / "desktop.ini", cfg), "系统/排除文件")
            tmp_file = desktop / "half.tmp"
            tmp_file.write_text("x", encoding="utf-8")
            self.assertEqual(exclusion_reason(tmp_file, cfg), "临时扩展名")
            inside = cfg.archive_root / "Microsoft Word" / "a.docx"
            inside.parent.mkdir(parents=True)
            inside.write_text("x", encoding="utf-8")
            self.assertIn("归档根", exclusion_reason(inside, cfg))

    def test_unique_target_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.docx"
            target.write_text("first", encoding="utf-8")
            candidate = unique_target(target)
            self.assertEqual(candidate.name, "a-1.docx")
            self.assertEqual(target.read_text(encoding="utf-8"), "first")


class MoveTests(unittest.TestCase):
    def test_dry_run_never_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = make_config(root, True)
            source = cfg.entry_dirs["desktop"] / "报告.docx"
            source.write_text("x", encoding="utf-8")
            log = MoveLog(cfg, root / "moves.jsonl")
            result = plan_or_move(source, cfg, ".docx → Microsoft Word", log, "batch-1")
            self.assertTrue(result.ok)
            self.assertTrue(source.exists())
            self.assertEqual(log.records()[0]["action"], "plan")

    def test_real_move_then_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = make_config(root, False)
            source = cfg.entry_dirs["desktop"] / "报告.docx"
            source.write_text("content", encoding="utf-8")
            log = MoveLog(cfg, root / "moves.jsonl")
            result = plan_or_move(source, cfg, ".docx → Microsoft Word", log, "batch-2")
            self.assertTrue(result.ok, result.note)
            self.assertFalse(source.exists())
            self.assertTrue(result.dst.exists())
            self.assertEqual(result.dst.read_text(encoding="utf-8"), "content")

            restored, problems = undo_batch(log, "batch-2")
            self.assertEqual(restored, 1, problems)
            self.assertTrue(source.exists())
            self.assertFalse(result.dst.exists())

    def test_stability_tracker_waits_for_quiet_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "growing.bin"
            path.write_bytes(b"a")
            tracker = StabilityTracker(0.05)
            self.assertFalse(tracker.ready(path))
            time.sleep(0.07)
            self.assertTrue(tracker.ready(path))


class TimelineTests(unittest.TestCase):
    def test_collect_and_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = make_config(root, True)
            folder = cfg.archive_root / "图片"
            folder.mkdir(parents=True)
            (folder / "假期.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            (cfg.archive_root / "_时间线.html").write_text("old", encoding="utf-8")
            entries = collect(cfg.archive_root)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["software"], "图片")
            page = render(entries, cfg)
            self.assertIn("假期.png", page)
            self.assertIn("DeskFlow 时间线", page)
            self.assertNotIn("https://", page)
            self.assertNotIn("http://", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
