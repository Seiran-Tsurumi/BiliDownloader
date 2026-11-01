"""按 tg_dl 契约实现的核心 stub（仅供 gui/tests 使用）。

test_tg_gui.py 在导入 gui.main_window 之前把它注册为 sys.modules["tg_dl"]，
因此与真实 tg_dl 包保持相同的导入路径、函数签名与异常类型，
并把收到的调用与参数记进 STATE，便于断言透传与失败分支。
"""

import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


class TgInputError(Exception):
    pass


class TgAuthError(Exception):
    """登录/权限错误；password_required=True 表示需要两步验证密码。"""

    def __init__(self, message="", password_required=False):
        super().__init__(message)
        self.password_required = bool(password_required)


class TgDownloadError(Exception):
    pass


class TgCancelledError(Exception):
    pass


@dataclass
class TgMediaItem:
    message_id: int
    kind: str
    filename: str
    size: int
    date: object = None


@dataclass
class TgChannelInfo:
    title: str
    username: str
    total: int
    items: list = field(default_factory=list)


@dataclass
class TgConfig:
    api_id: int
    api_hash: str
    session_path: str
    proxy: object = None


QR_URL = "tg://login?token=stub-token"
CHANNEL = "@stub_channel"
CHANNEL_TITLE = "测试频道：飞机模式演示"


def make_channel_info(title=CHANNEL_TITLE, username="stub_channel"):
    """固定清单：图片 3、视频 2、文件 1、音频 1（共 7 项）。"""
    items = [
        TgMediaItem(index, "photo", f"photo-{index}.jpg", 1024 * index, 1700000000 + index)
        for index in range(1, 4)
    ]
    items += [
        TgMediaItem(index, "video", f"video-{index}.mp4", 4096 * index, 1700000000 + index)
        for index in range(4, 6)
    ]
    items.append(TgMediaItem(6, "document", "doc-1.pdf", 8192, 1700000006))
    items.append(TgMediaItem(7, "audio", "audio-1.m4a", 2048, 1700000007))
    return TgChannelInfo(title=title, username=username, total=len(items), items=items)


DEFAULT_CHANNEL_INFO = make_channel_info()


def default_session_path():
    return str(Path(tempfile.gettempdir()) / "bili_tg_stub.session")


def qr_matrix(url):
    """按链接生成确定性矩阵（21x21，含三个定位角），供 QPainter 渲染。"""
    STATE["qr_matrix_calls"] += 1
    STATE["last_qr_url"] = str(url)
    if STATE["qr_matrix_error"]:
        raise RuntimeError(str(STATE["qr_matrix_error"]))
    size = 21
    matrix = [[False] * size for _ in range(size)]
    for origin_y, origin_x in ((0, 0), (0, size - 7), (size - 7, 0)):
        for y in range(7):
            for x in range(7):
                edge = y in (0, 6) or x in (0, 6)
                core = 2 <= y <= 4 and 2 <= x <= 4
                matrix[origin_y + y][origin_x + x] = bool(edge or core)
    seed = sum(ord(char) for char in str(url))
    for y in range(8, size - 8):
        for x in range(size):
            if (x * 7 + y * 11 + seed) % 3 == 0:
                matrix[y][x] = True
    return matrix


STATE = {
    # 登录
    "qr_login_calls": 0,
    "qr_thread_id": None,
    "last_config": None,
    "last_password": None,
    "last_timeout": None,
    "login_sleep_seconds": 0.001,
    "login_result": True,
    "login_error": None,
    "password_required": False,
    "password_required_message": "该账号开启了两步验证，需要密码",
    "qr_two_args": False,
    # 二维码矩阵
    "qr_matrix_calls": 0,
    "last_qr_url": None,
    "qr_matrix_error": None,
    # 预览
    "list_calls": 0,
    "list_thread_id": None,
    "last_channel": None,
    "last_media_types": None,
    "last_list_limit": None,
    "list_error": None,
    "channel_info": None,
    # 下载
    "download_calls": 0,
    "download_thread_id": None,
    "download_started": threading.Event(),
    "download_sleep_seconds": 0.001,
    "last_save_dir": None,
    "last_download_media_types": None,
    "last_download_limit": None,
    "last_cancel_hook": False,
    "download_error": None,
    "download_paths": None,
    # 退出与代理
    "logout_calls": 0,
    "last_logout_config": None,
    "logout_result": True,
    "detected_proxy": None,
    "detect_proxy_calls": 0,
}


