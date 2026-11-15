# DeskFlow 命令与配置参考

所有命令在仓库根执行，解释器用 `.venv\Scripts\python.exe`。统一入口为 `python -m deskflow.cli <子命令>`。

## 命令速查

| 命令 | 作用 | 是否动文件 |
| --- | --- | --- |
| `rules` | 打印归档根、入口目录、映射条数、dry_run 状态 | 否 |
| `scan` | 只读预演，生成 `reports/预演_*.md` 与 `.json` | 否 |
| `organize --yes` | 执行归档；`dry_run=true` 时退化为预演 | 视开关 |
| `organize --yes --limit 5` | 小范围试跑 | 视开关 |
| `undo --last` | 还原最近一批真实移动 | 是（搬回） |
| `undo --batch <id>` | 还原指定批次 | 是（搬回） |
| `watch` | 前台常驻实时监控，Ctrl+C 退出 | 视开关 |
| `timeline` | 生成 `<归档根>/_时间线.html` | 写一个 HTML |
| `timeline --output <path>` | 改输出位置 | 写一个 HTML |
| `service install` | 创建登录自启计划任务 | 改系统任务 |
| `service status` | 查询任务状态 | 否 |
| `service uninstall` | 删除任务 | 改系统任务 |
| `service print` | 只打印可复制的 PowerShell 命令 | 否 |

`--config <路径>` 对所有子命令有效，用于指定另一份规则表。

## 配置优先级

1. `--config` 指定的文件（此时不加载 local.toml）。
2. 默认 `config/rules.toml`，再被 `config/local.toml` **逐项覆盖**（局部合并，不是整体替换）。

`local.toml` 已被 `.gitignore` 排除，用来放本机专属路径。排查「改了规则没生效」时，先检查它是否覆盖了同名项。

## 规则表各段

| 段 | 含义 |
| --- | --- |
| `[settings].archive_root` | 归档根。`~` 会展开为用户主目录。**不要放进 OneDrive 或同步盘** |
| `[settings].dry_run` | `true` 只记录不移动；`false` 才真实移动 |
| `[settings].stable_window_seconds` | 文件大小与 mtime 连续稳定多久才处理；写大文件较多时调到 10 |
| `[settings].settle_poll_seconds` | 监控队列轮询间隔 |
| `[settings].recursive` | 是否递归监听入口目录子目录；保持 `false` 更安全 |
| `[entry_dirs]` | `"auto"` 调 Windows 已知文件夹 API 取重定向后的真实路径；也可直接写绝对路径 |
| `[exclude].names` | 永远不动的文件名（小写匹配） |
| `[exclude].extensions` | 永远不动的扩展名（含下载中间态与安装包组件） |
| `[exclude].suffixes` | 永远不动的文件名后缀 |
| `[exclude].dirs` | 永远不动的目录名 |
| `[desktop_intake].folder` | 入口目录里的子文件夹整体搬到这里，不拆散 |
| `[timeline].filename` | 时间线页面文件名 |
| `[extensions]` | 扩展名 → 归档根下的文件夹名；未命中进 `未分类/` |

归档根自身由代码强制排除，不需要写进配置。

## 归档判定顺序

1. 位于归档根内 → 排除（防监控自激）。
2. 文件名命中 `[exclude].names` → 排除。
3. 是目录：命中 `[exclude].dirs` 则排除；否则整体搬入 `文件夹归档/`。
4. 是文件：扩展名命中 `[exclude].extensions` 或文件名命中 `[exclude].suffixes` → 排除。
5. 其余文件按 `[extensions]` 映射；未命中进 `未分类/`。
6. 目标已存在 → 自动加 `-1`、`-2` 序号，绝不覆盖。

实时监控额外两道门：只处理文件（不处理新建目录），以及 `is_locked()` 占用检测与 `StabilityTracker` 稳定窗口。

## 启动文件夹备用方案

当 `schtasks.exe` 被安全策略禁用时，在普通 PowerShell 里执行（无需管理员权限，也不会弹黑窗）：

```powershell
$repo = (Resolve-Path .).Path
$startup = [Environment]::GetFolderPath('Startup')
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut((Join-Path $startup 'DeskFlow.lnk'))
$sc.TargetPath = Join-Path $repo '.venv\Scripts\pythonw.exe'
$sc.Arguments = '"' + (Join-Path $repo 'run_watch.py') + '"'
$sc.Save()
```

卸载：删除 `$startup` 目录下的 `DeskFlow.lnk`。

若 `service install` 或 `status` 返回「无法调用 schtasks」，不要重试、不要换 shell 绕过；使用 `service print` 取得命令，由用户在普通终端执行。

## 日志格式

`logs/moves.jsonl` 每行一条 JSON：

```json
{"ts":"2026-11-15T22:10:00+08:00","action":"move","batch":"20261115-221000-ab12","src":"...","dst":"...","rule":".docx → Microsoft Word","source":"cli"}
```

`action` 取值：`plan`（只读预演记录）、`move`（真实移动）、`undo`（已撤销）。`undo` 按批次倒序还原 `move`，跳过「文件已不在归档位置」与「原位置已被占用」的条目并逐条报告。

`logs/watch.log` 是常驻监控的文本日志，记录启动、归档、跳过原因。

## 故障排查

| 现象 | 检查 |
| --- | --- |
| `rules` 里入口目录比预期少 | 目录不存在，或在 `rules.toml` 里被注释掉了 |
| 改了映射没生效 | `config/local.toml` 覆盖了同名项；扩展名是否小写带点 |
| 提示缺少 watchdog | 执行 `.venv\Scripts\pip.exe install -r requirements.txt` |
| 文件落地但没被归档 | 看 `logs/watch.log`：多半是被占用、稳定窗口未到、或扩展名在排除清单里 |
| 归档后桌面仍有图标 | 公共桌面 `C:\Users\Public\Desktop` 的快捷方式与系统图标不在处理范围 |
| 时间线显示 0 个文件 | 归档根为空或 `dry_run=true`；这是预期行为，不是故障 |
| 中文输出乱码 | 用项目虚拟环境的解释器；`cli.py` 已把 stdout/stderr 重设为 UTF-8 |
| 软件「最近文件」打不开 | 文件被移动后旧路径失效，属预期副作用，用时间线索引打开新位置 |
| `undo` 报告「原位置已被占用」 | 该条目被跳过以避免覆盖，需人工确认后再处理 |

## 隐私提示

`reports/`、`logs/`、`config/local.toml`、`_时间线.html` 里含真实文件路径，均已在 `.gitignore` 中。推送公开仓库前用 `git status --ignored` 复核一次。
