"""按接口契约实现的核心 stub（仅供 gui/tests 使用）。

test_gui.py 在导入 gui.main_window 之前把它注册为 sys.modules["bili_dl"]，
因此本文件与真实核心包保持相同的导入路径与函数签名。
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path


class InputError(Exception):
    pass


class ApiError(Exception):
    pass


class DownloadError(Exception):
    pass


class CancelledError(Exception):
    pass


@dataclass
class VideoMeta:
    bvid: str
    aid: int
    cid: int
    title: str
    owner_name: str
    duration: int


@dataclass
class Quality:
    qn: int
    desc: str


DEFAULT_META = VideoMeta(
    bvid="BV1xx411c7mD",
    aid=170001,
    cid=170001,
    title="测试视频：GUI 集成演示",
    owner_name="测试UP主",
    duration=125,
)

DEFAULT_QUALITIES = [
    Quality(80, "1080P 高清"),
    Quality(64, "720P 高清"),
    Quality(32, "480P 清晰"),
]

STATE = {
    "parse_count": 0,
    "parse_thread_id": None,
    "download_count": 0,
    "download_thread_id": None,
    "download_sleep_seconds": 0.001,
    "download_started": threading.Event(),
}


def reset_state():
    STATE.update({
        "parse_count": 0,
        "parse_thread_id": None,
        "download_count": 0,
        "download_thread_id": None,
        "download_sleep_seconds": 0.001,
    })
    STATE["download_started"].clear()


def parse_input(text):
    STATE["parse_count"] += 1
    STATE["parse_thread_id"] = threading.get_ident()
    lowered = text.lower()
    if not (lowered.startswith("bv") or "bilibili" in lowered or "https://" in lowered):
        raise InputError(f"无效的输入：无法从“{text}”解析出视频")
    return DEFAULT_META


def list_qualities(meta, cookie=None):
    return list(DEFAULT_QUALITIES)


def download_video(meta, cookie=None, quality="max", save_dir=".", progress=None,
                   cancel=None):
    STATE["download_count"] += 1
    STATE["download_thread_id"] = threading.get_ident()
    STATE["download_started"].set()
    if progress is not None:
        half = 512 * 1024
        progress("fetching", 0, 0)
        for done in range(0, half, 64 * 1024):
            if cancel is not None and cancel():
                raise CancelledError()
            progress("video", done, half)
            time.sleep(STATE["download_sleep_seconds"])
        for done in range(0, half, 64 * 1024):
            if cancel is not None and cancel():
                raise CancelledError()
            progress("audio", done, half)
            time.sleep(STATE["download_sleep_seconds"])
        progress("merging", 0, 0)
        time.sleep(STATE["download_sleep_seconds"])
        progress("done", half * 2, half * 2)
    return Path(save_dir) / f"{meta.bvid}-{quality}.mp4"
