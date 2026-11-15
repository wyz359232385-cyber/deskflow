"""归档规则：算目标路径、判断排除项、枚举入口目录条目。

约定：
- 入口目录里的「子文件夹」整体搬到 文件夹归档/，不拆散（可能是程序目录或项目目录）。
- 普通文件按扩展名映射到软件文件夹，未命中进 未分类/。
- 归档根自身永远排除，否则监控会把自己刚搬进去的文件再搬一次。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .config import Config


def exclusion_reason(path: Path, cfg: Config) -> str | None:
    """返回排除原因；None 表示可以处理。"""
    try:
        if path.is_relative_to(cfg.archive_root):
            return "归档根内（防止监控自激）"
    except (ValueError, OSError):
        pass

    lowered = path.name.lower()
    if lowered in cfg.exclude_names:
        return "系统/排除文件"

    if path.is_dir():
        if lowered in cfg.exclude_dirs:
            return "排除目录"
        return None

    if path.suffix.lower() in cfg.exclude_extensions:
        return "临时扩展名"
    if any(lowered.endswith(suffix) for suffix in cfg.exclude_suffixes):
        return "临时后缀"
    return None


def target_for(path: Path, cfg: Config) -> tuple[Path, str]:
    """返回 (目标路径, 命中规则的可读说明)。只计算，不碰文件系统。"""
    if path.is_dir():
        return (
            cfg.archive_root / cfg.folder_target / path.name,
            "文件夹整体归档（不拆散）",
        )

    extension = path.suffix.lower()
    software = cfg.extensions.get(extension)
    if software:
        return cfg.archive_root / software / path.name, f"{extension} → {software}"
    return cfg.archive_root / "未分类" / path.name, "未命中规则 → 未分类"


def iter_entries(cfg: Config) -> Iterator[tuple[Path, str]]:
    """产出 (入口目录顶层条目, 来源名)。默认不递归，避免闯进程序目录。"""
    for source, directory in cfg.entry_dirs.items():
        try:
            items = sorted(directory.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            continue
        for item in items:
            yield item, source
