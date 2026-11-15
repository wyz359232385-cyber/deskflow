# DeskFlow

把 Windows 桌面上的文件与快捷方式收进一个归档文件夹，按「扩展名 → 软件」自动分目录；新文件落地即归类；再生成一份离线时间线页面，按日期浏览全部已归档文件。

纯本地、无网络请求、无云服务。当前版本 `0.1.0`，**默认开启只读预演**：先跑一周只出报告、不动任何文件，确认规则无误后再打开真实移动。

## 它能做什么 / 不能做什么

**能做**

- 清空桌面上的用户图标（含 `.lnk` 快捷方式、`steam/` 这类文件夹、压缩包、文档），桌面视觉上变干净。
- 按可编辑的规则表把文件归入 `Microsoft Word/`、`图片/`、`压缩工具/` 等软件目录；匹配不上的进 `未分类/`。
- 用 `watchdog` 常驻监听入口目录，文件写完并稳定后自动归类。
- 生成离线 HTML 时间线：按年月分组、按软件筛选、搜索、点击打开原文件；图片优先用 EXIF 拍摄时间。
- 每次真实移动都记 JSONL 日志，支持整批一键回滚。
- 以 WorkBuddy Skill 的形式在对话里调用（见文末）。

**做不到（说在前面）**

- 追溯历史文件"当年是哪个程序生成的"。分类依据是扩展名推断，不是进程来源。
- 拦截软件"另存为"到任意路径的保存动作。只有在你圈定的入口目录内才能捕获；全盘拦截需要文件系统过滤驱动，风险和代价都不值得。
- 移动 `C:\Users\Public\Desktop` 下的公共快捷方式，或隐藏「此电脑」「回收站」这类系统图标（前者属系统级、影响所有账户；后者要去 Windows 个性化设置里关）。
- 在不改动文件物理位置的前提下，同时实现"按软件分"和"按年月分"。本项目选择**物理目录按软件分、时间维度做索引页**。

## 快速开始

需要 Windows + Python 3.11+（用到内置 `tomllib`）。

```powershell
cd <仓库根>
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
```

**第 1 步：看当前配置**（确认归档根、入口目录、预演开关）

```powershell
.venv\Scripts\python.exe -m deskflow.cli rules
```

**第 2 步：只读预演**（不移动任何文件）

```powershell
.venv\Scripts\python.exe -m deskflow.cli scan
```

报告写在 `reports/预演_<时间>.md`，逐项列出「原位置 → 目标位置 → 依据」，另有同名 `.json` 便于程序处理。**先读一遍报告**。

**第 3 步：确认无误后打开真实移动**

把 `config/rules.toml` 里的 `dry_run` 改成 `false`，然后：

```powershell
.venv\Scripts\python.exe -m deskflow.cli organize --yes
```

每批最多 10 项，出错立即停。想先小范围试跑加 `--limit 5`。执行后会打印批次号。

**第 4 步：后悔了就回滚**

```powershell
.venv\Scripts\python.exe -m deskflow.cli undo --last
```

## 目录结构

```
deskflow/
├── config/
│   ├── rules.toml        # 入库规则表：扩展名映射、入口目录、排除清单、开关
│   └── local.toml        # 本机覆盖（已 gitignore），放本机归档根路径
├── deskflow/             # Python 包
│   ├── config.py         # 规则表加载 + Windows 已知文件夹解析
│   ├── rules.py          # 目标路径计算、排除判断
│   ├── safefile.py       # 稳定检测、占用检测、安全移动、日志、回滚
│   ├── cli.py            # 统一命令入口
│   ├── watch.py          # watchdog 常驻监控
│   ├── service.py        # 登录自启（schtasks）
│   └── timeline.py       # 离线时间线 HTML 生成
├── run_watch.py          # 供 pythonw.exe 调用的启动器
├── skill/deskflow-file-archiver/   # WorkBuddy Skill
├── reports/              # 运行时报告（已 gitignore）
└── logs/                 # 移动日志与监控日志（已 gitignore）
```

归档后的样子：

```
文件归档/
├── 快捷方式/            ← 桌面上的 .lnk
├── 文件夹归档/          ← 桌面上的子文件夹整体搬入，不拆散
├── 压缩工具/            ← .rar .zip .7z
├── Microsoft Word/      ← .doc .docx
├── 图片/ 视频/ 音频/
├── 未分类/
└── _时间线.html         ← 离线索引
```

## 规则表怎么改

`config/rules.toml` 是唯一要改的文件，改完保存即生效，不用动代码。

```toml
[extensions]
".docx" = "Microsoft Word"
".psd"  = "Adobe Photoshop"
```

键是小写带点扩展名，值是归档根下的文件夹名。未命中进 `未分类/`。当前内置 116 条映射。

`config/local.toml` 会**覆盖** `rules.toml` 的同名项，用来放本机专属路径，不入库。若出现「改了规则没生效」，先检查这个文件。

