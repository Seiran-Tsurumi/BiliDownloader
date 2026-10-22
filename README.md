# BiliDownloader

> B 站单视频下载桌面工具（Python + PySide6）。输入视频播放页链接或 BV 号，程序自动解析、下载并合并音画，输出可直接播放的 MP4。

> ⚠️ 本程序仅作为技术研究演示使用，使用者必须遵守 B 站用户协议以及版权相关法律法规，仅可下载自身拥有版权或已获得授权的视频，禁止私自下载、传播他人受版权保护的内容。

## 功能特性

- **两种输入，自动识别**：视频播放页完整 URL 或裸 BV 号，程序自动判断格式并解析。
- **仅处理单视频**：自动拒绝主页、合集、列表、番剧、直播、课程等非单视频页面，非法输入中文弹窗提示。
- **免登录可用**：默认免登录下载；可在设置中粘贴 Cookie 解锁更高画质（仅存内存、绝不落盘）。
- **后台下载 + 进度**：QThread 后台执行，进度条、速度、阶段实时展示，支持随时取消。
- **开箱即播的 MP4**：内嵌 ffmpeg 以 `-c copy` 自动合并音视频流，输出单一、无分片、无加密的 MP4，普通播放器直接打开。
- **单文件 exe**：约 80 MB，内含 Python 运行时、PySide6、requests 与 ffmpeg，双击即用。

## 输入格式

播放页 URL：

```
https://www.bilibili.com/video/BV1xx411c7mD
```

BV 号：

```
BV1xx411c7mD
```

说明：仅支持 `www.bilibili.com/video/BV...` 播放页完整链接或 BV 号；短链（b23.tv）、主页、合集、列表等一律拒绝。

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
├── bili_dl/                    # 下载核心（纯 Python、无 UI、可独立复用）
│   ├── parse.py                # 输入识别：URL / BV 校验，拒绝非单视频页面
│   ├── api.py                  # B 站接口：view / playurl（WBI 签名）
│   ├── wbi.py                  # WBI 签名实现（mixin_key 派生、参数排序过滤、md5）
│   ├── net.py                  # HTTP 层：UA/Referer、失败重试、流式下载、取消检查
│   ├── download.py             # 画质列表、选流、下载、ffmpeg 合并、命名与清理
│   ├── models.py               # VideoMeta / Quality 数据模型
│   ├── errors.py               # InputError / ApiError / DownloadError / CancelledError
│   └── tests/                  # 30 个离线单测 + 5 个真实网络集成测试
├── gui/                        # PySide6 界面
│   ├── main_window.py          # 主窗口与交互状态机
│   ├── workers.py              # QThread 后台工作线程（解析 / 下载）
│   ├── notify.py               # 弹窗薄封装（便于测试）
│   └── tests/                  # 35 项离屏 UI 自测 + 真实集成测试
├── requirements.txt            # 运行时依赖
├── BiliDownloader.spec         # PyInstaller 打包配置
├── build_exe.bat               # 一键打包
├── run.bat                     # 源码启动脚本
└── README.md
```

## 实现方法

### 1. 输入识别

纯本地正则判断，零网络开销：匹配 `BV` 号格式（长度、大小写、字符集校验）或 `https://www.bilibili.com/video/BV...` 播放页 URL（可带 query 参数）。命中 `space.`、`/list/`、`collection`、`bangumi`、`live`、`cheese` 等特征的一律抛 `InputError`（中文提示），不做任何接口调用。

### 2. 元数据获取

调用 `x/web-interface/view` 接口（WBI 签名）获取 `bvid → aid/cid/title/owner/duration`。接口错误码统一映射为中文说明（-404 视频不存在、-403 权限不足、-352 风控、-101 未登录等）。

### 3. WBI 签名

B 站接口的反爬签名，自行实现：

