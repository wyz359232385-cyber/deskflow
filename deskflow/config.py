"""配置加载与 Windows 已知文件夹解析。

桌面可能被重定向到任意目录，因此入口目录优先通过 SHGetKnownFolderPath
取得真实路径，而不是硬编码 Path.home() / "Desktop"。
"""
from __future__ import annotations

import ctypes
import sys
import tomllib
from ctypes import wintypes
from pathlib import Path
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "rules.toml"
LOCAL_CONFIG = REPO_ROOT / "config" / "local.toml"

FOLDER_IDS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
}
FALLBACK = {"desktop": "Desktop", "downloads": "Downloads", "documents": "Documents"}


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.ULONG),
        ("Data2", wintypes.USHORT),
        ("Data3", wintypes.USHORT),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def known_folder(name: str) -> Path | None:
    """返回 Windows 已知文件夹的真实路径；解析失败返回 None。"""
    if sys.platform != "win32" or name not in FOLDER_IDS:
        return None
    try:
        raw = UUID(FOLDER_IDS[name]).bytes_le
        guid = _GUID()
        guid.Data1 = int.from_bytes(raw[0:4], "little")
        guid.Data2 = int.from_bytes(raw[4:6], "little")
        guid.Data3 = int.from_bytes(raw[6:8], "little")
        guid.Data4 = (ctypes.c_ubyte * 8)(*raw[8:16])

        pointer = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(pointer)
        )
        if result != 0:
            return None
        try:
            value = pointer.value
        finally:
            ctypes.windll.ole32.CoTaskMemFree(pointer)
        return Path(value) if value else None
    except Exception:
        return None


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Config:
    """规则表的一层薄封装，所有路径与开关都从这里取。"""

    def __init__(self, raw: dict, path: Path):
        self.raw = raw
        self.path = path

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        chosen = Path(path) if path else DEFAULT_CONFIG
        with open(chosen, "rb") as handle:
            raw = tomllib.load(handle)
        if chosen == DEFAULT_CONFIG and LOCAL_CONFIG.exists():
            with open(LOCAL_CONFIG, "rb") as handle:
                raw = _merge(raw, tomllib.load(handle))
        return cls(raw, chosen)

    @property
    def settings(self) -> dict:
        return self.raw.get("settings", {})

    @property
    def archive_root(self) -> Path:
        value = self.settings.get("archive_root", str(REPO_ROOT / "归档"))
        return Path(str(value)).expanduser()

    @property
    def entry_dirs(self) -> dict[str, Path]:
        resolved: dict[str, Path] = {}
        for name, value in self.raw.get("entry_dirs", {}).items():
            if isinstance(value, str) and value.lower() == "auto":
                candidate = known_folder(name) or (Path.home() / FALLBACK.get(name, name))
            else:
                candidate = Path(str(value)).expanduser()
            if candidate.exists() and candidate.is_dir():
                resolved[name] = candidate
        return resolved

    @property
    def dry_run(self) -> bool:
        return bool(self.settings.get("dry_run", True))

    @property
    def stable_window(self) -> float:
        return float(self.settings.get("stable_window_seconds", 5))

    @property
    def poll_interval(self) -> float:
        return float(self.settings.get("settle_poll_seconds", 1))

    @property
    def recursive(self) -> bool:
        return bool(self.settings.get("recursive", False))

    @property
    def extensions(self) -> dict[str, str]:
        return {str(k).lower(): str(v) for k, v in self.raw.get("extensions", {}).items()}

    @property
    def exclude_names(self) -> set[str]:
        return {str(x).lower() for x in self.raw.get("exclude", {}).get("names", [])}

    @property
    def exclude_extensions(self) -> set[str]:
        return {str(x).lower() for x in self.raw.get("exclude", {}).get("extensions", [])}

    @property
    def exclude_suffixes(self) -> tuple[str, ...]:
        return tuple(str(x).lower() for x in self.raw.get("exclude", {}).get("suffixes", []))

    @property
    def exclude_dirs(self) -> set[str]:
        return {str(x).lower() for x in self.raw.get("exclude", {}).get("dirs", [])}

    @property
    def folder_target(self) -> str:
        return str(self.raw.get("desktop_intake", {}).get("folder", "文件夹归档"))

    @property
    def timeline_filename(self) -> str:
        return str(self.raw.get("timeline", {}).get("filename", "_时间线.html"))

    @property
    def report_dir(self) -> Path:
        return REPO_ROOT / "reports"

    @property
    def log_dir(self) -> Path:
        return REPO_ROOT / "logs"

    @property
    def move_log_path(self) -> Path:
        return self.log_dir / "moves.jsonl"

    @property
    def timeline_path(self) -> Path:
        return self.archive_root / self.timeline_filename

    def summary(self) -> str:
        entries = "\n".join(f"  {name}: {path}" for name, path in self.entry_dirs.items())
        return (
            f"规则表: {self.path}\n"
            f"归档根: {self.archive_root}\n"
            f"只读预演: {'开启（不动文件）' if self.dry_run else '关闭（会真实移动）'}\n"
            f"映射规则: {len(self.extensions)} 条\n"
            f"入口目录:\n{entries or '  （无有效入口目录）'}"
        )