### 关于入口目录

默认只监听**桌面**：

```toml
[entry_dirs]
desktop = "auto"
# downloads = "auto"
# documents = "auto"
```

`"auto"` 会调用 Windows 已知文件夹 API 取真实路径，桌面被重定向过也能找对。

2026-11-15 首次实测发现：某台机器的下载目录有 437 项，其中 324 项是驱动安装包解压出的 `.dl_` / `.ch_` / `.dll` 碎片。若把下载目录纳入实时监控，这些碎片会被逐个搬走、把安装包拆散。因此：

- 默认关闭下载与文档入口，确认过内容后再取消注释；
- `.dl_`、`.ch_`、`.dll`、`.inf`、`.cat` 等安装组件，以及 `.tmp`、`.crdownload`、`.part` 等中间态，已列入 `[exclude].extensions` 永久排除。

## 安全设计

| 措施 | 说明 |
| --- | --- |
| 只读预演 | `dry_run = true` 时 `scan` / `organize` / `watch` 都只写报告与日志，不碰文件 |
| 只移不删 | 全程没有删除操作；目标已存在自动加 `-1`、`-2` 序号 |
| 稳定窗口 | 文件大小与修改时间连续稳定 5 秒才处理，避免搬走写了一半的文件 |
| 占用检测 | 以「不共享」方式试开文件，被 Word/PS 占用就跳过，不硬搬 |
| 防自激 | 归档根强制排除，监控不会反复搬自己刚放好的文件 |
| 不拆目录 | 入口目录里的子文件夹整体归档；实时监控只处理文件，避免搬走解压中的目录 |
| 小批量 | 每批 10 项，任一失败立即停止 |
| 可回滚 | `logs/moves.jsonl` 记录每次移动，`undo --last` 整批还原 |

## 实时监控与登录自启

前台试跑（Ctrl+C 退出）：

```powershell
.venv\Scripts\python.exe -m deskflow.cli watch
```

登录自启：

```powershell
.venv\Scripts\python.exe -m deskflow.cli service install
.venv\Scripts\python.exe -m deskflow.cli service status
.venv\Scripts\python.exe -m deskflow.cli service print   # 只打印命令，不改系统
.venv\Scripts\python.exe -m deskflow.cli service uninstall
```

`service install` 用 `schtasks /SC ONLOGON` 创建当前用户任务，优先调用 `pythonw.exe` 避免登录时弹黑窗。若终端环境禁止调用 `schtasks.exe`，`service print` 会输出可直接复制的 PowerShell 命令；也可以改用启动文件夹快捷方式（完整命令见 `skill/deskflow-file-archiver/references/usage.md`）。

## 时间线索引

```powershell
.venv\Scripts\python.exe -m deskflow.cli timeline
```

生成 `<归档根>/_时间线.html`，双击即可打开。页面按年月倒序、支持分类筛选与搜索、点击文件名在本机打开；图片优先读 EXIF 拍摄时间（需要可选的 Pillow），否则回退文件修改时间。页面不含任何外部请求，也不会把路径上传到任何地方。`--output reports/时间线.html` 可改输出位置。

## 用 WorkBuddy Skill 调用

`skill/deskflow-file-archiver/` 是符合 Skill 规范的包，含 `SKILL.md` 与 `references/usage.md`。它把上面这些命令编排成工作流，并写死了安全底线（未确认不得关闭预演、不得删除文件、不得替用户登录 GitHub 等）。把该目录放进 WorkBuddy 的 skills 目录即可在对话里直接使用。

## 推送到 GitHub

```powershell
git init
git add .
git commit -m "feat: initial DeskFlow implementation"
gh auth login                                  # 需要本人浏览器授权
gh repo create deskflow --public --source=. --push
```

`gh auth login` 与 Git 提交身份属于本人授权和身份信息，不由工具代劳。推送前确认 `.gitignore` 已排除 `.venv/`、`reports/`、`logs/`、`config/local.toml`——这些目录里可能含真实文件路径，不要入库。

## 完全卸载

```powershell
.venv\Scripts\python.exe -m deskflow.cli service uninstall
```

然后删除项目目录即可。已经归档的文件不会自动搬回桌面；需要还原请先用 `undo --last`（或 `undo --batch <id>`）再删项目。

## 已知限制

- 只支持 Windows；`schtasks` 与 `CreateFileW` 占用检测在非 Windows 上不适用。
- 快捷方式移走后仍能双击（`.lnk` 存的是目标路径），但要进归档文件夹找，启动习惯会变。
- 公共桌面的快捷方式与系统图标不会消失，桌面能清到几乎全空、但不是 100% 空。
- 实时监控默认只看入口目录顶层；新建子文件夹里的文件不会被自动归类，需手动跑一次 `organize`。
- 移动文件会让部分软件的「最近使用的文件」记录失效，属预期副作用。

## License

MIT，见 [LICENSE](LICENSE)。