def reset_state():
    STATE.update({
        "qr_login_calls": 0,
        "qr_thread_id": None,
        "last_config": None,
        "last_password": None,
        "last_timeout": None,
        "login_sleep_seconds": 0.001,
        "login_result": True,
        "login_error": None,
        "password_required": False,
        "password_required_message": "该账号开启了两步验证，需要密码",
        "qr_two_args": False,
        "qr_matrix_calls": 0,
        "last_qr_url": None,
        "qr_matrix_error": None,
        "list_calls": 0,
        "list_thread_id": None,
        "last_channel": None,
        "last_media_types": None,
        "last_list_limit": None,
        "list_error": None,
        "channel_info": None,
        "download_calls": 0,
        "download_thread_id": None,
        "download_sleep_seconds": 0.001,
        "last_save_dir": None,
        "last_download_media_types": None,
        "last_download_limit": None,
        "last_cancel_hook": False,
        "download_error": None,
        "download_paths": None,
        "logout_calls": 0,
        "last_logout_config": None,
        "logout_result": True,
        "detected_proxy": None,
        "detect_proxy_calls": 0,
    })
    STATE["download_started"].clear()


def detect_local_proxy():
    """模拟本地代理探测（真实 tg_dl 若未提供该接口，GUI 会回退万能页的探测）。"""
    STATE["detect_proxy_calls"] += 1
    return STATE["detected_proxy"]


def qr_login(config, on_qr=None, password=None, cancel=None, timeout=180):
    STATE["qr_login_calls"] += 1
    STATE["qr_thread_id"] = threading.get_ident()
    STATE["last_config"] = config
    STATE["last_password"] = password
    STATE["last_timeout"] = timeout
    if on_qr is not None:
        # 两种核心回调风格都要兼容：on_qr(url) 与 on_qr(url, matrix)
        if STATE["qr_two_args"]:
            on_qr(QR_URL, qr_matrix(QR_URL))
        else:
            on_qr(QR_URL)
    if STATE["password_required"]:
        raise TgAuthError(STATE["password_required_message"], password_required=True)
    if STATE["login_error"]:
        raise TgAuthError(str(STATE["login_error"]))
    time.sleep(STATE["login_sleep_seconds"])
    if cancel is not None and cancel():
        raise TgCancelledError()
    return bool(STATE["login_result"])


def list_channel_media(config, channel, media_types=None, limit=0, cancel=None):
    STATE["list_calls"] += 1
    STATE["list_thread_id"] = threading.get_ident()
    STATE["last_config"] = config
    STATE["last_channel"] = channel
    STATE["last_media_types"] = media_types
    STATE["last_list_limit"] = limit
    if STATE["list_error"]:
        raise TgDownloadError(str(STATE["list_error"]))
    text = str(channel or "").strip()
    if not text:
        raise TgInputError("频道不能为空")
    if "garbage" in text.lower() or not (text.startswith("@") or "t.me/" in text):
        raise TgInputError(f"无法解析频道“{channel}”，请输入 @用户名 或 t.me 链接")
    return STATE["channel_info"] or DEFAULT_CHANNEL_INFO


def download_channel_media(config, channel, save_dir=".", media_types=None, limit=0,
                           progress=None, cancel=None):
    STATE["download_calls"] += 1
    STATE["download_thread_id"] = threading.get_ident()
    STATE["download_started"].set()
    STATE["last_config"] = config
    STATE["last_channel"] = channel
    STATE["last_save_dir"] = save_dir
    STATE["last_download_media_types"] = media_types
    STATE["last_download_limit"] = limit
    STATE["last_cancel_hook"] = cancel is not None
    if STATE["download_error"]:
        raise TgDownloadError(str(STATE["download_error"]))
    info = STATE["channel_info"] or DEFAULT_CHANNEL_INFO
    items = list(info.items)
    if media_types:
        items = [item for item in items if item.kind in media_types]
    if int(limit or 0) > 0:
        items = items[:int(limit)]
    total = max(1, len(items))
    if progress is not None:
        progress("download", 0, total)
    paths = []
    for index, item in enumerate(items, 1):
        if cancel is not None and cancel():
            raise TgCancelledError()
        time.sleep(STATE["download_sleep_seconds"])
        path = Path(save_dir) / item.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"stub-media")
        paths.append(str(path))
        if progress is not None:
            progress("download", index, total)
    if cancel is not None and cancel():
        raise TgCancelledError()
    if progress is not None:
        progress("done", total, total)
    STATE["download_paths"] = list(paths)
    return paths


def logout(config):
    STATE["logout_calls"] += 1
    STATE["last_logout_config"] = config
    return bool(STATE["logout_result"])
