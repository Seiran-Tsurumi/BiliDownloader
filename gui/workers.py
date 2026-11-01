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


class UniversalParseWorker(QThread):
    """后台执行 uni_dl.parse_input。"""

    parsed = Signal(object)  # UniversalMeta
    failed = Signal(str)     # 可直接展示的中文 message

    def __init__(self, parse_func, text, cookie=None, proxy=None, error_types=(),
                 parent=None):
        super().__init__(parent)
        self._parse_func = parse_func
        self._text = text
        self._cookie = cookie
        self._proxy = proxy
        self._error_types = tuple(error_types)

    def request_cancel(self):
        """解析阶段无取消回调，占位以统一接口。"""

    def run(self):
        try:
            meta = self._parse_func(self._text, cookie=self._cookie, proxy=self._proxy)
        except Exception as exc:
            if isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            self.parsed.emit(meta)


class UniversalDownloadWorker(QThread):
    """后台执行 uni_dl.download_video，cancel 回调桥接 threading.Event。"""

    progress = Signal(str, int, int)  # (stage, downloaded, total)
    finished_ok = Signal(list)        # list[str]：播放列表可能返回多个路径
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, download_func, meta, format_sel=None, save_dir=".",
                 cookie=None, proxy=None, accelerator=True,
                 cancel_error_type=None, error_types=(), parent=None):
        super().__init__(parent)
        self._download_func = download_func
        self._meta = meta
        self._format_sel = format_sel
        self._save_dir = save_dir
        self._cookie = cookie
        self._proxy = proxy
        self._accelerator = bool(accelerator)
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
            paths = self._download_func(
                meta=self._meta,
                format_sel=self._format_sel,
                save_dir=self._save_dir,
                cookie=self._cookie,
                proxy=self._proxy,
                accelerator=self._accelerator,
                progress=self._on_progress,
                cancel=self._is_cancelled,
            )
        except Exception as exc:
            if (self._cancel_error_type is not None
                    and isinstance(exc, self._cancel_error_type)):
                self.cancelled.emit()
            elif isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            self.finished_ok.emit(list(paths))

class PageParseWorker(QThread):
    """后台执行 page_dl.parse_page。"""

    parsed = Signal(object)  # PageBundle
    failed = Signal(str)     # 可直接展示的中文 message

    def __init__(self, parse_func, text, cookie=None, proxy=None, error_types=(),
                 parent=None):
        super().__init__(parent)
        self._parse_func = parse_func
        self._text = text
        self._cookie = cookie
        self._proxy = proxy
        self._error_types = tuple(error_types)

    def request_cancel(self):
        """解析阶段无取消回调，占位以统一接口。"""

    def run(self):
        try:
            bundle = self._parse_func(self._text, cookie=self._cookie, proxy=self._proxy)
        except Exception as exc:
            if isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            self.parsed.emit(bundle)


