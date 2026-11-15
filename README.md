# 桌面归位（DeskFlow）

桌面乱了，就让它自己收好。

这个工具把桌面上的图标（文件、文件夹、快捷方式）收进一个文件夹，按软件分好类；以后再往桌面放东西，也会被自动放进对应软件的文件夹。还能打开一个网页，按时间往回翻，看看以前的文件都放哪儿了。

它只在你自己电脑上跑，不联网、不上传。**最要紧的是不会一上来就乱动你的东西**：第一次只给你看一份清单——「我打算把什么搬到哪」，你点头之后才真的搬，而且随时能整批搬回去。

只支持 Windows。

## 最省事的做法：把下面这段话复制给 AI

不用装环境、不用记命令。整段复制，粘贴给 WorkBuddy / Claude / 任意能操作你电脑的 AI 助手，它会替你做完：

```
帮我用「桌面归位」这个项目把电脑桌面整理好（只适用于 Windows）：
https://github.com/wyz359232385-cyber/deskflow

1. 把仓库克隆到当前工作目录，建 .venv 并安装 requirements.txt。
2. 先跑 rules 和 scan，把报告念给我听：一共多少项、分别会搬到哪、有哪些拿不准的。
3. 这一步不要动我的任何文件。等我明确说「确认」，再把 config/rules.toml 里的 dry_run 改成 false，执行 organize --yes，并告诉我批次号。
4. 之后生成时间线页面，把开机自动整理的命令给我，别替我改系统设置。

规矩：只搬不删；重名别覆盖；下载目录里成堆的 .dl_、.dll 之类安装包碎片一律别碰；拿不准就先问我。
```

AI 会先把清单给你看，你确认了它才动手。想还原，就说一句「帮我把上一批搬回去」。

不想用 AI 的话，看下面的「手动做法」，四条命令也能跑起来。

## 它能做什么 / 做不到什么

**能做**

- 把桌面上的图标收走（快捷方式、文件夹、压缩包、文档都算），桌面变干净。
- 按文件类型分到 `Microsoft Word/`、`图片/`、`压缩工具/` 这些文件夹里；认不出来的先放 `未分类/`。分类规则是一张表，自己能改。
- 以后新放到桌面的文件，等它写完了会自动被收进对应的文件夹。
- 生成一个网页，按年月翻看所有收好的文件，能搜、能筛选、点一下就打开原文件；照片按拍摄时间排。
- 每次搬东西都记一笔账，说一句「搬回去」就能整批还原。
- 附带一个 AI 技能包，可以在对话里直接喊它干活（见文末）。

**做不到（说在前面）**

- 分不出某个文件当年是用哪个软件做的，只能看文件类型来分。
- 只盯着桌面（和你自己加的目录）。软件把文件存到别的盘，它管不着。
- 系统自带的「此电脑」「回收站」图标不会消失，别的账户共用的快捷方式也不动。
- 一个文件不能同时躺在「Word」和「2026 年 11 月」两个文件夹里。所以文件夹按软件分，时间用一个网页来看。

## 手动做法（不用 AI 的话）

需要 Windows 和 Python 3.11 以上，四条命令就能跑起来。

```powershell
cd <仓库根>
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
```

**第 1 步：看看它打算把东西放哪**

```powershell
.venv\Scripts\python.exe -m deskflow.cli rules
```

**第 2 步：先看清单，一个文件都不会动**

```powershell
.venv\Scripts\python.exe -m deskflow.cli scan
```

清单在 `reports/` 里，一条条写着「什么文件 → 搬到哪 → 凭什么这么分」。**先读一遍，再往下走。**

**第 3 步：你点头了，才真的搬**

把 `config/rules.toml` 里的 `dry_run` 改成 `false`（意思是「别只看了，动手吧」），然后：

```powershell
.venv\Scripts\python.exe -m deskflow.cli organize --yes
```

一次最多搬 10 个，一出错就停。想先试 5 个就加 `--limit 5`。搬完会给你一个批次号，留着用来还原。

**第 4 步：后悔了，一句话搬回去**

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

## 想改分类规则

