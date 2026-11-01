"""BiliDownloader 主窗口：B站专属下载、万能下载、视图打包与飞机模式（Telegram）。

UI 线程只负责界面；parse_input / list_qualities / download_video、
uni_dl.parse_input / uni_dl.download_video、page_dl.parse_page / page_dl.download_page
以及 tg_dl.qr_login / list_channel_media / download_channel_media
全部在 QThread 后台线程中执行，通过信号回传进度与结果。
B站标签页的对象名与行为保持不变。
"""

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import notify
from . import settings as app_settings
from .assets import app_icon
from .theme import apply_theme
from .workers import (
    DownloadWorker,
    PagePackWorker,
    PageParseWorker,
    ParseWorker,
    TgDownloadWorker,
    TgListWorker,
    TgQrLoginWorker,
    UniversalDownloadWorker,
    UniversalParseWorker,
)

_CORE_IMPORT_ERROR = None
try:
    from bili_dl import (
        ApiError,
        CancelledError,
        DownloadError,
        InputError,
        download_video,
        list_qualities,
        parse_input,
    )
    _CORE_READY = True
except ImportError:  # 核心未就绪：GUI 仍可启动，仅下载不可用
    import sys as _sys

    _CORE_READY = False
    _CORE_IMPORT_ERROR = str(_sys.exc_info()[1])
    ApiError = CancelledError = DownloadError = InputError = None
    download_video = list_qualities = parse_input = None

_UNI_IMPORT_ERROR = None
try:
    from uni_dl import (
        DEFAULT_FORMAT,
        FORMAT_PRESETS,
        UniCancelledError,
        UniDownloadError,
        UniInputError,
        download_video as uni_download_video,
        parse_input as uni_parse_input,
    )
    import uni_dl as _uni_dl_module
    _UNI_READY = True
except ImportError:  # uni_dl 未就绪：万能标签页可显示，但解析/下载禁用
    import sys as _uni_sys

    _UNI_READY = False
    _UNI_IMPORT_ERROR = str(_uni_sys.exc_info()[1])
    DEFAULT_FORMAT = None
    FORMAT_PRESETS = ()
    UniCancelledError = UniDownloadError = UniInputError = None
    uni_download_video = uni_parse_input = None
    _uni_dl_module = None

_PACK_IMPORT_ERROR = None
try:
    from page_dl import (
        PageCancelledError,
        PageDownloadError,
        PageInputError,
        download_page as pack_download_page,
        parse_page,
    )
    import page_dl as _pack_dl_module
    _PACK_READY = True
except ImportError:  # page_dl 未就绪：视图打包标签页可显示，但解析/打包禁用
    import sys as _pack_sys

    _PACK_READY = False
    _PACK_IMPORT_ERROR = str(_pack_sys.exc_info()[1])
    PageCancelledError = PageDownloadError = PageInputError = None
    pack_download_page = parse_page = None
    _pack_dl_module = None

_TG_IMPORT_ERROR = None
try:
    from tg_dl import (
        TgAuthError,
        TgCancelledError,
        TgConfig,
        TgDownloadError,
        TgInputError,
        default_session_path as tg_default_session_path,
        download_channel_media as tg_download_channel_media,
        list_channel_media as tg_list_channel_media,
        logout as tg_logout,
        qr_login as tg_qr_login,
        qr_matrix as tg_qr_matrix,
    )
    import tg_dl as _tg_dl_module
    _TG_READY = True
except Exception:  # tg_dl 或依赖（telethon）未就绪：飞机标签页可显示，但登录/下载禁用
    import sys as _tg_sys

    _TG_READY = False
    _TG_IMPORT_ERROR = str(_tg_sys.exc_info()[1])
    TgAuthError = TgCancelledError = TgConfig = TgDownloadError = TgInputError = None
    tg_default_session_path = tg_download_channel_media = None
    tg_list_channel_media = tg_logout = tg_qr_login = tg_qr_matrix = None
    _tg_dl_module = None

COMPLIANCE_TEXT = (
    "本程序仅作为技术研究演示使用，使用者必须遵守B站用户协议以及版权相关法律法规，"
    "仅可下载自身拥有版权或已获得授权的视频，禁止私自下载、传播他人受版权保护的内容。"
)
UNI_COMPLIANCE_TEXT = (
    "万能下载基于 yt-dlp 仅作技术研究演示，请仅下载自身拥有版权或已获授权的视频，"
    "禁止下载、传播他人受版权保护的内容，并遵守目标网站的服务条款与当地法律法规。"
)
PACK_COMPLIANCE_TEXT = (
    "视图打包功能仅作技术研究演示，请仅打包自身拥有版权或已获授权的内容，"
    "禁止批量抓取、传播他人受版权保护的媒体，并遵守目标网站服务条款与当地法律法规。"
)
TG_COMPLIANCE_TEXT = (
    "飞机模式基于 Telethon 客户端，仅作技术研究演示：请仅下载自身拥有版权或已获授权的频道媒体，"
    "禁止批量抓取、传播他人受版权保护的音视频与文件，并遵守 Telegram 服务条款与当地法律法规。"
)
WINDOW_TITLE = "BiliDownloader - 视频下载工具（技术研究演示）"
DEFAULT_QUALITY_LABEL = "最高可用"

_STAGE_TEXT = {
    "fetching": "获取视频信息",
    "video": "下载视频流",
    "audio": "下载音频流",
    "merging": "合并音视频",
    "done": "完成",
}

_PACK_STAGE_TEXT = {
    "download": "下载媒体",
    "packing": "打包 ZIP",
    "done": "完成",
}

_TG_STAGE_TEXT = {
    "download": "下载媒体",
    "done": "完成",
}


