# BiliDownloader

> B 站专属 + 万能下载（基于 yt-dlp）双模式视频下载桌面工具（Python + PySide6）。「B站专属」标签页输入视频播放页链接或 BV 号，自动解析、下载并合并音画，输出可直接播放的 MP4；「万能下载」标签页粘贴任意 yt-dlp 支持的网站链接（含 B 站），支持单视频与播放列表。

> ⚠️ 本程序仅作为技术研究演示使用，使用者必须遵守 B 站用户协议以及版权相关法律法规，仅可下载自身拥有版权或已获得授权的视频，禁止私自下载、传播他人受版权保护的内容。

## 功能特性

### B站专属模式

- **两种输入，自动识别**：视频播放页完整 URL 或裸 BV 号，程序自动判断格式并解析。
- **仅处理单视频**：自动拒绝主页、合集、列表、番剧、直播、课程等非单视频页面，非法输入中文弹窗提示。
- **免登录可用**：默认免登录下载；可在设置中粘贴 Cookie 解锁更高画质（仅存内存、绝不落盘）。
- **后台下载 + 进度**：QThread 后台执行，进度条、速度、阶段实时展示，支持随时取消。
- **开箱即播的 MP4**：内嵌 ffmpeg 以 `-c copy` 自动合并音视频流，输出单一、无分片、无加密的 MP4，普通播放器直接打开。

### 万能下载模式（uni_dl / yt-dlp）

- **任意 yt-dlp 支持的网站**：粘贴 http/https 视频页链接（含 B 站），支持单视频与播放列表。
- **先解析后下载**：解析展示标题、UP主、时长、条目数，并区分单视频/播放列表。
- **画质预设 + 自定义格式**：预设下拉（最高可用 / 最高画质+最佳音质 / 单一文件（免合并）/ 最低画质），可另填自定义 yt-dlp 格式串（留空用预设）。
- **Cookie 两种来源**：浏览器读取（Chrome / Edge / Firefox / Brave / Opera / Vivaldi）或 cookies.txt 文件；Cookie 仅存内存、绝不落盘、不写回。
- **后台解析/下载**：解析与下载均在 QThread 后台线程执行，进度、阶段、速度实时回传，支持取消。
- **多线程加速（aria2c）**：内置 aria2c 1.37.0（GPLv2，附 COPYING），可勾选启用 8 连接下载（默认关闭，走内置分块下载器更稳）；失败自动回退内置下载器。
- **代理**：自动检测本机常见代理端口（Clash/v2rayN 等），也可手动填写 http/socks5 代理；留空走系统网络。
- **站点内置解析**：yhdmtv.cc、hanime1.me 等由内置解析直接提取直链；Cloudflare 反爬用 curl_cffi 浏览器指纹伪装。
- **失败自动恢复**：直链令牌失效（403/410）时自动重新解析页面换新直链并重试；连接中断自动分块续传。
- **设置自动记忆**：存储位置、代理模式与端口（默认 127.0.0.1:12334）、加速开关、主题会在重启后恢复；设置保存在 `%APPDATA%\BiliDownloader\settings.json`（Cookie 不保存）。
- **防误用旧结果**：输入框内容改变后，上一个链接的解析结果立即失效，下载按钮禁用，必须重新解析当前链接。

### 双模式与主题

- **两模式互不影响**：B站专属标签页的对象名与行为保持不变；万能下载独立维护自身解析/下载状态。
- **三套 QSS 主题**：菜单栏「主题(&T)」切换 chiikawa（默认，纯 QSS 粉彩可爱风，无图片资源）/ light（纯白）/ dark（纯黑）。
- **单文件 exe**：内含 Python 运行时、PySide6、requests、yt-dlp、aria2c、curl_cffi 与 ffmpeg，双击即用（体积随依赖版本变化）。

## 输入格式

### B站专属标签页

播放页 URL：

```
https://www.bilibili.com/video/BV1xx411c7mD
```

BV 号：

```
BV1xx411c7mD
```

说明：B站专属模式仅支持 `www.bilibili.com/video/BV...` 播放页完整链接或 BV 号；短链（b23.tv）、主页、合集、列表等一律拒绝。

### 万能下载标签页

任意 http/https 视频页链接，单视频或播放列表均可：

```
https://www.bilibili.com/video/BV1xx411c7mD
https://www.youtube.com/watch?v=...
https://www.youtube.com/playlist?list=...
```

