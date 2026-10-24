"""按 uni_dl 契约实现的核心 stub（仅供 gui/tests 使用）。

test_universal_gui.py 在导入 gui.main_window 之前把它注册为
sys.modules["uni_dl"]，因此与真实 uni_dl 包保持相同的导入路径与函数签名。
"""

import threading
import time
from dataclasses import dataclass
from pathlib import Path


class UniInputError(Exception):
    pass


class UniDownloadError(Exception):
    pass


class UniCancelledError(Exception):
    pass


@dataclass
class UniversalMeta:
    url: str
    title: str
    uploader: str
    duration: int
    is_playlist: bool
    entry_count: int
    webpage_url: str
    extractor: str


FORMAT_PRESETS = [
    ("默认", "bv*+ba/b"),
    ("1080P", "bv*[height<=1080]+ba/b[height<=1080]"),
    ("720P", "bv*[height<=720]+ba/b[height<=720]"),
    ("仅音频", "ba/b"),
]
DEFAULT_FORMAT = "bv*+ba/b"

DEFAULT_META = UniversalMeta(
    url="https://example.com/watch?v=abc123",
    title="测试视频：万能下载演示",
    uploader="测试UP主",
    duration=95,
    is_playlist=False,
    entry_count=1,
    webpage_url="https://example.com/watch?v=abc123",
    extractor="example",
)

PLAYLIST_META = UniversalMeta(
    url="https://example.com/playlist?list=pl1",
    title="测试播放列表：万能下载演示",
    uploader="测试UP主",
    duration=0,
    is_playlist=True,
    entry_count=3,
    webpage_url="https://example.com/playlist?list=pl1",
    extractor="example",
)

STATE = {
    "parse_count": 0,
    "parse_thread_id": None,
    "parse_cookie": None,
    "parse_proxy": None,
    "download_count": 0,
    "download_thread_id": None,
    "download_started": threading.Event(),
    "download_sleep_seconds": 0.001,
    "last_format_sel": None,
    "last_cookie": None,
    "last_save_dir": None,
    "last_proxy": None,
    "last_accelerator": None,
    # 加速/代理联动的可配置项，测试可按需改写
    "has_accelerator": True,
    "detected_proxy": None,
    "detect_proxy_calls": 0,
}


def reset_state():
    STATE.update({
        "parse_count": 0,
        "parse_thread_id": None,
        "parse_cookie": None,
        "parse_proxy": None,
        "download_count": 0,
        "download_thread_id": None,
        "download_sleep_seconds": 0.001,
        "last_format_sel": None,
        "last_cookie": None,
        "last_save_dir": None,
        "last_proxy": None,
        "last_accelerator": None,
        "has_accelerator": True,
        "detected_proxy": None,
        "detect_proxy_calls": 0,
    })
    STATE["download_started"].clear()


def has_accelerator():
    """模拟 uni_dl.has_accelerator()：结果由 STATE["has_accelerator"] 控制。"""
    return bool(STATE["has_accelerator"])


def detect_local_proxy():
    """模拟 uni_dl.detect_local_proxy()：返回 STATE["detected_proxy"]。"""
    STATE["detect_proxy_calls"] += 1
    return STATE["detected_proxy"]


def parse_input(text, cookie=None, proxy=None):
    STATE["parse_count"] += 1
    STATE["parse_thread_id"] = threading.get_ident()
    STATE["parse_cookie"] = cookie
    STATE["parse_proxy"] = proxy
    lowered = text.lower()
    if "garbage" in lowered or not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise UniInputError(f"无法从“{text}”解析出视频")
    if "playlist" in lowered:
        return PLAYLIST_META
    return DEFAULT_META


def download_video(meta, format_sel=None, save_dir=".", cookie=None, proxy=None,
                   accelerator=True, progress=None, cancel=None):
    STATE["download_count"] += 1
    STATE["download_thread_id"] = threading.get_ident()
    STATE["download_started"].set()
    STATE["last_format_sel"] = format_sel
    STATE["last_cookie"] = cookie
    STATE["last_save_dir"] = save_dir
    STATE["last_proxy"] = proxy
    STATE["last_accelerator"] = accelerator
    if progress is not None:
        total = 1024 * 1024
        progress("video", 0, total)
        for done in range(0, total, 256 * 1024):
            if cancel is not None and cancel():
                raise UniCancelledError()
            progress("video", done, total)
            time.sleep(STATE["download_sleep_seconds"])
        progress("merging", 0, 0)
        time.sleep(STATE["download_sleep_seconds"])
        progress("done", total, total)
    paths = []
    if getattr(meta, "is_playlist", False):
        for index in range(1, int(getattr(meta, "entry_count", 1)) + 1):
            paths.append(str(Path(save_dir) / f"{meta.extractor}-{index:02d}.mp4"))
    else:
        paths.append(str(Path(save_dir) / f"{meta.extractor}-video.mp4"))
    return paths
