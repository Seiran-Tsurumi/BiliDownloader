"""后台线程 worker：网络/解析/合并全部在 QThread 中执行。

通过信号回传进度与结果，绝不直接触碰控件。
"""

import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal


class ParseWorker(QThread):
    """后台执行 parse_input + list_qualities。"""

    parsed = Signal(object, object)  # (VideoMeta, list[Quality])
    failed = Signal(str)             # 可直接展示的中文 message

    def __init__(self, parse_func, list_qualities_func, text, cookie=None,
                 error_types=(), parent=None):
        super().__init__(parent)
        self._parse_func = parse_func
        self._list_func = list_qualities_func
        self._text = text
        self._cookie = cookie
        self._error_types = tuple(error_types)

    def request_cancel(self):
        """解析阶段无取消回调，占位以统一接口。"""

    def run(self):
        try:
            meta = self._parse_func(self._text)
            qualities = self._list_func(meta, cookie=self._cookie)
        except Exception as exc:
            if isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            self.parsed.emit(meta, qualities)


class DownloadWorker(QThread):
    """后台执行 download_video，cancel 回调桥接 threading.Event。"""

    progress = Signal(str, int, int)  # (stage, downloaded, total)
    finished_ok = Signal(str)         # 输出文件路径
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, download_func, meta, cookie=None, quality="max",
                 save_dir=".", cancel_error_type=None, error_types=(),
                 parent=None):
        super().__init__(parent)
        self._download_func = download_func
        self._meta = meta
        self._cookie = cookie
        self._quality = quality
        self._save_dir = save_dir
        self._cancel_error_type = cancel_error_type
        self._error_types = tuple(error_types)
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def _is_cancelled(self):
        return self._cancel_event.is_set()

    def _on_progress(self, stage, downloaded, total):
        self.progress.emit(str(stage), int(downloaded), int(total))

    def run(self):
        try:
            Path(self._save_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.failed.emit(f"无法创建保存目录：{exc}")
            return
        try:
            path = self._download_func(
                meta=self._meta,
                cookie=self._cookie,
                quality=self._quality,
                save_dir=self._save_dir,
                progress=self._on_progress,
                cancel=self._is_cancelled,
            )
        except self._cancel_error_type:
            self.cancelled.emit()
        except Exception as exc:
            if isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            self.finished_ok.emit(str(path))