打开 `config/rules.toml`，照着样子改，存一下就生效，不用碰代码：

```toml
[extensions]
".docx" = "Microsoft Word"
".psd"  = "Adobe Photoshop"
```

左边是文件后缀，右边是它该进哪个文件夹。认不出来的进 `未分类/`。现在内置了 116 条，够用了。

`config/local.toml` 是放你自己电脑路径的，会盖掉上面文件的同名设置，而且不会传到网上。要是「改了规则没反应」，先看看它。

### 为什么默认只盯桌面

实测碰到过：下载文件夹里躺着 400 多个文件，其中 300 多个是某个驱动安装包解压出来的碎片。要是也自动搬，安装包就废了。所以：

- 默认只盯桌面，下载和文档先别开；想开就到 `config/rules.toml` 里把 `downloads`、`documents` 两行前面的 `#` 去掉，但**开之前一定先看一遍清单**；
- 安装包碎片、下载到一半的文件，一律不碰。

## 它凭什么不会把我的东西搞丢

一句话：**先看清单、只搬不删、半个文件不碰、随时搬得回去**。想看细节的，看这张表：

| 怎么做到的 | 说明 |
| --- | --- |
| 先看清单 | 开关没打开时只写报告，一个文件都不碰 |
| 只搬不删 | 全程没有删除；碰到同名文件自动加 `-1`、`-2`，不覆盖 |
| 等文件写完 | 大小和修改时间连续 5 秒不变才动，不会搬走写了一半的文件 |
| 正在用的不碰 | Word、PS 正打开着的文件直接跳过 |
| 不自己折腾自己 | 收好的地方不再盯着，不会来回搬 |
| 文件夹整个搬 | 桌面上的文件夹不拆散，免得把还在解压的东西搬坏 |
| 小步走 | 一次最多 10 个，出岔子立刻停 |
| 记一笔账 | 每次搬都记下来，`undo --last` 一句话搬回去 |

## 开机后自动整理

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

装好之后，每次开机它就在后台自己盯着，不会弹黑窗口。如果电脑的安全设置不让装，跑一下 `service print`，它会把该敲的命令直接打出来给你复制；也可以改用「启动」文件夹的快捷方式（做法写在 `skill/deskflow-file-archiver/references/usage.md`）。

## 按时间往回翻（时间线页面）

```powershell
.venv\Scripts\python.exe -m deskflow.cli timeline
```

会在收好的那个文件夹里生成一个网页，双击就能打开。按年月排好，能搜、能按软件筛、点一下就打开原文件；照片按拍摄日期排。这个网页不联网，也不会把你的文件名传到任何地方。

## 给 AI 用的技能包（可选）

`skill/deskflow-file-archiver/` 是一个 AI 技能包。把它放进 WorkBuddy 的 skills 目录，以后在对话里说一句「帮我看看桌面该怎么整理」，AI 就会按规矩来：先给清单、等你点头、不删文件、不替你登录任何账号。

## 想自己改一份

直接 Fork 这个仓库，克隆下来照上面的步骤跑就行。`gh auth login` 要你本人在浏览器点授权，AI 不会替你登录。改完记得别把 `.venv/`、`reports/`、`logs/`、`config/local.toml` 传上去——里面有你电脑上的真实路径。

## 完全卸载

```powershell
.venv\Scripts\python.exe -m deskflow.cli service uninstall
```

然后删掉项目文件夹就行。已经收好的文件不会自己跑回桌面，想还原先执行 `undo --last` 再删。

## 几个要提前知道的事

- 只支持 Windows，Mac 和 Linux 用不了。
- 快捷方式搬走后照样能双击打开，只是以后得进那个文件夹找，习惯会变。
- 「此电脑」「回收站」和别人共用的快捷方式不会消失，桌面能清到几乎全空，但不是 100% 空。
- 默认只盯着桌面这一层；你在桌面上新建的文件夹里面的东西不会被自动收走，得手动跑一次整理。
- 文件搬走后，有些软件「最近打开的文件」里那条记录会点不开，从新位置打开一次就好。

## License

MIT，见 [LICENSE](LICENSE)。
