---
name: deskflow-file-archiver
description: This skill should be used when the user wants to preview, run, configure, inspect, or roll back automatic Windows file archiving by software category, manage the login-start real-time monitor, generate a local timeline index, or publish the DeskFlow project to GitHub. Chinese triggers include 整理桌面、桌面图标收进文件夹、文件自动归类、按软件分文件夹、时间线查看文件、回滚归档、开机自启归档。
---

# DeskFlow 文件归档

## 用途

把 Windows 桌面（以及用户显式开启的其他入口目录）里的文件，按「扩展名 → 软件」映射表收进统一的归档根；用常驻脚本实现新文件落地即归类；另生成一份离线时间线索引页，按日期浏览全部已归档文件。物理目录**只按软件分**，时间维度放在索引页里，不重复搬动文件。

## 何时使用

- 用户要求整理桌面、清空桌面图标、按软件/按类型分文件夹。
- 用户要求「以后新产生的文件也自动分好类」。
- 用户要求查看归档结果、按时间线浏览、核对某次归档做了什么。
- 用户要求撤销归档、修改分类规则、开关登录自启、把项目推到 GitHub。

## 仓库位置与执行方式

定位包含 `config/rules.toml` 与 `deskflow/` 包的目录作为 `<repo>`。所有命令都在 `<repo>` 下执行，使用项目虚拟环境的解释器 `<repo>/.venv/Scripts/python.exe`；若虚拟环境不存在，先执行 `python -m venv .venv` 再 `.venv/Scripts/pip.exe install -r requirements.txt`。

统一入口：`python -m deskflow.cli <子命令>`。
`--config <路径>` 可指定另一份规则表；`config/local.toml` 若存在会覆盖默认规则表，优先检查它，避免「改了规则却没生效」的误判。

## 核心工作流

### 1. 先确认当前状态

执行 `python -m deskflow.cli rules`，向用户复述归档根、入口目录、映射规则条数，以及 **dry_run 是开还是关**。不跳过这一步。

### 2. 永远先做只读预演

执行 `python -m deskflow.cli scan`。该命令只读，生成 `reports/预演_*.md` 与同名 `.json`。读取报告，向用户复述待处理数量、按软件分组分布、跳过项。发现异常分布（例如某个目录出现几百个安装包碎片）时，先收敛入口目录或补排除规则，再继续。

### 3. 取得明确确认才允许真实移动

把 `config/rules.toml` 的 `dry_run` 从 `true` 改为 `false` 之前，必须向用户展示预演报告要点并取得明确同意。禁止在未经确认时关闭预演，禁止替用户「顺手」打开真实移动。

真实移动：`python -m deskflow.cli organize --yes`。每批最多 10 项，出错立即停止；`--limit N` 可先小范围试跑。

### 4. 提供随时可撤销的路径

执行后立即告知批次号。`python -m deskflow.cli undo --last` 撤销最近一批，`undo --batch <id>` 撤销指定批次。遇到原位置已被占用的条目会跳过并报告，绝不覆盖。

### 5. 实时监控与登录自启

前台试跑：`python -m deskflow.cli watch`。
登录自启：`python -m deskflow.cli service install`；查询 `status`；卸载 `uninstall`；只打印命令不改系统用 `print`。

当 `schtasks.exe` 被安全策略禁用时，不要重试、不要换 shell 绕过。改用 `service print` 输出命令让用户在普通 PowerShell 执行，或按 `references/usage.md` 的启动文件夹快捷方式方案操作。

### 6. 时间线索引

`python -m deskflow.cli timeline` 生成到归档根；`--output <路径>` 可改到 `reports/` 便于预览。页面完全离线，图片优先取 EXIF 拍摄时间，缺失则回退修改时间。归档根为空时生成空页面属正常结果。

## 安全底线（不可跳过）

- 未经用户明确确认，不得关闭 `dry_run`；未跑 `scan` 不得执行 `organize`。
- 只移动，绝不删除；目标已存在时自动加序号，绝不覆盖。
- 不得递归清空桌面、下载、文档或用户主目录；入口目录默认只看顶层。
- 不得把归档根放进 OneDrive 或其他同步盘目录。
- 不得把 `C:\Users\Public\Desktop` 的公共快捷方式、系统图标、被占用的文件、Git 仓库纳入搬运。
- 不得替用户执行 `gh auth login`、不得设置全局 `git config user.*`；这些属于用户本人授权与身份信息。

## 常见调整

- 改分类：`config/rules.toml` 的 `[extensions]` 表，键为小写带点扩展名，值为归档根下的文件夹名。
- 扩大范围：取消 `[entry_dirs]` 里 `downloads` / `documents` 的注释。执行前务必重新 `scan`，下载目录里常有安装包解压碎片。
- 排除碎片：往 `[exclude].extensions` 加扩展名，例如 `.dl_`、`.ch_`、`.dll`、`.inf`。
- 调整稳定窗口：`[settings].stable_window_seconds`，写大文件较多时调大到 10。
- 完整命令、目录结构、故障排查见 `references/usage.md`。
