"""生成离线静态时间线索引。

物理目录只按软件分；时间维度放在这个页面里，不重复搬动文件。
页面不联网、不上传任何数据，双击即可在本机打开。
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .config import Config

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".tif", ".tiff"}
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}


def _exif_time(path: Path) -> str | None:
    """读取 EXIF 拍摄时间；Pillow 未安装或读取失败时返回 None。"""
    try:
        from PIL import Image

        with Image.open(path) as image:
            exif = image.getexif()
            try:
                raw = exif.get_ifd(0x8769).get(36867)  # DateTimeOriginal
            except Exception:
                raw = None
            raw = raw or exif.get(306)  # DateTime（IFD0）
        if isinstance(raw, bytes):
            raw = raw.decode("ascii", errors="ignore")
        value = str(raw).strip()
        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S").isoformat(timespec="seconds")
    except Exception:
        return None


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def collect(archive_root: Path) -> list[dict]:
    if not archive_root.exists():
        return []
    entries: list[dict] = []
    for path in archive_root.rglob("*"):
        try:
            if not path.is_file():
                continue
            if path.name.lower() in SKIP_NAMES or path.name.startswith("_时间线"):
                continue
            if path.suffix.lower() in {".jsonl", ".log"}:
                continue
            stat = path.stat()
        except OSError:
            continue

        taken = _exif_time(path) if path.suffix.lower() in IMAGE_SUFFIXES else None
        moment = taken or datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
        try:
            relative = path.relative_to(archive_root)
            software = relative.parts[0] if len(relative.parts) > 1 else "归档根"
        except ValueError:
            software = "归档根"
        try:
            uri = path.as_uri()
        except ValueError:
            uri = ""
        entries.append(
            {
                "name": path.name,
                "path": str(path),
                "uri": uri,
                "software": software,
                "date": moment,
                "source": "EXIF 拍摄时间" if taken else "文件修改时间",
                "size": _human_size(stat.st_size),
            }
        )
    entries.sort(key=lambda item: item["date"], reverse=True)
    return entries


def render(entries: list[dict], cfg: Config) -> str:
    software_list = sorted({item["software"] for item in entries})
    payload = json.dumps(entries, ensure_ascii=False).replace("<", "\\u003c")
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    options = "".join(
        f'<option value="{html.escape(name)}">{html.escape(name)}</option>' for name in software_list
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DeskFlow 时间线</title>
<style>
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 32px 24px 64px; background: #faf9f7; color: #2c2c2a;
       font: 14px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }}
.wrap {{ max-width: 900px; margin: 0 auto; }}
h1 {{ font-size: 22px; font-weight: 500; margin: 0 0 6px; }}
.meta {{ color: #5f5e5a; font-size: 13px; margin-bottom: 22px; }}
.controls {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 24px; }}
input, select {{ font: inherit; padding: 8px 11px; border: 1px solid #d3d1c7; border-radius: 8px;
                background: #fff; color: inherit; }}
input {{ flex: 1; min-width: 220px; }}
#count {{ color: #5f5e5a; font-size: 13px; }}
.month {{ margin: 26px 0 12px; font-size: 15px; font-weight: 500; color: #3c3489; }}
.list {{ border-left: 2px solid #d3d1c7; padding-left: 18px; }}
.item {{ position: relative; padding: 10px 12px; margin-bottom: 8px; background: #fff;
         border: 1px solid #e8e6df; border-radius: 10px; }}
.item::before {{ content: ""; position: absolute; left: -23px; top: 18px; width: 8px; height: 8px;
                 border-radius: 50%; background: #7f77dd; }}
.item a {{ color: #185fa5; text-decoration: none; font-weight: 500; }}
.item a:hover {{ text-decoration: underline; }}
.tags {{ color: #5f5e5a; font-size: 12px; margin-top: 4px; }}
.tag {{ display: inline-block; padding: 1px 8px; margin-right: 6px; border-radius: 20px;
        background: #eeedfe; color: #3c3489; }}
.empty {{ color: #5f5e5a; padding: 24px 0; }}
code {{ font-family: Consolas, monospace; font-size: 12px; color: #5f5e5a; }}
</style>
</head>
<body>
<div class="wrap">
<h1>DeskFlow 时间线</h1>
<div class="meta">归档根：<code>{html.escape(str(cfg.archive_root))}</code> · 共 <span id="total">{len(entries)}</span> 个文件 · 生成于 {html.escape(generated)}</div>
<div class="controls">
  <input id="search" type="search" placeholder="搜索文件名或路径…">
  <select id="software"><option value="">全部分类</option>{options}</select>
  <span id="count"></span>
</div>
<main id="timeline"></main>
</div>
<script>
const DATA = {payload};
const timeline = document.getElementById('timeline');
const search = document.getElementById('search');
const software = document.getElementById('software');
const count = document.getElementById('count');
function esc(value) {{
  return String(value).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
}}
function render() {{
  const keyword = search.value.trim().toLowerCase();
  const chosen = software.value;
  const rows = DATA.filter(item =>
    (!chosen || item.software === chosen) &&
    (!keyword || item.name.toLowerCase().includes(keyword) || item.path.toLowerCase().includes(keyword))
  );
  count.textContent = `显示 ${{rows.length}} / ${{DATA.length}}`;
  if (!rows.length) {{ timeline.innerHTML = '<div class="empty">没有匹配的文件。归档根为空时，先执行一次 organize 或等待监控归档。</div>'; return; }}
  const groups = {{}};
  rows.forEach(item => {{ const key = item.date.slice(0, 7); (groups[key] = groups[key] || []).push(item); }});
  let markup = '';
  Object.keys(groups).sort().reverse().forEach(key => {{
    const [year, month] = key.split('-');
    markup += `<h2 class="month">${{year}} 年 ${{Number(month)}} 月 · ${{groups[key].length}} 个</h2><div class="list">`;
    groups[key].forEach(item => {{
      const link = item.uri
        ? `<a href="${{esc(item.uri)}}" title="点击在本机打开">${{esc(item.name)}}</a>`
        : esc(item.name);
      markup += `<div class="item">${{link}}<div class="tags"><span class="tag">${{esc(item.software)}}</span>${{esc(item.date.slice(0, 10))}} · ${{esc(item.size)}} · ${{esc(item.source)}}<br><code>${{esc(item.path)}}</code></div></div>`;
    }});
    markup += '</div>';
  }});
  timeline.innerHTML = markup;
}}
search.addEventListener('input', render);
software.addEventListener('change', render);
render();
</script>
</body>
</html>
"""


def build_timeline(cfg: Config, output: str | None = None) -> int:
    target = Path(output).expanduser() if output else cfg.timeline_path
    entries = collect(cfg.archive_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(entries, cfg), encoding="utf-8")
    print(f"时间线已生成：{target}")
    print(f"收录 {len(entries)} 个文件；页面完全离线，不含任何外部请求。")
    if not entries:
        print("归档根目前为空——这是正常的，首周只读预演不会移动文件。")
    return 0