def _format_bytes(num):
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0 or unit == "TB":
            return f"{int(num)} B" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def _format_duration(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "未知"
    if seconds <= 0:
        return "未知"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _default_save_dir():
    folder = Path.home() / "Downloads" / "BiliDownloader"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        folder = Path.home()
    return folder


def _uni_has_accelerator():
    """探测 uni_dl 的多线程加速可用性；核心缺少该接口或异常时按不可用处理。"""
    probe = getattr(_uni_dl_module, "has_accelerator", None)
    if probe is None:
        return False
    try:
        return bool(probe())
    except Exception:  # 探测失败不应影响界面
        return False


def _uni_detect_local_proxy():
    """探测本地代理；核心缺少该接口或异常时返回 None（走系统网络）。"""
    probe = getattr(_uni_dl_module, "detect_local_proxy", None)
    if probe is None:
        return None
    try:
        proxy = probe()
    except Exception:
        return None
    return str(proxy) if proxy else None


def _mask_secret(value):
    """脱敏展示敏感串（API Hash 绝不整段写入日志）。"""
    text = str(value or "")
    if not text:
        return "未填写"
    if len(text) <= 4:
        return "*" * len(text)
    return text[:4] + "…" + "*" * 4


def _tg_detect_local_proxy():
    """飞机模式的本地代理探测：优先 tg_dl，其次复用万能下载的探测结果。"""
    probe = getattr(_tg_dl_module, "detect_local_proxy", None)
    if probe is None:
        return _uni_detect_local_proxy()
    try:
        proxy = probe()
    except Exception:
        return None
    return str(proxy) if proxy else None


def _pack_detect_local_proxy():
    """打包页的本地代理探测：优先 page_dl，其次复用万能下载的探测结果。"""
    probe = getattr(_pack_dl_module, "detect_local_proxy", None)
    if probe is None:
        return _uni_detect_local_proxy()
    try:
        proxy = probe()
    except Exception:
        return None
    return str(proxy) if proxy else None


class MainWindow(QMainWindow):
    """主窗口：QTabWidget 承载 B站专属下载与万能下载。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(820, 680)
        self.setMinimumSize(680, 520)
        icon = app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        self._cookie = None      # 仅内存变量，绝不写盘
        self._meta = None
        self._parsed_text = None
        self._worker = None
        self._parsing = False
        self._last_stage = None
        self._speed_anchor_bytes = 0
        self._speed_anchor_time = 0.0

        self._uni_meta = None
        self._uni_parsed_text = None
        self._uni_parse_text = None
        self._uni_worker = None
        self._uni_parsing = False
        self._uni_last_stage = None
        self._uni_speed_anchor_bytes = 0
        self._uni_speed_anchor_time = 0.0

        self._pack_bundle = None
        self._pack_parsed_text = None
        self._pack_parse_text = None
        self._pack_worker = None
        self._pack_parsing = False
        self._pack_last_stage = None
        self._pack_speed_anchor_bytes = 0
        self._pack_speed_anchor_time = 0.0

        self._tg_login_worker = None
        self._tg_list_worker = None
        self._tg_worker = None
        self._tg_last_stage = None
        self._tg_speed_anchor_bytes = 0
        self._tg_speed_anchor_time = 0.0
        self._syncing_proxy = False   # 万能页/打包页共用代理设置时的同步哨兵

        self._settings = app_settings.load_settings()
        self._current_theme = str(self._settings.get("theme") or "chiikawa")

        self._build_ui()

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._current_theme)

        if not _CORE_READY:
            self._log(f"警告：核心模块 bili_dl 未就绪（{_CORE_IMPORT_ERROR}），下载功能暂不可用。")
            self.download_button.setEnabled(False)
        else:
            self._log("已就绪，粘贴视频链接或 BV 号后点击“下载”。")

        if not _UNI_READY:
            self._uni_log(f"警告：万能下载模块 uni_dl 未就绪（{_UNI_IMPORT_ERROR}），解析与下载暂不可用。")
            self.uni_parse_button.setEnabled(False)
            self.uni_download_button.setEnabled(False)
        else:
            self._uni_log("万能下载已就绪，粘贴任意网站视频页链接后点击“解析”。")
            if _uni_has_accelerator():
                self._uni_log("已找到 aria2c，可勾选“多线程加速”（默认关闭；站点限制并发时可能失败，程序会自动回退内置下载器）。")
            else:
                self.uni_accel_check.setChecked(False)
                self.uni_accel_check.setEnabled(False)
                self._uni_log("未找到 aria2c，使用内置单连接分块下载")

        if not _PACK_READY:
            self._pack_log(f"警告：视图打包模块 page_dl 未就绪（{_PACK_IMPORT_ERROR}），解析与打包暂不可用。")
            self.pack_parse_button.setEnabled(False)
            self.pack_start_button.setEnabled(False)
        else:
            self._pack_log("视图打包已就绪，粘贴页面 URL 后点击“解析页面”。")

        if not _TG_READY:
            self._tg_log(f"警告：飞机模式模块 tg_dl 未就绪（{_TG_IMPORT_ERROR}），登录与下载暂不可用。")
            self.tg_login_button.setEnabled(False)
            self.tg_logout_button.setEnabled(False)
            self.tg_list_button.setEnabled(False)
            self.tg_start_button.setEnabled(False)
        else:
            self._tg_log("飞机模式已就绪：填写 API ID / API Hash 后点击“扫码登录”。")

    # ---------- UI 构建 ----------

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        settings_menu = self.menuBar().addMenu("设置(&S)")
        self.cookie_action = settings_menu.addAction("Cookie 设置…")
        self.cookie_action.setObjectName("cookie_action")
        self.cookie_action.triggered.connect(self._open_cookie_dialog)

        theme_menu = self.menuBar().addMenu("主题(&T)")
        self.theme_action_chiikawa = theme_menu.addAction("chiikawa")
        self.theme_action_chiikawa.setObjectName("theme_action_chiikawa")
        self.theme_action_chiikawa.triggered.connect(lambda: self._apply_theme("chiikawa"))
        self.theme_action_light = theme_menu.addAction("light")
        self.theme_action_light.setObjectName("theme_action_light")
        self.theme_action_light.triggered.connect(lambda: self._apply_theme("light"))
        self.theme_action_dark = theme_menu.addAction("dark")
        self.theme_action_dark.setObjectName("theme_action_dark")
        self.theme_action_dark.triggered.connect(lambda: self._apply_theme("dark"))

        self.mode_tabs = QTabWidget()
        self.mode_tabs.setObjectName("mode_tabs")
        root.addWidget(self.mode_tabs, 1)

        self._build_bilibili_tab()
        self._build_universal_tab()
        self._build_pack_tab()
        self._build_tg_tab()
        self._connect_settings_signals()

    def _build_bilibili_tab(self):
        tab = QWidget()
        tab.setObjectName("bilibili_tab")
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("视频链接："))
        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("input_edit")
        self.input_edit.setPlaceholderText("粘贴视频播放页链接或 BV 号")
        self.input_edit.returnPressed.connect(self._on_download_clicked)
        input_row.addWidget(self.input_edit, 1)
        self.download_button = QPushButton("下载")
        self.download_button.setObjectName("download_button")
        self.download_button.clicked.connect(self._on_download_clicked)
        input_row.addWidget(self.download_button)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("cancel_button")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        input_row.addWidget(self.cancel_button)
        layout.addLayout(input_row)

        option_row = QHBoxLayout()
        option_row.addWidget(QLabel("画质："))
        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("quality_combo")
        self.quality_combo.setEnabled(False)
        option_row.addWidget(self.quality_combo, 1)
        option_row.addWidget(QLabel("保存到："))
        self.save_dir_edit = QLineEdit(str(self._settings.get("bili_save_dir") or _default_save_dir()))
        self.save_dir_edit.setObjectName("save_dir_edit")
        self.save_dir_edit.setReadOnly(True)
        option_row.addWidget(self.save_dir_edit, 2)
        self.browse_button = QPushButton("选择…")
        self.browse_button.setObjectName("browse_button")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        option_row.addWidget(self.browse_button)
        layout.addLayout(option_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progress_bar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        progress_text_row = QHBoxLayout()
        self.stage_label = QLabel("就绪")
        self.stage_label.setObjectName("stage_label")
        self.percent_label = QLabel("—")
        self.percent_label.setObjectName("percent_label")
        self.speed_label = QLabel("—")
        self.speed_label.setObjectName("speed_label")
        progress_text_row.addWidget(self.stage_label, 2)
        progress_text_row.addWidget(self.percent_label)
        progress_text_row.addWidget(self.speed_label)
        layout.addLayout(progress_text_row)

        layout.addWidget(QLabel("状态日志："))
        self.status_log = QPlainTextEdit()
        self.status_log.setObjectName("status_log")
        self.status_log.setReadOnly(True)
        self.status_log.setMaximumBlockCount(2000)
        layout.addWidget(self.status_log, 1)

        self.compliance_label = QLabel(COMPLIANCE_TEXT)
        self.compliance_label.setObjectName("compliance_label")
        self.compliance_label.setWordWrap(True)
        self.compliance_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.compliance_label)

        self.mode_tabs.addTab(tab, "B站专属")

    def _build_universal_tab(self):
        tab = QWidget()
        tab.setObjectName("universal_tab")
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("视频链接："))
        self.uni_input_edit = QLineEdit()
        self.uni_input_edit.setObjectName("uni_input_edit")
        self.uni_input_edit.setPlaceholderText("任意网站视频页链接，支持播放列表")
        self.uni_input_edit.returnPressed.connect(self._on_uni_parse_clicked)
        self.uni_input_edit.textChanged.connect(self._on_uni_input_changed)
        input_row.addWidget(self.uni_input_edit, 1)
        self.uni_parse_button = QPushButton("解析")
        self.uni_parse_button.setObjectName("uni_parse_button")
        self.uni_parse_button.clicked.connect(self._on_uni_parse_clicked)
        input_row.addWidget(self.uni_parse_button)
        layout.addLayout(input_row)

        option_row = QHBoxLayout()
        option_row.addWidget(QLabel("画质："))
        self.uni_quality_combo = QComboBox()
        self.uni_quality_combo.setObjectName("uni_quality_combo")
        if FORMAT_PRESETS:
            for desc, fmt in FORMAT_PRESETS:
                self.uni_quality_combo.addItem(str(desc), str(fmt))
        elif DEFAULT_FORMAT:
            self.uni_quality_combo.addItem(str(DEFAULT_FORMAT), str(DEFAULT_FORMAT))
        self.uni_quality_combo.setCurrentIndex(0)
        option_row.addWidget(self.uni_quality_combo, 1)
        option_row.addWidget(QLabel("格式："))
        self.uni_format_edit = QLineEdit()
        self.uni_format_edit.setObjectName("uni_format_edit")
        self.uni_format_edit.setPlaceholderText("可选：自定义 yt-dlp 格式串，留空用预设")
        option_row.addWidget(self.uni_format_edit, 1)
        layout.addLayout(option_row)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("保存到："))
        self.uni_save_dir_edit = QLineEdit(str(self._settings.get("uni_save_dir") or _default_save_dir()))
        self.uni_save_dir_edit.setObjectName("uni_save_dir_edit")
        self.uni_save_dir_edit.setReadOnly(True)
        save_row.addWidget(self.uni_save_dir_edit, 1)
        self.uni_browse_button = QPushButton("选择…")
        self.uni_browse_button.setObjectName("uni_browse_button")
        self.uni_browse_button.clicked.connect(self._on_uni_browse_clicked)
        save_row.addWidget(self.uni_browse_button)
        layout.addLayout(save_row)

        accel_row = QHBoxLayout()
        accel_row.addWidget(QLabel("加速："))
        self.uni_accel_check = QCheckBox("多线程加速（aria2c，8 连接）")
        self.uni_accel_check.setObjectName("uni_accel_check")
        self.uni_accel_check.setChecked(bool(self._settings.get("accelerator", False)))
        accel_row.addWidget(self.uni_accel_check)
        accel_row.addWidget(QLabel("代理："))
        self.uni_proxy_combo = QComboBox()
        self.uni_proxy_combo.setObjectName("uni_proxy_combo")
        for label, data in (("自动检测", "auto"), ("不使用", "none"), ("手动", "manual")):
            self.uni_proxy_combo.addItem(label, data)
        _proxy_mode = str(self._settings.get("proxy_mode") or "auto")
        _proxy_index = self.uni_proxy_combo.findData(_proxy_mode)
        self.uni_proxy_combo.setCurrentIndex(_proxy_index if _proxy_index >= 0 else 0)
        accel_row.addWidget(self.uni_proxy_combo)
        self.uni_proxy_edit = QLineEdit()
        self.uni_proxy_edit.setObjectName("uni_proxy_edit")
        self.uni_proxy_edit.setText(
            str(self._settings.get("proxy_url") or app_settings.DEFAULT_PROXY_URL)
        )
        self.uni_proxy_edit.setPlaceholderText("如 http://127.0.0.1:12348 或 socks5://127.0.0.1:7891")
        self.uni_proxy_edit.setEnabled(self.uni_proxy_combo.currentData() == "manual")
        accel_row.addWidget(self.uni_proxy_edit, 1)
        layout.addLayout(accel_row)
        self.uni_proxy_combo.currentIndexChanged.connect(self._on_uni_proxy_mode_changed)

        cookie_row = QHBoxLayout()
        cookie_row.addWidget(QLabel("Cookie 浏览器："))
        self.uni_cookie_browser_combo = QComboBox()
        self.uni_cookie_browser_combo.setObjectName("uni_cookie_browser_combo")
        for label, data in (
            ("不登录", None),
            ("Chrome", "chrome"),
            ("Edge", "edge"),
            ("Firefox", "firefox"),
            ("Brave", "brave"),
            ("Opera", "opera"),
            ("Vivaldi", "vivaldi"),
        ):
            self.uni_cookie_browser_combo.addItem(label, data)
        cookie_row.addWidget(self.uni_cookie_browser_combo, 1)
        cookie_row.addWidget(QLabel("Cookie 文件："))
        self.uni_cookie_file_edit = QLineEdit()
        self.uni_cookie_file_edit.setObjectName("uni_cookie_file_edit")
        self.uni_cookie_file_edit.setPlaceholderText("可选：cookies.txt 路径")
        cookie_row.addWidget(self.uni_cookie_file_edit, 1)
        self.uni_cookie_file_button = QPushButton("选择…")
        self.uni_cookie_file_button.setObjectName("uni_cookie_file_button")
        self.uni_cookie_file_button.clicked.connect(self._on_uni_cookie_file_clicked)
        cookie_row.addWidget(self.uni_cookie_file_button)
        layout.addLayout(cookie_row)

        action_row = QHBoxLayout()
        self.uni_download_button = QPushButton("下载")
        self.uni_download_button.setObjectName("uni_download_button")
        self.uni_download_button.clicked.connect(self._on_uni_download_clicked)
        action_row.addWidget(self.uni_download_button, 1)
        self.uni_cancel_button = QPushButton("取消")
        self.uni_cancel_button.setObjectName("uni_cancel_button")
        self.uni_cancel_button.setEnabled(False)
        self.uni_cancel_button.clicked.connect(self._on_uni_cancel_clicked)
        action_row.addWidget(self.uni_cancel_button, 1)
        layout.addLayout(action_row)

        self.uni_progress_bar = QProgressBar()
        self.uni_progress_bar.setObjectName("uni_progress_bar")
        self.uni_progress_bar.setRange(0, 100)
        self.uni_progress_bar.setValue(0)
        layout.addWidget(self.uni_progress_bar)

        uni_progress_text_row = QHBoxLayout()
        self.uni_stage_label = QLabel("就绪")
        self.uni_stage_label.setObjectName("uni_stage_label")
        self.uni_percent_label = QLabel("—")
        self.uni_percent_label.setObjectName("uni_percent_label")
        self.uni_speed_label = QLabel("—")
        self.uni_speed_label.setObjectName("uni_speed_label")
        uni_progress_text_row.addWidget(self.uni_stage_label, 2)
        uni_progress_text_row.addWidget(self.uni_percent_label)
        uni_progress_text_row.addWidget(self.uni_speed_label)
        layout.addLayout(uni_progress_text_row)

        self.uni_meta_label = QLabel("尚未解析")
        self.uni_meta_label.setObjectName("uni_meta_label")
        self.uni_meta_label.setWordWrap(True)
        layout.addWidget(self.uni_meta_label)

        layout.addWidget(QLabel("状态日志："))
        self.uni_status_log = QPlainTextEdit()
        self.uni_status_log.setObjectName("uni_status_log")
        self.uni_status_log.setReadOnly(True)
        self.uni_status_log.setMaximumBlockCount(2000)
        layout.addWidget(self.uni_status_log, 1)

        self.uni_compliance_label = QLabel(UNI_COMPLIANCE_TEXT)
        self.uni_compliance_label.setObjectName("uni_compliance_label")
        self.uni_compliance_label.setWordWrap(True)
        self.uni_compliance_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.uni_compliance_label)

        self.mode_tabs.addTab(tab, "万能下载")

    def _build_pack_tab(self):
        tab = QWidget()
        tab.setObjectName("pack_tab")
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("页面链接："))
        self.pack_input_edit = QLineEdit()
        self.pack_input_edit.setObjectName("pack_input_edit")
        self.pack_input_edit.setPlaceholderText("粘贴页面 URL（如相册/文章页），解析页面内的媒体清单")
        self.pack_input_edit.returnPressed.connect(self._on_pack_parse_clicked)
        self.pack_input_edit.textChanged.connect(self._on_pack_input_changed)
        input_row.addWidget(self.pack_input_edit, 1)
        self.pack_parse_button = QPushButton("解析页面")
        self.pack_parse_button.setObjectName("pack_parse_button")
        self.pack_parse_button.clicked.connect(self._on_pack_parse_clicked)
        input_row.addWidget(self.pack_parse_button)
        layout.addLayout(input_row)

        self.pack_meta_label = QLabel("尚未解析")
        self.pack_meta_label.setObjectName("pack_meta_label")
        self.pack_meta_label.setWordWrap(True)
        layout.addWidget(self.pack_meta_label)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("保存到："))
        self.pack_save_dir_edit = QLineEdit(str(self._settings.get("pack_save_dir") or _default_save_dir()))
        self.pack_save_dir_edit.setObjectName("pack_save_dir_edit")
        self.pack_save_dir_edit.setReadOnly(True)
        save_row.addWidget(self.pack_save_dir_edit, 1)
        self.pack_browse_button = QPushButton("选择…")
        self.pack_browse_button.setObjectName("pack_browse_button")
        self.pack_browse_button.clicked.connect(self._on_pack_browse_clicked)
        save_row.addWidget(self.pack_browse_button)
        layout.addLayout(save_row)

        cookie_row = QHBoxLayout()
        cookie_row.addWidget(QLabel("Cookie 文件："))
        self.pack_cookie_file_edit = QLineEdit()
        self.pack_cookie_file_edit.setObjectName("pack_cookie_file_edit")
        self.pack_cookie_file_edit.setPlaceholderText("可选：cookies.txt 路径")
        cookie_row.addWidget(self.pack_cookie_file_edit, 1)
        self.pack_cookie_file_button = QPushButton("选择…")
        self.pack_cookie_file_button.setObjectName("pack_cookie_file_button")
        self.pack_cookie_file_button.clicked.connect(self._on_pack_cookie_file_clicked)
        cookie_row.addWidget(self.pack_cookie_file_button)
        layout.addLayout(cookie_row)

        proxy_row = QHBoxLayout()
        proxy_row.addWidget(QLabel("代理："))
        self.pack_proxy_combo = QComboBox()
        self.pack_proxy_combo.setObjectName("pack_proxy_combo")
        for label, data in (("自动检测", "auto"), ("不使用", "none"), ("手动", "manual")):
            self.pack_proxy_combo.addItem(label, data)
        _pack_proxy_mode = str(self._settings.get("proxy_mode") or "auto")
        _pack_proxy_index = self.pack_proxy_combo.findData(_pack_proxy_mode)
        self.pack_proxy_combo.setCurrentIndex(_pack_proxy_index if _pack_proxy_index >= 0 else 0)
        proxy_row.addWidget(self.pack_proxy_combo)
        self.pack_proxy_edit = QLineEdit()
        self.pack_proxy_edit.setObjectName("pack_proxy_edit")
        self.pack_proxy_edit.setText(
            str(self._settings.get("proxy_url") or app_settings.DEFAULT_PROXY_URL)
        )
        self.pack_proxy_edit.setPlaceholderText("如 http://127.0.0.1:12348 或 socks5://127.0.0.1:7891")
        self.pack_proxy_edit.setEnabled(self.pack_proxy_combo.currentData() == "manual")
        proxy_row.addWidget(self.pack_proxy_edit, 1)
        layout.addLayout(proxy_row)
        self.pack_proxy_combo.currentIndexChanged.connect(self._on_pack_proxy_mode_changed)
        self.pack_proxy_edit.textChanged.connect(self._on_pack_proxy_text_changed)

        action_row = QHBoxLayout()
        self.pack_start_button = QPushButton("开始打包")
        self.pack_start_button.setObjectName("pack_start_button")
        self.pack_start_button.setEnabled(False)
        self.pack_start_button.clicked.connect(self._on_pack_start_clicked)
        action_row.addWidget(self.pack_start_button, 1)
        self.pack_cancel_button = QPushButton("取消")
        self.pack_cancel_button.setObjectName("pack_cancel_button")
        self.pack_cancel_button.setEnabled(False)
        self.pack_cancel_button.clicked.connect(self._on_pack_cancel_clicked)
        action_row.addWidget(self.pack_cancel_button, 1)
        layout.addLayout(action_row)

        self.pack_progress_bar = QProgressBar()
        self.pack_progress_bar.setObjectName("pack_progress_bar")
        self.pack_progress_bar.setRange(0, 100)
        self.pack_progress_bar.setValue(0)
        layout.addWidget(self.pack_progress_bar)

        pack_progress_text_row = QHBoxLayout()
        self.pack_stage_label = QLabel("就绪")
        self.pack_stage_label.setObjectName("pack_stage_label")
        self.pack_percent_label = QLabel("—")
        self.pack_percent_label.setObjectName("pack_percent_label")
        self.pack_speed_label = QLabel("—")
        self.pack_speed_label.setObjectName("pack_speed_label")
        pack_progress_text_row.addWidget(self.pack_stage_label, 2)
        pack_progress_text_row.addWidget(self.pack_percent_label)
        pack_progress_text_row.addWidget(self.pack_speed_label)
        layout.addLayout(pack_progress_text_row)

        layout.addWidget(QLabel("状态日志："))
        self.pack_status_log = QPlainTextEdit()
        self.pack_status_log.setObjectName("pack_status_log")
        self.pack_status_log.setReadOnly(True)
        self.pack_status_log.setMaximumBlockCount(2000)
        layout.addWidget(self.pack_status_log, 1)

        self.pack_compliance_label = QLabel(PACK_COMPLIANCE_TEXT)
        self.pack_compliance_label.setObjectName("pack_compliance_label")
        self.pack_compliance_label.setWordWrap(True)
        self.pack_compliance_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.pack_compliance_label)

        self.mode_tabs.addTab(tab, "视图打包")

    def _build_tg_tab(self):
        tab = QWidget()
        tab.setObjectName("tg_tab")
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        api_row = QHBoxLayout()
        api_row.addWidget(QLabel("API ID："))
        self.tg_api_id_edit = QLineEdit(str(self._settings.get("tg_api_id") or ""))
        self.tg_api_id_edit.setObjectName("tg_api_id_edit")
        self.tg_api_id_edit.setPlaceholderText("API ID（数字）")
        api_row.addWidget(self.tg_api_id_edit, 1)
        api_row.addWidget(QLabel("API Hash："))
        self.tg_api_hash_edit = QLineEdit(str(self._settings.get("tg_api_hash") or ""))
        self.tg_api_hash_edit.setObjectName("tg_api_hash_edit")
        self.tg_api_hash_edit.setPlaceholderText("API Hash")
        api_row.addWidget(self.tg_api_hash_edit, 2)
        layout.addLayout(api_row)

        no_save_row = QHBoxLayout()
        self.tg_no_save_check = QCheckBox("不保存 API 凭据（仅本次运行）")
        self.tg_no_save_check.setObjectName("tg_no_save_check")
        self.tg_no_save_check.setChecked(bool(self._settings.get("tg_no_save_credentials", False)))
        self.tg_no_save_check.toggled.connect(self._on_tg_no_save_toggled)
        no_save_row.addWidget(self.tg_no_save_check)
        no_save_row.addStretch(1)
        layout.addLayout(no_save_row)

        login_row = QHBoxLayout()
        self.tg_login_button = QPushButton("扫码登录")
        self.tg_login_button.setObjectName("tg_login_button")
        self.tg_login_button.clicked.connect(self._on_tg_login_clicked)
        login_row.addWidget(self.tg_login_button)
        self.tg_logout_button = QPushButton("退出登录")
        self.tg_logout_button.setObjectName("tg_logout_button")
        self.tg_logout_button.clicked.connect(self._on_tg_logout_clicked)
        login_row.addWidget(self.tg_logout_button)
        self.tg_status_label = QLabel("未登录")
        self.tg_status_label.setObjectName("tg_status_label")
        login_row.addWidget(self.tg_status_label)
        self.tg_password_edit = QLineEdit()
        self.tg_password_edit.setObjectName("tg_password_edit")
        self.tg_password_edit.setEchoMode(QLineEdit.Password)
        self.tg_password_edit.setPlaceholderText("两步验证密码（可选）")
        login_row.addWidget(self.tg_password_edit, 1)
        layout.addLayout(login_row)

        middle_row = QHBoxLayout()
        self.tg_qr_label = QLabel("点击“扫码登录”获取二维码")
        self.tg_qr_label.setObjectName("tg_qr_label")
        self.tg_qr_label.setMinimumSize(240, 240)
        self.tg_qr_label.setAlignment(Qt.AlignCenter)
        self.tg_qr_label.setWordWrap(True)
        self.tg_qr_label.setStyleSheet("background: white; border: 1px solid #e6c8d4;")
        middle_row.addWidget(self.tg_qr_label)

        right_column = QVBoxLayout()
        right_column.setSpacing(6)
        channel_row = QHBoxLayout()
        channel_row.addWidget(QLabel("频道："))
        self.tg_channel_edit = QLineEdit(str(self._settings.get("tg_channel") or ""))
        self.tg_channel_edit.setObjectName("tg_channel_edit")
        self.tg_channel_edit.setPlaceholderText("@频道 或 t.me 链接")
        self.tg_channel_edit.returnPressed.connect(self._on_tg_list_clicked)
        channel_row.addWidget(self.tg_channel_edit, 1)
        self.tg_list_button = QPushButton("预览频道")
        self.tg_list_button.setObjectName("tg_list_button")
        self.tg_list_button.clicked.connect(self._on_tg_list_clicked)
        channel_row.addWidget(self.tg_list_button)
        right_column.addLayout(channel_row)

        self.tg_media_info_label = QLabel("尚未预览")
        self.tg_media_info_label.setObjectName("tg_media_info_label")
        self.tg_media_info_label.setWordWrap(True)
        right_column.addWidget(self.tg_media_info_label)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("类型："))
        self.tg_types_combo = QComboBox()
        self.tg_types_combo.setObjectName("tg_types_combo")
        for label, data in (("全部媒体", None), ("图片", "photo"), ("视频", "video"),
                            ("文件", "document"), ("音频", "audio")):
            self.tg_types_combo.addItem(label, data)
        _tg_types_saved = str(self._settings.get("tg_types") or "")
        _tg_types_index = 0
        for _index in range(self.tg_types_combo.count()):
            if str(self.tg_types_combo.itemData(_index) or "") == _tg_types_saved:
                _tg_types_index = _index
                break
        self.tg_types_combo.setCurrentIndex(_tg_types_index)
        filter_row.addWidget(self.tg_types_combo)
        filter_row.addWidget(QLabel("条数："))
        self.tg_limit_spin = QSpinBox()
        self.tg_limit_spin.setObjectName("tg_limit_spin")
        self.tg_limit_spin.setRange(0, 1000000)
        try:
            _tg_limit_saved = int(self._settings.get("tg_limit") or 0)
        except (TypeError, ValueError):
            _tg_limit_saved = 0
        self.tg_limit_spin.setValue(_tg_limit_saved)
        self.tg_limit_spin.setSuffix(" 条（0=全部）")
        filter_row.addWidget(self.tg_limit_spin)
        filter_row.addStretch(1)
        right_column.addLayout(filter_row)
        right_column.addStretch(1)
        middle_row.addLayout(right_column, 1)
        layout.addLayout(middle_row)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("保存到："))
        self.tg_save_dir_edit = QLineEdit(
            str(self._settings.get("tg_save_dir") or _default_save_dir())
        )
        self.tg_save_dir_edit.setObjectName("tg_save_dir_edit")
        self.tg_save_dir_edit.setReadOnly(True)
        save_row.addWidget(self.tg_save_dir_edit, 1)
        self.tg_browse_button = QPushButton("选择…")
        self.tg_browse_button.setObjectName("tg_browse_button")
        self.tg_browse_button.clicked.connect(self._on_tg_browse_clicked)
        save_row.addWidget(self.tg_browse_button)
        layout.addLayout(save_row)

        action_row = QHBoxLayout()
        self.tg_start_button = QPushButton("开始下载")
        self.tg_start_button.setObjectName("tg_start_button")
        self.tg_start_button.clicked.connect(self._on_tg_start_clicked)
        action_row.addWidget(self.tg_start_button, 1)
        self.tg_cancel_button = QPushButton("取消")
        self.tg_cancel_button.setObjectName("tg_cancel_button")
        self.tg_cancel_button.setEnabled(False)
        self.tg_cancel_button.clicked.connect(self._on_tg_cancel_clicked)
        action_row.addWidget(self.tg_cancel_button, 1)
        layout.addLayout(action_row)

        self.tg_progress_bar = QProgressBar()
        self.tg_progress_bar.setObjectName("tg_progress_bar")
        self.tg_progress_bar.setRange(0, 100)
        self.tg_progress_bar.setValue(0)
        layout.addWidget(self.tg_progress_bar)

        tg_progress_text_row = QHBoxLayout()
        self.tg_stage_label = QLabel("就绪")
        self.tg_stage_label.setObjectName("tg_stage_label")
        self.tg_percent_label = QLabel("—")
        self.tg_percent_label.setObjectName("tg_percent_label")
        self.tg_speed_label = QLabel("—")
        self.tg_speed_label.setObjectName("tg_speed_label")
        tg_progress_text_row.addWidget(self.tg_stage_label, 2)
        tg_progress_text_row.addWidget(self.tg_percent_label)
        tg_progress_text_row.addWidget(self.tg_speed_label)
        layout.addLayout(tg_progress_text_row)

        layout.addWidget(QLabel("状态日志："))
        self.tg_status_log = QPlainTextEdit()
        self.tg_status_log.setObjectName("tg_status_log")
        self.tg_status_log.setReadOnly(True)
        self.tg_status_log.setMaximumBlockCount(2000)
        layout.addWidget(self.tg_status_log, 1)

        self.tg_compliance_label = QLabel(TG_COMPLIANCE_TEXT)
        self.tg_compliance_label.setObjectName("tg_compliance_label")
        self.tg_compliance_label.setWordWrap(True)
        self.tg_compliance_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.tg_compliance_label)

        self.mode_tabs.addTab(tab, "飞机模式")

    # ---------- 主题 ----------

    def _apply_theme(self, name):
        app = QApplication.instance()
        if app is not None and apply_theme(app, name):
            self._current_theme = name
            self._persist_settings()
            self._log(f"主题已切换：{name}")

    def _connect_settings_signals(self):
        self.save_dir_edit.textChanged.connect(self._persist_settings)
        self.uni_save_dir_edit.textChanged.connect(self._persist_settings)
        self.pack_save_dir_edit.textChanged.connect(self._persist_settings)
        self.uni_proxy_edit.textChanged.connect(self._on_uni_proxy_text_changed)
        self.uni_accel_check.toggled.connect(self._persist_settings)
        self.tg_api_id_edit.textChanged.connect(self._persist_settings)
        self.tg_api_hash_edit.textChanged.connect(self._persist_settings)
        self.tg_channel_edit.textChanged.connect(self._persist_settings)
        self.tg_save_dir_edit.textChanged.connect(self._persist_settings)
        self.tg_limit_spin.valueChanged.connect(self._persist_settings)
        self.tg_types_combo.currentIndexChanged.connect(self._persist_settings)

    def _persist_settings(self, *_args):
        self._settings.update({
            "bili_save_dir": self.save_dir_edit.text().strip(),
            "uni_save_dir": self.uni_save_dir_edit.text().strip(),
            "pack_save_dir": self.pack_save_dir_edit.text().strip(),
            "proxy_mode": self.uni_proxy_combo.currentData() or "auto",
            "proxy_url": self.uni_proxy_edit.text().strip(),
            "accelerator": self.uni_accel_check.isChecked(),
            "theme": self._current_theme,
            "tg_api_id": "" if self.tg_no_save_check.isChecked() else self.tg_api_id_edit.text().strip(),
            "tg_api_hash": "" if self.tg_no_save_check.isChecked() else self.tg_api_hash_edit.text().strip(),
            "tg_no_save_credentials": self.tg_no_save_check.isChecked(),
            "tg_channel": self.tg_channel_edit.text().strip(),
            "tg_save_dir": self.tg_save_dir_edit.text().strip(),
            "tg_limit": int(self.tg_limit_spin.value()),
            "tg_types": str(self.tg_types_combo.currentData() or ""),
        })
        app_settings.save_settings(self._settings)

    def _sync_proxy_widgets(self, src_combo, src_edit, dst_combo, dst_edit):
        """万能页与打包页共用 proxy_mode/proxy_url：一侧修改后同步另一侧。"""
        if self._syncing_proxy:
            return
        self._syncing_proxy = True
        try:
            index = dst_combo.findData(src_combo.currentData())
            if index >= 0 and index != dst_combo.currentIndex():
                dst_combo.setCurrentIndex(index)
            if dst_edit.text() != src_edit.text():
                dst_edit.setText(src_edit.text())
        finally:
            self._syncing_proxy = False
        self._persist_settings()

    # ---------- B站事件处理 ----------

    def _on_download_clicked(self):
        if not _CORE_READY:
            notify.show_error(self, "核心模块 bili_dl 未就绪，暂无法下载。")
            return
        text = self.input_edit.text().strip()
        if not text:
            notify.show_error(self, "请输入视频链接或 BV 号")
            return
        if self._parsing or (self._worker is not None and self._worker.isRunning()):
            return
        if self._meta is not None and text == self._parsed_text:
            self._start_download()
        else:
            self._start_parse(text)

    def _start_parse(self, text):
        self._parsing = True
        self._meta = None
        self._parsed_text = None
        self._worker = None
        self.download_button.setEnabled(False)
        self.download_button.setText("解析中…")
        self.quality_combo.setEnabled(False)
        self.stage_label.setText("解析中")
        self.percent_label.setText("—")
        self.speed_label.setText("—")
        self._log(f"正在解析：{text}")
        worker = ParseWorker(
            parse_input,
            list_qualities,
            text,
            cookie=self._cookie,
            error_types=(InputError, ApiError, DownloadError),
            parent=self,
        )
        worker.parsed.connect(lambda meta, qualities, t=text: self._on_parsed(t, meta, qualities))
        worker.failed.connect(self._on_parse_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_parsed(self, text, meta, qualities):
        self._parsing = False
        self._worker = None
        self._meta = meta
        self._parsed_text = text
        self.quality_combo.clear()
        self.quality_combo.addItem(DEFAULT_QUALITY_LABEL, "max")
        for quality in qualities:
            self.quality_combo.addItem(str(quality.desc), int(quality.qn))
        self.quality_combo.setEnabled(True)
        self.download_button.setEnabled(True)
        self.download_button.setText("下载")
        self.stage_label.setText("已就绪")
        duration = _format_duration(getattr(meta, "duration", 0))
        self._log(f"解析成功：{meta.title}（UP主：{meta.owner_name}，时长 {duration}），请选择画质后再次点击下载")
        self._log(f"画质列表：最高可用 > {' > '.join(str(q.desc) for q in qualities)}")

    def _on_parse_failed(self, message):
        self._parsing = False
        self._worker = None
        self._meta = None
        self._parsed_text = None
        self.quality_combo.clear()
        self.quality_combo.setEnabled(False)
        self.download_button.setEnabled(True)
        self.download_button.setText("下载")
        self.stage_label.setText("解析失败")
        self._log(f"解析失败：{message}")
        notify.show_error(self, message)

    def _start_download(self):
        quality = self.quality_combo.currentData()
        save_dir = self.save_dir_edit.text().strip() or str(Path.home())
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._reset_progress()
        self._last_stage = None
        self._speed_anchor_bytes = 0
        self._speed_anchor_time = 0.0
        self._log(f"开始下载：{self._meta.title}（画质：{self.quality_combo.currentText()}）→ {save_dir}")
        worker = DownloadWorker(
            download_video,
            meta=self._meta,
            cookie=self._cookie,
            quality=quality,
            save_dir=save_dir,
            cancel_error_type=CancelledError,
            error_types=(InputError, ApiError, DownloadError),
            parent=self,
        )
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_download_finished)
        worker.failed.connect(self._on_download_failed)
        worker.cancelled.connect(self._on_download_cancelled)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_progress(self, stage, downloaded, total):
        if stage != self._last_stage:
            self._last_stage = stage
            self._log(f"阶段：{_STAGE_TEXT.get(stage, stage)}")
            self._speed_anchor_bytes = downloaded
            self._speed_anchor_time = time.monotonic()
        self.stage_label.setText(_STAGE_TEXT.get(stage, stage))
        if stage == "done":
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.percent_label.setText("100%")
            self.speed_label.setText("—")
            return
        if stage in ("video", "audio") and total > 0:
            self.progress_bar.setRange(0, 100)
            percent = max(0, min(100, int(downloaded * 100 // total)))
            self.progress_bar.setValue(percent)
            self.percent_label.setText(f"{percent}%")
            now = time.monotonic()
            dt = now - self._speed_anchor_time
            if dt >= 0.5:
                speed = max(0.0, (downloaded - self._speed_anchor_bytes) / dt)
                self.speed_label.setText(f"{_format_bytes(int(speed))}/s")
                self._speed_anchor_bytes = downloaded
                self._speed_anchor_time = now
        else:
            self.progress_bar.setRange(0, 0)
            self.percent_label.setText("—")
            self.speed_label.setText("—")

    def _on_download_finished(self, path_str):
        self._worker = None
        path = Path(path_str)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.stage_label.setText("完成")
        self.percent_label.setText("100%")
        self.speed_label.setText("—")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._log(f"下载完成：{path}")
        notify.show_success(self, "下载完成", f"视频已保存到：{path}", folder=path.parent)

    def _on_download_failed(self, message):
        self._worker = None
        self.progress_bar.setRange(0, 100)
        self.stage_label.setText("下载失败")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._log(f"下载失败：{message}")
        notify.show_error(self, message)

    def _on_download_cancelled(self):
        self._worker = None
        self.progress_bar.setRange(0, 100)
        self.stage_label.setText("已取消")
        self.percent_label.setText("—")
        self.speed_label.setText("—")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._log("已取消下载")
        notify.show_cancelled(self)

    def _on_cancel_clicked(self):
        worker = self._worker
        if worker is not None and worker.isRunning():
            self._log("正在取消下载…")
            worker.request_cancel()
            self.cancel_button.setEnabled(False)

    def _on_browse_clicked(self):
        current = self.save_dir_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", current)
        if folder:
            self.save_dir_edit.setText(folder)
            self._log(f"保存目录已切换：{folder}")

    def _open_cookie_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Cookie 设置")
        dlg.setModal(True)
        dlg.resize(560, 360)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("粘贴完整 Cookie 字符串（可选，用于解锁高画质）："))
        editor = QPlainTextEdit()
        editor.setObjectName("cookie_edit")
        editor.setPlaceholderText("name1=value1; name2=value2; …")
        if self._cookie:
            editor.setPlainText(self._cookie)
        layout.addWidget(editor)
        note = QLabel("Cookie 仅本次运行有效，用于解锁高画质，程序不会保存")
        note.setObjectName("cookie_note")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.Accepted:
            cookie = editor.toPlainText().strip()
            if cookie:
                self._cookie = cookie
                self._log("已设置 Cookie（仅本次运行有效，程序不会保存）")
            else:
                self._cookie = None
                self._log("已清除 Cookie")

    # ---------- 万能下载事件处理 ----------

    def _on_uni_proxy_mode_changed(self, _index=None):
        """仅“手动”模式允许编辑代理地址。"""
        self.uni_proxy_edit.setEnabled(self.uni_proxy_combo.currentData() == "manual")
        self._sync_proxy_widgets(self.uni_proxy_combo, self.uni_proxy_edit,
                                 self.pack_proxy_combo, self.pack_proxy_edit)

    def _on_uni_proxy_text_changed(self, _text=None):
        self._sync_proxy_widgets(self.uni_proxy_combo, self.uni_proxy_edit,
                                 self.pack_proxy_combo, self.pack_proxy_edit)

    def _uni_proxy_value(self):
        """按代理下拉框算出本次请求使用的代理；None 表示走系统网络。"""
        mode = self.uni_proxy_combo.currentData()
        if mode == "manual":
            return self.uni_proxy_edit.text().strip() or None
        if mode == "none":
            return None
        proxy = _uni_detect_local_proxy()
        if proxy is None:
            self._uni_log("未检测到本地代理，使用系统网络")
            return None
        self._uni_log(f"已检测到本地代理：{proxy}")
        return proxy

    def _uni_cookie_dict(self):
        file_path = self.uni_cookie_file_edit.text().strip()
        if file_path:
            return {"cookiefile": file_path}
        browser = self.uni_cookie_browser_combo.currentData()
        if browser:
            return {"browser": browser}
        return None

    def _on_uni_input_changed(self, text):
        """输入变化后旧解析结果立即失效，避免沿用上一个链接的元数据。"""
        if text.strip() == (self._uni_parsed_text or ""):
            return
        if self._uni_meta is not None:
            self._uni_meta = None
            self.uni_meta_label.setText("尚未解析")
            self.uni_download_button.setEnabled(False)

    def _on_uni_parse_clicked(self):
        if not _UNI_READY:
            notify.show_error(self, "万能下载模块 uni_dl 未就绪，暂无法解析。")
            return
        text = self.uni_input_edit.text().strip()
        if not text:
            notify.show_error(self, "请输入视频链接")
            return
        if self._uni_parsing or (self._uni_worker is not None and self._uni_worker.isRunning()):
            self._uni_log("请等待当前解析/下载任务结束后再解析")
            return
        proxy = self._uni_proxy_value()
        self._uni_parse_text = text
        self._uni_parsing = True
        self._uni_meta = None
        self._uni_worker = None
        self.uni_parse_button.setEnabled(False)
        self.uni_parse_button.setText("解析中…")
        self.uni_download_button.setEnabled(False)
        self.uni_stage_label.setText("解析中")
        self.uni_percent_label.setText("—")
        self.uni_speed_label.setText("—")
        self.uni_meta_label.setText("解析中…")
        self._uni_log(f"正在解析：{text}")
        worker = UniversalParseWorker(
            uni_parse_input,
            text,
            cookie=self._uni_cookie_dict(),
            proxy=proxy,
            error_types=(UniInputError, UniDownloadError),
            parent=self,
        )
        worker.parsed.connect(self._on_uni_parsed)
        worker.failed.connect(self._on_uni_parse_failed)
        worker.finished.connect(worker.deleteLater)
        self._uni_worker = worker
        worker.start()

    def _on_uni_parsed(self, meta):
        self._uni_parsing = False
        self._uni_worker = None
        self._uni_meta = meta
        self._uni_parsed_text = self._uni_parse_text
        matched = self.uni_input_edit.text().strip() == (self._uni_parsed_text or "")
        title = getattr(meta, "title", "") or ""
        uploader = getattr(meta, "uploader", "") or ""
        duration = _format_duration(getattr(meta, "duration", 0))
        entry_count = getattr(meta, "entry_count", 0)
        is_playlist = bool(getattr(meta, "is_playlist", False))
        playlist_note = "（播放列表）" if is_playlist else ""
        self.uni_meta_label.setText(
            f"标题：{title}\nUP主：{uploader}\n时长：{duration}\n条目数：{entry_count}{playlist_note}"
        )
        self.uni_parse_button.setEnabled(True)
        self.uni_parse_button.setText("解析")
        self.uni_download_button.setEnabled(matched)
        self.uni_stage_label.setText("已就绪")
        self._uni_log(f"解析成功：{title}（UP主：{uploader}，时长 {duration}，条目数 {entry_count}）")
        if not matched:
            self._uni_log("输入链接已更改，请重新点击“解析”后再下载")

    def _on_uni_parse_failed(self, message):
        self._uni_parsing = False
        self._uni_worker = None
        self._uni_meta = None
        self._uni_parsed_text = None
        self.uni_parse_button.setEnabled(True)
        self.uni_parse_button.setText("解析")
        self.uni_download_button.setEnabled(False)
        self.uni_stage_label.setText("解析失败")
        self.uni_meta_label.setText("解析失败")
        self._uni_log(f"解析失败：{message}")
        notify.show_error(self, message)

    def _on_uni_download_clicked(self):
        if not _UNI_READY:
            notify.show_error(self, "万能下载模块 uni_dl 未就绪，暂无法下载。")
            return
        meta = self._uni_meta
        current_text = self.uni_input_edit.text().strip()
        if meta is None or current_text != (self._uni_parsed_text or ""):
            notify.show_error(self, "链接已更改，请先点击“解析”解析当前链接")
            return
        if self._uni_parsing or (self._uni_worker is not None and self._uni_worker.isRunning()):
            self._uni_log("请等待当前任务结束后再下载")
            return
        proxy = self._uni_proxy_value()
        accelerator = self.uni_accel_check.isChecked()
        custom = self.uni_format_edit.text().strip()
        format_sel = custom if custom else self.uni_quality_combo.currentData()
        save_dir = self.uni_save_dir_edit.text().strip() or str(Path.home())
        self.uni_download_button.setEnabled(False)
        self.uni_cancel_button.setEnabled(True)
        self._uni_reset_progress()
        self._uni_last_stage = None
        self._uni_speed_anchor_bytes = 0
        self._uni_speed_anchor_time = 0.0
        self._uni_log(
            f"开始下载：{getattr(meta, 'title', '')}（格式：{format_sel}，"
            f"代理：{proxy or '系统网络'}，加速：{'开' if accelerator else '关'}）→ {save_dir}"
        )
        worker = UniversalDownloadWorker(
            uni_download_video,
            meta=meta,
            format_sel=format_sel,
            save_dir=save_dir,
            cookie=self._uni_cookie_dict(),
            proxy=proxy,
            accelerator=accelerator,
            cancel_error_type=UniCancelledError,
            error_types=(UniInputError, UniDownloadError),
            parent=self,
        )
        worker.progress.connect(self._on_uni_progress)
        worker.finished_ok.connect(self._on_uni_download_finished)
        worker.failed.connect(self._on_uni_download_failed)
        worker.cancelled.connect(self._on_uni_download_cancelled)
        worker.finished.connect(worker.deleteLater)
        self._uni_worker = worker
        worker.start()

    def _on_uni_progress(self, stage, downloaded, total):
        if stage != self._uni_last_stage:
            self._uni_last_stage = stage
            self._uni_log(f"阶段：{_STAGE_TEXT.get(stage, stage)}")
            self._uni_speed_anchor_bytes = downloaded
            self._uni_speed_anchor_time = time.monotonic()
        self.uni_stage_label.setText(_STAGE_TEXT.get(stage, stage))
        if stage == "done":
            self.uni_progress_bar.setRange(0, 100)
            self.uni_progress_bar.setValue(100)
            self.uni_percent_label.setText("100%")
            self.uni_speed_label.setText("—")
            return
        if stage == "video" and total > 0:
            self.uni_progress_bar.setRange(0, 100)
            percent = max(0, min(100, int(downloaded * 100 // total)))
            self.uni_progress_bar.setValue(percent)
            self.uni_percent_label.setText(f"{percent}%")
            now = time.monotonic()
            dt = now - self._uni_speed_anchor_time
            if dt >= 0.5:
                speed = max(0.0, (downloaded - self._uni_speed_anchor_bytes) / dt)
                self.uni_speed_label.setText(f"{_format_bytes(int(speed))}/s")
                self._uni_speed_anchor_bytes = downloaded
                self._uni_speed_anchor_time = now
        else:
            self.uni_progress_bar.setRange(0, 0)
            self.uni_percent_label.setText("—")
            self.uni_speed_label.setText("—")

    def _on_uni_download_finished(self, paths):
        self._uni_worker = None
        paths = [str(p) for p in (paths or [])]
        self.uni_progress_bar.setRange(0, 100)
        self.uni_progress_bar.setValue(100)
        self.uni_stage_label.setText("完成")
        self.uni_percent_label.setText("100%")
        self.uni_speed_label.setText("—")
        self.uni_download_button.setEnabled(True)
        self.uni_cancel_button.setEnabled(False)
        if not paths:
            self._uni_log("下载完成但未返回任何文件路径")
            notify.show_error(self, "下载完成但未返回任何文件路径")
            return
        self._uni_log(f"下载完成，共 {len(paths)} 个文件：")
        for path in paths:
            self._uni_log(f"  {path}")
        if getattr(self._uni_meta, "is_playlist", False):
            self._uni_log("播放列表下载完成（逐项路径见上）")
        folder = Path(paths[0]).parent
        message = "已保存：\n" + "\n".join(paths)
        notify.show_success(self, "下载完成", message, folder=folder)

    def _on_uni_download_failed(self, message):
        self._uni_worker = None
        self.uni_progress_bar.setRange(0, 100)
        self.uni_stage_label.setText("下载失败")
        self.uni_download_button.setEnabled(True)
        self.uni_cancel_button.setEnabled(False)
        self._uni_log(f"下载失败：{message}")
        notify.show_error(self, message)

    def _on_uni_download_cancelled(self):
        self._uni_worker = None
        self.uni_progress_bar.setRange(0, 100)
        self.uni_stage_label.setText("已取消")
        self.uni_percent_label.setText("—")
        self.uni_speed_label.setText("—")
        self.uni_download_button.setEnabled(True)
        self.uni_cancel_button.setEnabled(False)
        self._uni_log("已取消下载")
        notify.show_cancelled(self)

    def _on_uni_cancel_clicked(self):
        worker = self._uni_worker
        if worker is not None and worker.isRunning():
            self._uni_log("正在取消下载…")
            worker.request_cancel()
            self.uni_cancel_button.setEnabled(False)

    def _on_uni_browse_clicked(self):
        current = self.uni_save_dir_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", current)
        if folder:
            self.uni_save_dir_edit.setText(folder)
            self._uni_log(f"保存目录已切换：{folder}")

    def _on_uni_cookie_file_clicked(self):
        current = self.uni_cookie_file_edit.text().strip()
        start_dir = str(Path(current).parent) if current else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 cookies.txt", start_dir, "Cookies 文本 (*.txt);;所有文件 (*.*)"
        )
        if path:
            self.uni_cookie_file_edit.setText(path)
            self._uni_log(f"Cookie 文件已选择：{path}")

    # ---------- 视图打包事件处理 ----------

    def _on_pack_proxy_mode_changed(self, _index=None):
        """仅“手动”模式允许编辑代理地址；代理设置与万能页共用。"""
        self.pack_proxy_edit.setEnabled(self.pack_proxy_combo.currentData() == "manual")
        self._sync_proxy_widgets(self.pack_proxy_combo, self.pack_proxy_edit,
                                 self.uni_proxy_combo, self.uni_proxy_edit)

    def _on_pack_proxy_text_changed(self, _text=None):
        self._sync_proxy_widgets(self.pack_proxy_combo, self.pack_proxy_edit,
                                 self.uni_proxy_combo, self.uni_proxy_edit)

    def _pack_proxy_value(self):
        """按打包页代理下拉框算出本次请求使用的代理；None 表示走系统网络。"""
        mode = self.pack_proxy_combo.currentData()
        if mode == "manual":
            return self.pack_proxy_edit.text().strip() or None
        if mode == "none":
            return None
        proxy = _pack_detect_local_proxy()
        if proxy is None:
            self._pack_log("未检测到本地代理，使用系统网络")
            return None
        self._pack_log(f"已检测到本地代理：{proxy}")
        return proxy

    def _pack_cookie_value(self):
        """page_dl 的 cookie 参数：None 或 {"cookiefile": cookies.txt 路径}。"""
        path = self.pack_cookie_file_edit.text().strip()
        return {"cookiefile": path} if path else None

    def _on_pack_input_changed(self, text):
        """输入变化后旧解析结果立即失效，避免打包上一个链接。"""
        if text.strip() == (self._pack_parsed_text or ""):
            return
        if self._pack_bundle is not None:
            self._pack_bundle = None
            self.pack_meta_label.setText("尚未解析")
            self.pack_start_button.setEnabled(False)

    def _pack_can_start(self):
        """当前输入是否仍对应当前解析结果。"""
        return (self._pack_bundle is not None
                and self.pack_input_edit.text().strip() == (self._pack_parsed_text or ""))

    def _on_pack_parse_clicked(self):
        if not _PACK_READY:
            notify.show_error(self, "视图打包模块 page_dl 未就绪，暂无法解析。")
            return
        text = self.pack_input_edit.text().strip()
        if not text:
            notify.show_error(self, "请输入页面 URL")
            return
        if self._pack_parsing or (self._pack_worker is not None and self._pack_worker.isRunning()):
            self._pack_log("请等待当前解析/打包任务结束后再解析")
            return
        proxy = self._pack_proxy_value()
        self._pack_parse_text = text
        self._pack_parsing = True
        self._pack_bundle = None
        self._pack_worker = None
        self.pack_parse_button.setEnabled(False)
        self.pack_parse_button.setText("解析中…")
        self.pack_start_button.setEnabled(False)
        self.pack_stage_label.setText("解析中")
        self.pack_percent_label.setText("—")
        self.pack_speed_label.setText("—")
        self.pack_meta_label.setText("解析中…")
        self._pack_log(f"正在解析：{text}")
        worker = PageParseWorker(
            parse_page,
            text,
            cookie=self._pack_cookie_value(),
            proxy=proxy,
            error_types=(PageInputError, PageDownloadError),
            parent=self,
        )
        worker.parsed.connect(self._on_pack_parsed)
        worker.failed.connect(self._on_pack_parse_failed)
        worker.finished.connect(worker.deleteLater)
        self._pack_worker = worker
        worker.start()

    def _on_pack_parsed(self, bundle):
        self._pack_parsing = False
        self._pack_worker = None
        self._pack_bundle = bundle
        self._pack_parsed_text = self._pack_parse_text
        matched = self.pack_input_edit.text().strip() == (self._pack_parsed_text or "")
        title = getattr(bundle, "title", "") or ""
        image = getattr(bundle, "image_count", 0)
        video = getattr(bundle, "video_count", 0)
        audio = getattr(bundle, "audio_count", 0)
        other = getattr(bundle, "other_count", 0)
        item_count = len(getattr(bundle, "items", None) or [])
        self.pack_meta_label.setText(
            f"标题：{title}\n图片：{image}\n视频：{video}\n音频：{audio}\n其他：{other}"
        )
        self.pack_parse_button.setEnabled(True)
        self.pack_parse_button.setText("解析页面")
        self.pack_start_button.setEnabled(matched and item_count > 0)
        self.pack_stage_label.setText("已就绪")
        if item_count <= 0:
            self.pack_start_button.setEnabled(False)
            self._pack_log("未找到可打包的媒体（页面可能由 JS 动态加载，或需要 Cookie/代理）")
        self._pack_log(
            f"解析成功：{title}（共 {item_count} 项：图片 {image} / 视频 {video} / "
            f"音频 {audio} / 其他 {other}）"
        )
        if not matched:
            self._pack_log("输入链接已更改，请重新点击“解析页面”后再打包")

    def _on_pack_parse_failed(self, message):
        self._pack_parsing = False
        self._pack_worker = None
        self._pack_bundle = None
        self._pack_parsed_text = None
        self.pack_parse_button.setEnabled(True)
        self.pack_parse_button.setText("解析页面")
        self.pack_start_button.setEnabled(False)
        self.pack_stage_label.setText("解析失败")
        self.pack_meta_label.setText("解析失败")
        self._pack_log(f"解析失败：{message}")
        notify.show_error(self, message)

    def _on_pack_start_clicked(self):
        if not _PACK_READY:
            notify.show_error(self, "视图打包模块 page_dl 未就绪，暂无法打包。")
            return
        if not self._pack_can_start():
            notify.show_error(self, "链接已更改，请先点击“解析页面”解析当前链接")
            return
        if self._pack_parsing or (self._pack_worker is not None and self._pack_worker.isRunning()):
            self._pack_log("请等待当前任务结束后再打包")
            return
        bundle = self._pack_bundle
        proxy = self._pack_proxy_value()
        save_dir = self.pack_save_dir_edit.text().strip() or str(Path.home())
        item_count = len(getattr(bundle, "items", None) or [])
        self.pack_start_button.setEnabled(False)
        self.pack_cancel_button.setEnabled(True)
        self._pack_reset_progress()
        self._pack_last_stage = None
        self._pack_speed_anchor_bytes = 0
        self._pack_speed_anchor_time = 0.0
        self._pack_log(
            f"开始打包：{getattr(bundle, 'title', '')}（共 {item_count} 项，"
            f"代理：{proxy or '系统网络'}）→ {save_dir}"
        )
        worker = PagePackWorker(
            pack_download_page,
            bundle,
            save_dir=save_dir,
            zip_output=True,
            proxy=proxy,
            cookie=self._pack_cookie_value(),
            cancel_error_type=PageCancelledError,
            error_types=(PageInputError, PageDownloadError),
            parent=self,
        )
        worker.progress.connect(self._on_pack_progress)
        worker.finished_ok.connect(self._on_pack_finished)
        worker.failed.connect(self._on_pack_failed)
        worker.cancelled.connect(self._on_pack_cancelled)
        worker.finished.connect(worker.deleteLater)
        self._pack_worker = worker
        worker.start()

    def _on_pack_progress(self, stage, done, total):
        if stage != self._pack_last_stage:
            self._pack_last_stage = stage
            self._pack_log(f"阶段：{_PACK_STAGE_TEXT.get(stage, stage)}")
            self._pack_speed_anchor_bytes = done
            self._pack_speed_anchor_time = time.monotonic()
        self.pack_stage_label.setText(_PACK_STAGE_TEXT.get(stage, stage))
        if stage == "done":
            self.pack_progress_bar.setRange(0, 100)
            self.pack_progress_bar.setValue(100)
            self.pack_percent_label.setText("100%")
            self.pack_speed_label.setText("—")
            return
        if stage == "download" and total > 0:
            self.pack_progress_bar.setRange(0, 100)
            percent = max(0, min(100, int(done * 100 // total)))
            self.pack_progress_bar.setValue(percent)
            self.pack_percent_label.setText(f"{percent}%")
            now = time.monotonic()
            dt = now - self._pack_speed_anchor_time
            if dt >= 0.5:
                speed = max(0.0, (done - self._pack_speed_anchor_bytes) / dt)
                self.pack_speed_label.setText(f"{_format_bytes(int(speed))}/s")
                self._pack_speed_anchor_bytes = done
                self._pack_speed_anchor_time = now
        else:
            self.pack_progress_bar.setRange(0, 0)
            self.pack_percent_label.setText("—")
            self.pack_speed_label.setText("—")

    def _on_pack_finished(self, path_str):
        self._pack_worker = None
        path = Path(path_str)
        self.pack_progress_bar.setRange(0, 100)
        self.pack_progress_bar.setValue(100)
        self.pack_stage_label.setText("完成")
        self.pack_percent_label.setText("100%")
        self.pack_speed_label.setText("—")
        self.pack_start_button.setEnabled(self._pack_can_start())
        self.pack_cancel_button.setEnabled(False)
        self._pack_log(f"打包完成：{path}")
        notify.show_success(self, "打包完成", f"视图已打包为 ZIP：{path}", folder=path.parent)

    def _on_pack_failed(self, message):
        self._pack_worker = None
        self.pack_progress_bar.setRange(0, 100)
        self.pack_stage_label.setText("打包失败")
        self.pack_start_button.setEnabled(self._pack_can_start())
        self.pack_cancel_button.setEnabled(False)
        self._pack_log(f"打包失败：{message}")
        notify.show_error(self, message)

    def _on_pack_cancelled(self):
        self._pack_worker = None
        self.pack_progress_bar.setRange(0, 100)
        self.pack_progress_bar.setValue(0)
        self.pack_stage_label.setText("已取消")
        self.pack_percent_label.setText("—")
        self.pack_speed_label.setText("—")
        self.pack_start_button.setEnabled(self._pack_can_start())
        self.pack_cancel_button.setEnabled(False)
        self._pack_log("已取消打包，临时文件已清理")
        notify.show_cancelled(self, "已取消打包")

    def _on_pack_cancel_clicked(self):
        worker = self._pack_worker
        if worker is not None and worker.isRunning():
            self._pack_log("正在取消打包…")
            worker.request_cancel()
            self.pack_cancel_button.setEnabled(False)

    def _on_pack_browse_clicked(self):
        current = self.pack_save_dir_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", current)
        if folder:
            self.pack_save_dir_edit.setText(folder)
            self._pack_log(f"保存目录已切换：{folder}")

    def _on_pack_cookie_file_clicked(self):
        current = self.pack_cookie_file_edit.text().strip()
        start_dir = str(Path(current).parent) if current else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 cookies.txt", start_dir, "Cookies 文本 (*.txt);;所有文件 (*.*)"
        )
        if path:
            self.pack_cookie_file_edit.setText(path)
            self._pack_log(f"Cookie 文件已选择：{path}")

    # ---------- 飞机模式（Telegram）事件处理 ----------

    def _on_tg_no_save_toggled(self, checked):
        if checked:
            self._tg_log("已开启“不保存 API 凭据”：本次运行结束后不会写入设置文件")
        else:
            self._tg_log("已关闭“不保存 API 凭据”：API 凭据将随设置保存")
        self._persist_settings()

    def _tg_proxy_value(self):
        """飞机模式代理：复用共用代理设置（自动检测 / 不使用 / 手动），None 表示系统网络。"""
        mode = self.uni_proxy_combo.currentData() or "auto"
        if mode == "manual":
            return self.uni_proxy_edit.text().strip() or None
        if mode == "none":
            return None
        proxy = _tg_detect_local_proxy()
        if proxy is None:
            self._tg_log("未检测到本地代理，使用系统网络")
            return None
        self._tg_log(f"已检测到本地代理：{proxy}")
        return proxy

    def _tg_config(self, require_credentials=True):
        """构造 TgConfig：会话路径取 tg_dl.default_session_path()，代理走共用设置。"""
        if not _TG_READY or TgConfig is None:
            return None
        api_id_text = self.tg_api_id_edit.text().strip()
        api_hash = self.tg_api_hash_edit.text().strip()
        if require_credentials and not api_id_text:
            notify.show_error(self, "请先填写 Telegram API ID（在 my.telegram.org 申请，纯数字）")
            return None
        api_id = 0
        if api_id_text:
            try:
                api_id = int(api_id_text)
            except ValueError:
                notify.show_error(self, "API ID 必须是数字（在 my.telegram.org 申请）")
                return None
        if require_credentials and not api_hash:
            notify.show_error(self, "请先填写 Telegram API Hash")
            return None
        try:
            session_path = str(tg_default_session_path())
        except Exception:  # 核心异常不应阻断界面
            session_path = "telegram.session"
        return TgConfig(
            api_id=api_id,
            api_hash=api_hash,
            session_path=session_path,
            proxy=self._tg_proxy_value(),
        )

    def _render_tg_qr(self, matrix):
        """把二维码矩阵用 QPainter 画成方块（不引入除 qrcode 之外的渲染依赖）。"""
        try:
            rows = len(matrix)
            cols = max(len(row) for row in matrix)
        except (TypeError, ValueError):
            return False
        if rows <= 0 or cols <= 0:
            return False
        quiet = 4
        modules = max(rows, cols) + quiet * 2
        scale = max(1, 240 // modules)   # 向下取整，保证画布不超过 240px 的标签区
        side = scale * modules
        pixmap = QPixmap(side, side)
        pixmap.fill(Qt.white)
        painter = QPainter(pixmap)
        try:
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.black)
            origin = scale * quiet
            for y, row in enumerate(matrix):
                for x, cell in enumerate(row):
                    if cell:
                        painter.drawRect(origin + x * scale, origin + y * scale, scale, scale)
        finally:
            painter.end()
        self.tg_qr_label.clear()
        self.tg_qr_label.setPixmap(pixmap)
        return True

    def _on_tg_login_clicked(self):
        if not _TG_READY:
            notify.show_error(self, "飞机模式模块 tg_dl 未就绪，暂无法登录。")
            return
        worker = self._tg_login_worker
        if worker is not None and worker.isRunning():
            self._tg_log("正在登录中，请稍候")
            return
        config = self._tg_config()
        if config is None:
            return
        self._tg_login_worker = None
        self.tg_login_button.setEnabled(False)
        self.tg_login_button.setText("登录中…")
        self.tg_status_label.setText("等待扫码…")
        self.tg_qr_label.clear()
        self.tg_qr_label.setText("正在生成二维码…")
        self._tg_log(
            f"开始扫码登录：API ID={config.api_id}，API Hash={_mask_secret(config.api_hash)}，"
            f"代理：{config.proxy or '系统网络'}"
        )
        worker = TgQrLoginWorker(
            tg_qr_login,
            config,
            qr_matrix_func=tg_qr_matrix,
            password=self.tg_password_edit.text(),
            cancel_error_type=TgCancelledError,
            error_types=(TgInputError, TgAuthError),
            parent=self,
        )
        worker.qr_ready.connect(self._on_tg_qr_ready)
        worker.logged_in.connect(self._on_tg_logged_in)
        worker.password_required.connect(self._on_tg_password_required)
        worker.failed.connect(self._on_tg_login_failed)
        worker.finished.connect(worker.deleteLater)
        self._tg_login_worker = worker
        worker.start()

    def _on_tg_qr_ready(self, url, matrix):
        self._tg_log("二维码已生成，请用 Telegram 手机客户端扫码登录")
        if not self._render_tg_qr(matrix):
            self.tg_qr_label.setText("二维码生成失败，请重新点击“扫码登录”")

    def _restore_tg_login_button(self):
        self.tg_login_button.setEnabled(True)
        self.tg_login_button.setText("扫码登录")

    def _on_tg_logged_in(self):
        self._tg_login_worker = None
        self._restore_tg_login_button()
        self.tg_status_label.setText("已登录，会话已保存")
        self.tg_password_edit.clear()
        self._tg_log("扫码登录成功，会话已保存到本地")

    def _on_tg_password_required(self, message):
        self._tg_login_worker = None
        self._restore_tg_login_button()
        self.tg_status_label.setText("未登录")
        hint = "请在“两步验证密码（可选）”中填写密码后重新点击“扫码登录”"
        self._tg_log(f"登录需要两步验证密码：{message}；{hint}")
        self.tg_password_edit.setFocus()
        notify.show_error(self, f"{message}\n{hint}")

    def _on_tg_login_failed(self, message):
        self._tg_login_worker = None
        self._restore_tg_login_button()
        self.tg_status_label.setText("未登录")
        self._tg_log(f"登录失败：{message}")
        notify.show_error(self, message)

    def _on_tg_logout_clicked(self):
        if not _TG_READY:
            notify.show_error(self, "飞机模式模块 tg_dl 未就绪，暂无法退出登录。")
            return
        config = self._tg_config(require_credentials=False)
        if config is None:
            return
        try:
            ok = bool(tg_logout(config))
        except Exception as exc:
            self._tg_log(f"退出登录失败：{exc}")
            notify.show_error(self, str(exc))
            return
        self.tg_status_label.setText("未登录")
        self.tg_qr_label.clear()
        self.tg_qr_label.setText("已退出登录，点击“扫码登录”重新获取二维码")
        self.tg_password_edit.clear()
        self._tg_log("已退出登录，本地会话已删除" if ok else "已退出登录（本地会话文件不存在）")

    def _on_tg_list_clicked(self):
        if not _TG_READY:
            notify.show_error(self, "飞机模式模块 tg_dl 未就绪，暂无法预览频道。")
            return
        worker = self._tg_list_worker
        if worker is not None and worker.isRunning():
            self._tg_log("正在预览中，请稍候")
            return
        config = self._tg_config()
        if config is None:
            return
        channel = self.tg_channel_edit.text().strip()
        if not channel:
            notify.show_error(self, "请输入频道（@用户名 或 t.me 链接）")
            return
        self._tg_list_worker = None
        self.tg_list_button.setEnabled(False)
        self.tg_list_button.setText("预览中…")
        self.tg_media_info_label.setText("预览中…")
        self._tg_log(f"正在预览频道：{channel}（代理：{config.proxy or '系统网络'}）")
        worker = TgListWorker(
            tg_list_channel_media,
            config,
            channel,
            media_types=None,
            limit=self.tg_limit_spin.value(),
            error_types=(TgInputError, TgAuthError, TgDownloadError),
            parent=self,
        )
        worker.listed.connect(self._on_tg_listed)
        worker.failed.connect(self._on_tg_list_failed)
        worker.finished.connect(worker.deleteLater)
        self._tg_list_worker = worker
        worker.start()

    def _on_tg_listed(self, info):
        self._tg_list_worker = None
        self.tg_list_button.setEnabled(True)
        self.tg_list_button.setText("预览频道")
        items = list(getattr(info, "items", None) or [])
        counts = {"photo": 0, "video": 0, "document": 0, "audio": 0}
        for item in items:
            kind = str(getattr(item, "kind", "") or "")
            if kind in counts:
                counts[kind] += 1
        title = getattr(info, "title", "") or ""
        username = str(getattr(info, "username", "") or "").lstrip("@")
        total = getattr(info, "total", len(items))
        self.tg_media_info_label.setText(
            f"标题：{title}\n"
            f"用户名：{('@' + username) if username else '—'}\n"
            f"总数：{total}\n"
            f"图片：{counts['photo']} / 视频：{counts['video']} / "
            f"文件：{counts['document']} / 音频：{counts['audio']}"
        )
        self._tg_log(
            f"预览成功：{title}（共 {total} 项：图片 {counts['photo']} / 视频 {counts['video']} / "
            f"文件 {counts['document']} / 音频 {counts['audio']}）"
        )

    def _on_tg_list_failed(self, message):
        self._tg_list_worker = None
        self.tg_list_button.setEnabled(True)
        self.tg_list_button.setText("预览频道")
        self.tg_media_info_label.setText("预览失败")
        self._tg_log(f"预览失败：{message}")
        notify.show_error(self, message)

    def _on_tg_start_clicked(self):
        if not _TG_READY:
            notify.show_error(self, "飞机模式模块 tg_dl 未就绪，暂无法下载。")
            return
        worker = self._tg_worker
        if worker is not None and worker.isRunning():
            self._tg_log("请等待当前下载结束后再开始")
            return
        config = self._tg_config()
        if config is None:
            return
        channel = self.tg_channel_edit.text().strip()
        if not channel:
            notify.show_error(self, "请输入频道（@用户名 或 t.me 链接）")
            return
        save_dir = self.tg_save_dir_edit.text().strip() or str(_default_save_dir())
        media_types = self.tg_types_combo.currentData()
        limit = self.tg_limit_spin.value()
        self._tg_worker = None
        self.tg_start_button.setEnabled(False)
        self.tg_cancel_button.setEnabled(True)
        self._tg_reset_progress()
        self._tg_last_stage = None
        self._tg_speed_anchor_bytes = 0
        self._tg_speed_anchor_time = 0.0
        self._tg_log(
            f"开始下载：{channel}（类型：{self.tg_types_combo.currentText()}，"
            f"条数：{limit} 条（0=全部），代理：{config.proxy or '系统网络'}）→ {save_dir}"
        )
        worker = TgDownloadWorker(
            tg_download_channel_media,
            config,
            channel,
            save_dir=save_dir,
            media_types=media_types,
            limit=limit,
            cancel_error_type=TgCancelledError,
            error_types=(TgInputError, TgAuthError, TgDownloadError),
            parent=self,
        )
        worker.progress.connect(self._on_tg_progress)
        worker.finished_ok.connect(self._on_tg_finished)
        worker.failed.connect(self._on_tg_failed)
        worker.cancelled.connect(self._on_tg_cancelled)
        worker.finished.connect(worker.deleteLater)
        self._tg_worker = worker
        worker.start()

    def _on_tg_progress(self, stage, done, total):
        if stage != self._tg_last_stage:
            self._tg_last_stage = stage
            self._tg_log(f"阶段：{_TG_STAGE_TEXT.get(stage, stage)}")
            self._tg_speed_anchor_bytes = done
            self._tg_speed_anchor_time = time.monotonic()
        self.tg_stage_label.setText(_TG_STAGE_TEXT.get(stage, stage))
        if stage == "done":
            self.tg_progress_bar.setRange(0, 100)
            self.tg_progress_bar.setValue(100)
            self.tg_percent_label.setText("100%")
            self.tg_speed_label.setText("—")
            return
        if stage == "download" and total > 0:
            self.tg_progress_bar.setRange(0, 100)
            percent = max(0, min(100, int(done * 100 // total)))
            self.tg_progress_bar.setValue(percent)
            self.tg_percent_label.setText(f"{percent}%")
            now = time.monotonic()
            dt = now - self._tg_speed_anchor_time
            if dt >= 0.5:
                speed = max(0.0, (done - self._tg_speed_anchor_bytes) / dt)
                self.tg_speed_label.setText(f"{_format_bytes(int(speed))}/s")
                self._tg_speed_anchor_bytes = done
                self._tg_speed_anchor_time = now
        else:
            self.tg_progress_bar.setRange(0, 0)
            self.tg_percent_label.setText("—")
            self.tg_speed_label.setText("—")

    def _on_tg_finished(self, paths):
        self._tg_worker = None
        paths = list(paths or [])
        save_dir = self.tg_save_dir_edit.text().strip() or str(Path.home())
        self.tg_progress_bar.setRange(0, 100)
        self.tg_progress_bar.setValue(100)
        self.tg_stage_label.setText("完成")
        self.tg_percent_label.setText("100%")
        self.tg_speed_label.setText("—")
        self.tg_start_button.setEnabled(True)
        self.tg_cancel_button.setEnabled(False)
        self._tg_log(f"下载完成：共 {len(paths)} 个文件 → {save_dir}")
        notify.show_success(
            self, "下载完成", f"已下载 {len(paths)} 个文件到：{save_dir}", folder=Path(save_dir)
        )

    def _on_tg_failed(self, message):
        self._tg_worker = None
        self.tg_progress_bar.setRange(0, 100)
        self.tg_stage_label.setText("下载失败")
        self.tg_start_button.setEnabled(True)
        self.tg_cancel_button.setEnabled(False)
        self._tg_log(f"下载失败：{message}")
        notify.show_error(self, message)

    def _on_tg_cancelled(self):
        self._tg_worker = None
        self.tg_progress_bar.setRange(0, 100)
        self.tg_progress_bar.setValue(0)
        self.tg_stage_label.setText("已取消")
        self.tg_percent_label.setText("—")
        self.tg_speed_label.setText("—")
        self.tg_start_button.setEnabled(True)
        self.tg_cancel_button.setEnabled(False)
        self._tg_log("已取消下载")
        notify.show_cancelled(self, "已取消下载")

    def _on_tg_cancel_clicked(self):
        worker = self._tg_worker
        if worker is not None and worker.isRunning():
            self._tg_log("正在取消下载…")
            worker.request_cancel()
            self.tg_cancel_button.setEnabled(False)

    def _on_tg_browse_clicked(self):
        current = self.tg_save_dir_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", current)
        if folder:
            self.tg_save_dir_edit.setText(folder)
            self._tg_log(f"保存目录已切换：{folder}")

    # ---------- 工具 ----------

    def _log(self, message):
        self.status_log.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _uni_log(self, message):
        self.uni_status_log.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _pack_log(self, message):
        self.pack_status_log.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _tg_log(self, message):
        self.tg_status_log.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _reset_progress(self):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.stage_label.setText("准备中")
        self.percent_label.setText("—")
        self.speed_label.setText("—")

    def _uni_reset_progress(self):
        self.uni_progress_bar.setRange(0, 100)
        self.uni_progress_bar.setValue(0)
        self.uni_stage_label.setText("准备中")
        self.uni_percent_label.setText("—")
        self.uni_speed_label.setText("—")

    def _pack_reset_progress(self):
        self.pack_progress_bar.setRange(0, 100)
        self.pack_progress_bar.setValue(0)
        self.pack_stage_label.setText("准备中")
        self.pack_percent_label.setText("—")
        self.pack_speed_label.setText("—")

    def _tg_reset_progress(self):
        self.tg_progress_bar.setRange(0, 100)
        self.tg_progress_bar.setValue(0)
        self.tg_stage_label.setText("准备中")
        self.tg_percent_label.setText("—")
        self.tg_speed_label.setText("—")

    def closeEvent(self, event):
        self._persist_settings()
        for worker in (self._worker, self._uni_worker, self._pack_worker,
                       self._tg_login_worker, self._tg_list_worker, self._tg_worker):
            if worker is not None and worker.isRunning():
                worker.request_cancel()
                worker.wait(5000)
                if worker.isRunning():
                    worker.terminate()
                    worker.wait(2000)
        super().closeEvent(event)
