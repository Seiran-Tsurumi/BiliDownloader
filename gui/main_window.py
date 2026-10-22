"""BiliDownloader 主窗口：单视频下载的完整交互。

UI 线程只负责界面；parse_input / list_qualities / download_video 全部在
QThread 后台线程中执行，通过信号回传进度与结果。
"""

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    QVBoxLayout,
    QWidget,
)

from . import notify
from .workers import DownloadWorker, ParseWorker

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

COMPLIANCE_TEXT = (
    "本程序仅作为技术研究演示使用，使用者必须遵守B站用户协议以及版权相关法律法规，"
    "仅可下载自身拥有版权或已获得授权的视频，禁止私自下载、传播他人受版权保护的内容。"
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
    if seconds < 0:
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


class MainWindow(QMainWindow):
    """单视频下载主窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(760, 620)
        self.setMinimumSize(620, 480)

        self._cookie = None      # 仅内存变量，绝不写盘
        self._meta = None
        self._parsed_text = None
        self._worker = None
        self._parsing = False
        self._last_stage = None
        self._speed_anchor_bytes = 0
        self._speed_anchor_time = 0.0

        self._build_ui()

        if not _CORE_READY:
            self._log(f"警告：核心模块 bili_dl 未就绪（{_CORE_IMPORT_ERROR}），下载功能暂不可用。")
            self.download_button.setEnabled(False)
        else:
            self._log("已就绪，粘贴视频链接或 BV 号后点击“下载”。")

    # ---------- UI 构建 ----------

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        settings_menu = self.menuBar().addMenu("设置(&S)")
        self.cookie_action = settings_menu.addAction("Cookie 设置…")
        self.cookie_action.setObjectName("cookie_action")
        self.cookie_action.triggered.connect(self._open_cookie_dialog)

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
        root.addLayout(input_row)

        option_row = QHBoxLayout()
        option_row.addWidget(QLabel("画质："))
        self.quality_combo = QComboBox()
        self.quality_combo.setObjectName("quality_combo")
        self.quality_combo.setEnabled(False)
        option_row.addWidget(self.quality_combo, 1)
        option_row.addWidget(QLabel("保存到："))
        self.save_dir_edit = QLineEdit(str(_default_save_dir()))
        self.save_dir_edit.setObjectName("save_dir_edit")
        self.save_dir_edit.setReadOnly(True)
        option_row.addWidget(self.save_dir_edit, 2)
        self.browse_button = QPushButton("选择…")
        self.browse_button.setObjectName("browse_button")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        option_row.addWidget(self.browse_button)
        root.addLayout(option_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progress_bar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

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
        root.addLayout(progress_text_row)

        root.addWidget(QLabel("状态日志："))
        self.status_log = QPlainTextEdit()
        self.status_log.setObjectName("status_log")
        self.status_log.setReadOnly(True)
        self.status_log.setMaximumBlockCount(2000)
        root.addWidget(self.status_log, 1)

        self.compliance_label = QLabel(COMPLIANCE_TEXT)
        self.compliance_label.setObjectName("compliance_label")
        self.compliance_label.setWordWrap(True)
        self.compliance_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.compliance_label)

    # ---------- 事件处理 ----------

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

    # ---------- 工具 ----------

    def _log(self, message):
        self.status_log.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _reset_progress(self):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.stage_label.setText("准备中")
        self.percent_label.setText("—")
        self.speed_label.setText("—")

    def closeEvent(self, event):
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_cancel()
            worker.wait(5000)
            if worker.isRunning():
                worker.terminate()
                worker.wait(2000)
        super().closeEvent(event)