说明：万能下载模式交由 yt-dlp 识别站点与页面类型，实际支持范围以当前 yt-dlp 版本为准；仅支持 http/https 链接，非链接输入会以中文提示拒绝。部分站点（如 yhdmtv.cc）由程序内置预解析直接提取播放源。

## 快速开始

### 方式一：直接使用 exe

从 [Releases](https://github.com/Seiran-Tsurumi/BiliDownloader/releases) 下载 `BiliDownloader.exe`，双击运行，无需安装 Python 或 ffmpeg。

### 方式二：源码运行

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\pythonw.exe main.py
```

或直接双击 `run.bat`（未创建虚拟环境时会给出提示后退出）。

开发自检（离屏创建主窗口后立即关闭，退出码 0 表示通过）：

```bat
.venv\Scripts\python.exe main.py --selftest
```

### 重新打包 exe

```bat
.venv\Scripts\python -m pip install pyinstaller
build_exe.bat
```

## 程序结构

```
BiliDownloader/
├── main.py                     # 入口：启动 GUI；--selftest 离屏冒烟
├── bili_dl/                    # B站专属下载核心（纯 Python、无 UI、可独立复用）
│   ├── parse.py                # 输入识别：URL / BV 校验，拒绝非单视频页面
│   ├── api.py                  # B 站接口：view / playurl（WBI 签名）
│   ├── wbi.py                  # WBI 签名实现（mixin_key 派生、参数排序过滤、md5）
│   ├── net.py                  # HTTP 层：UA/Referer、失败重试、流式下载、取消检查
│   ├── download.py             # 画质列表、选流、下载、ffmpeg 合并、命名与清理
│   ├── models.py               # VideoMeta / Quality 数据模型
│   ├── errors.py               # InputError / ApiError / DownloadError / CancelledError
│   └── tests/                  # 30 个离线单测 + 5 个真实网络集成测试
├── uni_dl/                     # 万能下载核心（基于 yt-dlp，纯 Python、无 UI）
│   ├── __init__.py             # parse_input / download_video / 格式预设 / Cookie 参数 / 中文错误 / 站点预解析
│   └── tests/                  # 71 项离线单测（mock yt_dlp.YoutubeDL / requests / socket，不联网）
├── gui/                        # PySide6 界面
│   ├── main_window.py          # 主窗口：B站专属 + 万能下载双标签页、主题菜单
│   ├── workers.py              # QThread 后台工作线程（B站解析/下载 + 万能解析/下载）
│   ├── theme.py                # 三套 QSS 主题（chiikawa / light / dark）
│   ├── notify.py               # 弹窗薄封装（便于测试）
│   └── tests/                  # B站 GUI 自测 + 万能下载 GUI 自测 + 真实集成测试
├── requirements.txt            # 运行时依赖（requests / imageio-ffmpeg / PySide6 / yt-dlp）
├── BiliDownloader.spec         # PyInstaller 打包配置（collect imageio_ffmpeg + yt_dlp）
├── build_exe.bat               # 一键打包
├── run.bat                     # 源码启动脚本
└── README.md
```

## 实现方法

### 1. 输入识别（B站专属）

纯本地正则判断，零网络开销：匹配 `BV` 号格式（长度、大小写、字符集校验）或 `https://www.bilibili.com/video/BV...` 播放页 URL（可带 query 参数）。命中 `space.`、`/list/`、`collection`、`bangumi`、`live`、`cheese` 等特征的一律抛 `InputError`（中文提示），不做任何接口调用。

### 2. 元数据获取（B站专属）

调用 `x/web-interface/view` 接口（WBI 签名）获取 `bvid → aid/cid/title/owner/duration`。接口错误码统一映射为中文说明（-404 视频不存在、-403 权限不足、-352 风控、-101 未登录等）。

### 3. WBI 签名

B 站接口的反爬签名，自行实现：

1. 请求 `x/web-interface/nav` 获取 `wbi_img.img_url` / `sub_url`，取文件名部分拼接为原始 key；
2. 按官方混排表将原始 key 重排为 `mixin_key`（进程内缓存 1 小时）；
3. 参数表加入 `wts` 时间戳，按键名排序，过滤 `!'()*` 特殊字符后拼接，md5 得 `w_rid`。

已用官方测试向量校验通过。

### 4. 播放地址与流选择（B站专属）

调用 `x/player/wbi/playurl`（`fnval=4048` 请求 DASH）：

- 优先取 DASH 的视频流 + 音频流（DASH 免登录通常只给到 480P）；
- 若无 Cookie 且 durl 接口实际提供更高画质（实测可得 720P），按约定回退 durl 单文件流；
- `quality="max"` 时自动取实际可得最高档；指定不可得档位抛中文 `ApiError`。

### 5. 下载与合并（B站专属）

- 流式下载，64 KB/块写入，每块检查取消标志，支持断点续传与失败重试（指数退避）；
- 下载完成后用内嵌 ffmpeg（`imageio_ffmpeg.get_ffmpeg_exe()`）执行 `-c copy` 封装合并，**不转码**，保留原始编码与音轨；
- 合并成功即删除全部临时分片，输出目录只留最终 MP4；
- 文件名 = 清洗后的标题 + BV 号，重名自动追加 ` (1)` 序号。

### 6. 线程模型

B站与万能下载的网络、解析、合并全部在 `QThread` 工作线程执行，通过信号回传进度与结果；UI 线程零阻塞。B站进度回调 `progress(stage, downloaded, total)`，阶段依次为 `fetching → video → audio → merging → done`；万能下载阶段为 `video → merging → done`。

### 7. 错误分级

| 异常 | 触发场景 | 界面表现 |
|---|---|---|
| `InputError` | 输入非法、非单视频链接 | 中文弹窗，不发起网络请求 |
| `ApiError` | 接口失败、风控、画质不可得 | 中文弹窗展示原因 |
| `DownloadError` | 网络/磁盘/合并失败 | 中文弹窗 |
| `CancelledError` | 用户取消 | "已取消下载"提示，清理临时文件 |

### 8. 万能下载模式（uni_dl / yt-dlp）

- **解析**：`yt_dlp.YoutubeDL.extract_info(url, download=False)` 获取标题、UP主、时长、条目数，`_type` 为 playlist/multi_video 时识别为播放列表；错误经关键词映射为中文（站点不支持、视频不可用、网络失败、Cookie 无效、无可用格式等）。
- **下载**：`yt_dlp.YoutubeDL.download([url])`，输出模板 `%(title)s [%(id)s].%(ext)s`，`merge_output_format=mp4`，ffmpeg 使用 `imageio_ffmpeg.get_ffmpeg_exe()` 内置二进制。
- **画质/格式**：预设下拉 `bestvideo*+bestaudio/best`（最高可用）、`bestvideo+bestaudio/best`（最高画质+最佳音质）、`best/bestvideo+bestaudio`（单一文件免合并）、`worst`（最低画质）；「格式」输入框留空用预设，也可填自定义 yt-dlp 格式串。
- **Cookie**：仅经参数传入、仅存内存；支持浏览器读取（chrome / edge / firefox / brave / opera / vivaldi）或 `cookiefile`（cookies.txt 路径），二者只能选其一；关闭下载器时禁止把内存 cookie jar 写回磁盘。
- **播放列表**：`noplaylist=False`、`ignoreerrors=True`，逐项下载，单项失败不中断，成功项路径逐项返回。
- **取消**：`UniCancelledError` 同时继承 `yt_dlp.utils.DownloadCancelled`，取消信号可穿透 yt-dlp 播放列表循环。
- **多线程/代理**：勾选加速时 `external_downloader` 指向内置 aria2c（`-x8 -s8 -k1M`，连接超时 10s、单请求 20s、最多 5 次重试），失败回退内置分块下载器；`proxy` 同时用于 yt-dlp 与页面抓取。
- **反爬**：页面抓取优先 curl_cffi（chrome/edge 指纹），失败回退 requests；返回 200 但无直链（挑战页）也会自动重试。
- **站点解析**：对 yhdmtv.cc（Base64 混淆 m3u8）与 hanime1.me（vdownload 签名直链）内置解析，取页面内最高画质。
- **重试**：最多 3 次（aria2c → 内置下载器 → 重新解析直链），令牌失效/403/410 映射为中文错误。

## 画质与 Cookie 说明

### B站专属

- 解析成功后，在「画质」下拉框选择目标画质（默认「最高可用」）。
- Cookie 粘贴入口：菜单栏 **设置 → Cookie 设置…**，粘贴完整 Cookie 字符串（可选）。
- Cookie 仅保存在程序内存变量中，**仅本次运行有效，程序不会写入磁盘**；用于解锁高画质。

### 万能下载

- 解析成功后，在「画质」下拉框选择预设（默认「最高可用」）；「格式」输入框可留空或填自定义 yt-dlp 格式串。
- Cookie 入口：标签页内「Cookie 浏览器」下拉（不登录 / Chrome / Edge / Firefox / Brave / Opera / Vivaldi）或「Cookie 文件」选择 cookies.txt；二者只生效其一（优先 cookies.txt）。
- Cookie 仅本次运行有效、仅存内存：浏览器 Cookie 读取进内存，程序不保存、不写回任何 cookie 文件。
- 「代理」默认自动检测（含 12334 / 7890 / 10809 / 10808 / 1080 等常见端口）；手动模式可填 `http://127.0.0.1:12334` 或 `socks5://127.0.0.1:7891`，留空则走系统网络。

### 主题

菜单栏 **主题(&T)** 可切换 chiikawa（默认）/ light / dark；chiikawa 为纯 QSS 粉彩风格，不依赖任何图片资源。

## Cookie 获取步骤（B站专属）

1. 在浏览器中登录 bilibili.com，打开任意一个视频页面。
2. 按 F12 打开开发者工具，切换到 Network（网络）面板。
3. 刷新页面，在请求列表中找到 `api.bilibili.com` 开头的请求。
4. 在右侧 Request Headers（请求标头）中找到 `Cookie` 一项，复制其完整值。
5. 回到程序：**设置 → Cookie 设置…**，粘贴后点击确定。

万能下载标签页无需手动复制 Cookie：直接在「Cookie 浏览器」下拉选择浏览器，或点「选择…」指定 cookies.txt 文件即可。

## 测试

```bat
.venv\Scripts\python.exe -m unittest discover -s bili_dl/tests -t .    # B站核心 35 项（含 5 项真实网络集成）
.venv\Scripts\python.exe -m unittest discover -s uni_dl/tests -t .     # 万能下载核心 71 项（全离线 mock）
.venv\Scripts\python.exe main.py --selftest                             # GUI 冒烟
.venv\Scripts\python.exe gui/tests/test_gui.py                          # B站 GUI 离屏自测（脚本内置 offscreen）
.venv\Scripts\python.exe gui/tests/test_universal_gui.py                # 万能下载 GUI 离屏自测（脚本内置 offscreen）
```

## 已知限制

### B站专属模式

- 免登录（未提供 Cookie）实际最高可下载 720P（DASH 回退 durl 所得）；提供有效 Cookie 后可下载更高画质（受账号权益限制）。
- 仅支持单视频：不支持番剧、多 P、收藏夹等批量下载；B站专属模式仅支持 `www.bilibili.com` 播放页链接与 BV 号。
- Cookie 仅本次运行有效、不落盘，程序重启后需重新粘贴。
- 4K/8K/HDR/杜比等大会员画质需登录 + 会员，程序会在不可得时给出中文提示。

### 万能下载模式

- 受 yt-dlp 支持范围与目标网站限制：不支持的站点、需登录/会员内容或站点风控可能导致解析或下载失败（中文提示）。
- Cookie 仅内存：浏览器 Cookie 与 cookies.txt 均仅用于本次解析/下载，程序不保存、不写回，重启后需重新选择。
- 播放列表逐项下载，单项失败不中断（`ignoreerrors=True`），成功项保留，日志展示逐项路径。
- 音视频合并/后处理依赖 `imageio_ffmpeg` 内置 ffmpeg，无需另行安装 ffmpeg。
- 多线程加速使用内置 aria2c（默认 8 连接）；部分站点限制并发连接，可在界面关闭加速改用内置单连接分块下载。
- 启用 Cloudflare 反爬的站点可能仍要求浏览器 Cookie 或可用代理；程序会用 curl_cffi 伪装并自动重试，但仍可能被拒。
- 站点对单连接限流/中途断开时，程序按 10MB 分块请求并自动重试续传，避免大文件下载被截断。
- 部分站点（如 yhdmtv.cc）通过内置预解析提取 m3u8 播放源，站点改版可能导致该解析失效（届时会退回中文错误提示）。

## 合规声明

> 本程序仅作为技术研究演示使用，使用者必须遵守B站用户协议以及版权相关法律法规，仅可下载自身拥有版权或已获得授权的视频，禁止私自下载、传播他人受版权保护的内容。

万能下载模式：

> 万能下载基于 yt-dlp 仅作技术研究演示，请仅下载自身拥有版权或已获授权的视频，禁止下载、传播他人受版权保护的内容，并遵守目标网站的服务条款与当地法律法规。

## 许可

[MIT](LICENSE)

第三方组件：aria2（GPLv2，见 `tools/aria2/COPYING`）、yt-dlp（Unlicense）、curl_cffi（MIT）、imageio-ffmpeg（BSD）、PySide6（LGPLv3）、requests（Apache-2.0）。
