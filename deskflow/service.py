"""用 Windows 计划任务实现登录自启（不需要管理员权限）。

    python -m deskflow.cli service install
    python -m deskflow.cli service status
    python -m deskflow.cli service uninstall
    python -m deskflow.cli service print    # 只打印命令，不改系统
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import Config, REPO_ROOT

TASK_NAME = "DeskFlow Auto Archive"
LAUNCHER = REPO_ROOT / "run_watch.py"


def _python_executable() -> Path:
    """优先用 pythonw.exe，避免登录时弹出黑色控制台窗口。"""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.exists() else Path(sys.executable)


def _task_command() -> str:
    return f'"{_python_executable()}" "{LAUNCHER}"'


def _run(arguments: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        # 某些受限终端/沙箱禁止调用 schtasks.exe。不重试、不绕过，直接给出手动方案。
        return 1, (
            f"无法调用 {arguments[0]}：{exc}。"
            "当前环境可能禁止了计划任务程序；请执行 service print 取得命令，"
            "在普通 PowerShell 中手动运行，或改用 README 里的启动文件夹方案。"
        )
    return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()


def _print_manual_commands() -> None:
    python = _python_executable()
    print("在普通 PowerShell（非受限终端）里执行：")
    print()
    print(f'  $tr = \'"{python}" "{LAUNCHER}"\'')
    print(f'  schtasks /Create /TN "{TASK_NAME}" /TR $tr /SC ONLOGON /RL LIMITED /F')
    print()
    print("卸载：")
    print(f'  schtasks /Delete /TN "{TASK_NAME}" /F')
    print()
    print("如果 schtasks 被禁用，改用启动文件夹快捷方式（见 README）。")


def service_command(cfg: Config, action: str) -> int:
    if sys.platform != "win32":
        print("登录自启目前只支持 Windows。")
        return 1

    if action == "print":
        _print_manual_commands()
        return 0

    if action == "install":
        if not LAUNCHER.exists():
            print(f"找不到启动器：{LAUNCHER}")
            return 1
        arguments = [
            "schtasks", "/Create", "/TN", TASK_NAME,
            "/TR", _task_command(), "/SC", "ONLOGON", "/RL", "LIMITED", "/F",
        ]
        print("将创建计划任务：")
        print("  " + " ".join(arguments))
        code, output = _run(arguments)
        print(output or ("创建成功。" if code == 0 else "创建失败。"))
        if code == 0:
            print(f"当前规则为{'只读预演（只记录不移动）' if cfg.dry_run else '真实移动'}。")
        return code

    if action == "uninstall":
        code, output = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
        print(output or ("已删除计划任务。" if code == 0 else "删除失败或任务不存在。"))
        return 0 if code == 0 else code

    code, output = _run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"])
    if code != 0:
        if output.startswith("无法调用"):
            print(output)
        else:
            print("状态：未安装（或查询失败）。")
        print("查看完整命令：python -m deskflow.cli service print")
        return 0
    for line in output.splitlines():
        if any(key in line for key in ("任务名", "TaskName", "状态", "Status", "要运行的任务", "Task To Run")):
            print(line.strip())
    return 0