1. 请求 `x/web-interface/nav` 获取 `wbi_img.img_url` / `sub_url`，取文件名部分拼接为原始 key；
2. 按官方混排表将原始 key 重排为 `mixin_key`（进程内缓存 1 小时）；
3. 参数表加入 `wts` 时间戳，按键名排序，过滤 `!'()*` 特殊字符后拼接，md5 得 `w_rid`。

已用官方测试向量校验通过。

### 4. 播放地址与流选择

调用 `x/player/wbi/playurl`（`fnval=4048` 请求 DASH）：

- 优先取 DASH 的视频流 + 音频流（DASH 免登录通常只给到 480P）；
- 若无 Cookie 且 durl 接口实际提供更高画质（实测可得 720P），按约定回退 durl 单文件流；
- `quality="max"` 时自动取实际可得最高档；指定不可得档位抛中文 `ApiError`。

### 5. 下载与合并

- 流式下载，64 KB/块写入，每块检查取消标志，支持断点续传与失败重试（指数退避）；
- 下载完成后用内嵌 ffmpeg（`imageio_ffmpeg.get_ffmpeg_exe()`）执行 `-c copy` 封装合并，**不转码**，保留原始编码与音轨；
- 合并成功即删除全部临时分片，输出目录只留最终 MP4；
- 文件名 = 清洗后的标题 + BV 号，重名自动追加 ` (1)` 序号。

### 6. 线程模型

网络、解析、合并全部在 `QThread` 工作线程执行，通过信号回传进度与结果；UI 线程零阻塞。进度回调 `progress(stage, downloaded, total)`，阶段依次为 `fetching → video → audio → merging → done`。

### 7. 错误分级

| 异常 | 触发场景 | 界面表现 |
|---|---|---|
| `InputError` | 输入非法、非单视频链接 | 中文弹窗，不发起网络请求 |
| `ApiError` | 接口失败、风控、画质不可得 | 中文弹窗展示原因 |
| `DownloadError` | 网络/磁盘/合并失败 | 中文弹窗 |
| `CancelledError` | 用户取消 | "已取消下载"提示，清理临时文件 |

## 画质与 Cookie 说明

- 解析成功后，在「画质」下拉框选择目标画质（默认「最高可用」）。
- Cookie 粘贴入口：菜单栏 **设置 → Cookie 设置…**，粘贴完整 Cookie 字符串（可选）。
- Cookie 仅保存在程序内存变量中，**仅本次运行有效，程序不会写入磁盘**；用于解锁高画质。

## Cookie 获取步骤

1. 在浏览器中登录 bilibili.com，打开任意一个视频页面。
2. 按 F12 打开开发者工具，切换到 Network（网络）面板。
3. 刷新页面，在请求列表中找到 `api.bilibili.com` 开头的请求。
4. 在右侧 Request Headers（请求标头）中找到 `Cookie` 一项，复制其完整值。
5. 回到程序：**设置 → Cookie 设置…**，粘贴后点击确定。

## 测试

```bat
.venv\Scripts\python.exe -m unittest discover -s bili_dl/tests -t .    # 核心 35 项
.venv\Scripts\python.exe main.py --selftest                             # GUI 冒烟
QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe gui/tests/test_gui.py # 35 项离屏 UI 自测
```

## 已知限制

- 免登录（未提供 Cookie）实际最高可下载 720P（DASH 回退 durl 所得）；提供有效 Cookie 后可下载更高画质（受账号权益限制）。
- 仅支持单视频：不支持番剧、多 P、收藏夹等批量下载；仅支持 `www.bilibili.com` 播放页链接与 BV 号。
- Cookie 仅本次运行有效、不落盘，程序重启后需重新粘贴。
- 4K/8K/HDR/杜比等大会员画质需登录 + 会员，程序会在不可得时给出中文提示。

## 合规声明

> 本程序仅作为技术研究演示使用，使用者必须遵守B站用户协议以及版权相关法律法规，仅可下载自身拥有版权或已获得授权的视频，禁止私自下载、传播他人受版权保护的内容。

## 许可

[MIT](LICENSE)