class PagePackWorker(QThread):
    """后台执行 page_dl.download_page（打包 ZIP），cancel 回调桥接 threading.Event。"""

    progress = Signal(str, int, int)  # (stage, done, total)
    finished_ok = Signal(str)         # ZIP 路径
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, download_func, bundle, save_dir=".", zip_output=True,
                 proxy=None, cookie=None, cancel_error_type=None, error_types=(),
                 parent=None):
        super().__init__(parent)
        self._download_func = download_func
        self._bundle = bundle
        self._save_dir = save_dir
        self._zip_output = bool(zip_output)
        self._proxy = proxy
        self._cookie = cookie
        self._cancel_error_type = cancel_error_type
        self._error_types = tuple(error_types)
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def _is_cancelled(self):
        return self._cancel_event.is_set()

    def _on_progress(self, *args):
        """把核心的进度回调统一成 (stage, done, total)，兼容 1~3 个参数。"""
        stage, done, total = "download", 0, 0
        numbers = [a for a in args if isinstance(a, (int, float)) and not isinstance(a, bool)]
        if args and isinstance(args[0], str):
            stage = args[0]
        if len(numbers) >= 2:
            done, total = int(numbers[0]), int(numbers[1])
        elif numbers:
            done = total = int(numbers[0])
        self.progress.emit(stage, done, total)

    def run(self):
        try:
            Path(self._save_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.failed.emit(f"无法创建保存目录：{exc}")
            return
        try:
            path = self._download_func(
                self._bundle,
                save_dir=self._save_dir,
                zip_output=self._zip_output,
                progress=self._on_progress,
                cancel=self._is_cancelled,
                proxy=self._proxy,
                cookie=self._cookie,
            )
        except Exception as exc:
            if (self._cancel_error_type is not None
                    and isinstance(exc, self._cancel_error_type)):
                self.cancelled.emit()
            elif isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            self.finished_ok.emit(str(path))

class TgQrLoginWorker(QThread):
    """后台执行 tg_dl.qr_login：二维码矩阵在子线程算好后再回传 UI 线程绘制。"""

    qr_ready = Signal(str, object)    # (登录链接, list[list[bool]] 矩阵)
    logged_in = Signal()
    password_required = Signal(str)   # 需要两步验证密码（可直接展示的中文提示）
    failed = Signal(str)

    def __init__(self, login_func, config, qr_matrix_func=None, password=None,
                 timeout=180, cancel_error_type=None, error_types=(), parent=None):
        super().__init__(parent)
        self._login_func = login_func
        self._config = config
        self._qr_matrix_func = qr_matrix_func
        self._password = password
        self._timeout = int(timeout)
        self._cancel_error_type = cancel_error_type
        self._error_types = tuple(error_types)
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def _is_cancelled(self):
        return self._cancel_event.is_set()

    def _on_qr(self, url, matrix=None):
        """qr_login 的 on_qr 回调：兼容 on_qr(url) 与 on_qr(url, matrix) 两种核心实现。

        核心未附带矩阵时在此线程用 qr_matrix 算出，UI 线程只负责画方块。
        """
        if matrix is None and self._qr_matrix_func is not None:
            try:
                matrix = self._qr_matrix_func(url)
            except Exception:  # 矩阵生成失败不应中断登录
                traceback.print_exc()
                matrix = None
        self.qr_ready.emit(str(url), matrix)

    def run(self):
        try:
            ok = self._login_func(
                self._config,
                on_qr=self._on_qr,
                password=self._password or None,
                cancel=self._is_cancelled,
                timeout=self._timeout,
            )
        except Exception as exc:
            if bool(getattr(exc, "password_required", False)):
                self.password_required.emit(str(exc) or "该账号开启了两步验证，需要密码")
            elif (self._cancel_error_type is not None
                    and isinstance(exc, self._cancel_error_type)):
                self.failed.emit("登录已取消")
            elif isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            if ok:
                self.logged_in.emit()
            else:
                self.failed.emit("登录未完成（二维码已过期或已取消），请重新扫码")


class TgListWorker(QThread):
    """后台执行 tg_dl.list_channel_media。"""

    listed = Signal(object)  # TgChannelInfo
    failed = Signal(str)

    def __init__(self, list_func, config, channel, media_types=None, limit=0,
                 error_types=(), parent=None):
        super().__init__(parent)
        self._list_func = list_func
        self._config = config
        self._channel = channel
        self._media_types = media_types
        self._limit = int(limit)
        self._error_types = tuple(error_types)
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def _is_cancelled(self):
        return self._cancel_event.is_set()

    def run(self):
        try:
            info = self._list_func(
                self._config,
                self._channel,
                media_types=self._media_types,
                limit=self._limit,
                cancel=self._is_cancelled,
            )
        except Exception as exc:
            if isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            self.listed.emit(info)


class TgDownloadWorker(QThread):
    """后台执行 tg_dl.download_channel_media，cancel 回调桥接 threading.Event。"""

    progress = Signal(str, int, int)  # (stage, done, total)
    finished_ok = Signal(list)        # list[str]：已下载文件路径
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, download_func, config, channel, save_dir=".", media_types=None,
                 limit=0, cancel_error_type=None, error_types=(), parent=None):
        super().__init__(parent)
        self._download_func = download_func
        self._config = config
        self._channel = channel
        self._save_dir = save_dir
        self._media_types = media_types
        self._limit = int(limit)
        self._cancel_error_type = cancel_error_type
        self._error_types = tuple(error_types)
        self._cancel_event = threading.Event()

    def request_cancel(self):
        self._cancel_event.set()

    def _is_cancelled(self):
        return self._cancel_event.is_set()

    def _on_progress(self, *args):
        """把核心的进度回调统一成 (stage, done, total)，兼容 1~3 个参数。"""
        stage, done, total = "download", 0, 0
        numbers = [a for a in args if isinstance(a, (int, float)) and not isinstance(a, bool)]
        if args and isinstance(args[0], str):
            stage = args[0]
        if len(numbers) >= 2:
            done, total = int(numbers[0]), int(numbers[1])
        elif numbers:
            done = total = int(numbers[0])
        self.progress.emit(stage, done, total)

    def run(self):
        try:
            Path(self._save_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.failed.emit(f"无法创建保存目录：{exc}")
            return
        try:
            paths = self._download_func(
                self._config,
                self._channel,
                save_dir=self._save_dir,
                media_types=self._media_types,
                limit=self._limit,
                progress=self._on_progress,
                cancel=self._is_cancelled,
            )
        except Exception as exc:
            if (self._cancel_error_type is not None
                    and isinstance(exc, self._cancel_error_type)):
                self.cancelled.emit()
            elif isinstance(exc, self._error_types):
                self.failed.emit(str(exc))
            else:
                traceback.print_exc()
                self.failed.emit(f"未知错误：{exc}")
        else:
            self.finished_ok.emit(list(paths))
