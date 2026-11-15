"""登录自启用的启动器：不依赖当前工作目录，供 pythonw.exe 直接调用。

    pythonw.exe <仓库根>/run_watch.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deskflow.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["watch"]))
