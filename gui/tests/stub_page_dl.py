"""按 page_dl 契约实现的核心 stub（仅供 gui/tests 使用）。

test_pack_gui.py 在导入 gui.main_window 之前把它注册为
sys.modules["page_dl"]，因此与真实 page_dl 包保持相同的导入路径与函数签名，
并记录收到的参数，便于断言透传。
"""

import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path


class PageInputError(Exception):
    pass


class PageDownloadError(Exception):
    pass


class PageCancelledError(Exception):
    pass


@dataclass
class MediaItem:
    url: str
    kind: str
    filename: str
    referer: str = ""


@dataclass
class PageBundle:
    url: str
    title: str
    items: list
    image_count: int
    video_count: int
    audio_count: int
    other_count: int
    skipped: int = 0


PAGE_URL = "https://example.com/album/1"


def make_bundle(url=PAGE_URL, title="测试页面：视图打包演示"):
    """构造固定清单：图片 3、视频 2、音频 1、其他 0。"""
    items = [
        MediaItem(f"https://cdn.example.com/img/{index}.jpg", "image",
                  f"{index:03d}.jpg", url)
        for index in range(1, 4)
    ]
    items += [
        MediaItem(f"https://cdn.example.com/video/{index}.mp4", "video",
                  f"clip-{index}.mp4", url)
        for index in range(1, 3)
    ]
    items.append(MediaItem("https://cdn.example.com/audio/1.m4a", "audio", "bgm.m4a", url))
    return PageBundle(
        url=url,
        title=title,
        items=items,
        image_count=3,
        video_count=2,
        audio_count=1,
        other_count=0,
        skipped=0,
    )


DEFAULT_BUNDLE = make_bundle()


STATE = {
    "parse_calls": 0,
    "parse_thread_id": None,
    "last_cookie": None,
    "last_proxy": None,
    "last_max_items": None,
    "download_calls": 0,
    "download_thread_id": None,
    "download_started": threading.Event(),
    "download_sleep_seconds": 0.001,
    "last_bundle": None,
    "last_save_dir": None,
    "last_zip_output": None,
    "last_cancel_hook": None,
    "last_download_cookie": None,
    # 可按需改写的失败/返回行为
    "parse_error": None,
    "download_error": None,
    "zip_path": None,
    "detected_proxy": None,
    "detect_proxy_calls": 0,
}


def reset_state():
    STATE.update({
        "parse_calls": 0,
        "parse_thread_id": None,
        "last_cookie": None,
        "last_proxy": None,
        "last_max_items": None,
        "download_calls": 0,
        "download_thread_id": None,
        "download_sleep_seconds": 0.001,
        "last_bundle": None,
        "last_save_dir": None,
        "last_zip_output": None,
        "last_cancel_hook": None,
        "last_download_cookie": None,
        "parse_error": None,
        "download_error": None,
        "zip_path": None,
        "detected_proxy": None,
        "detect_proxy_calls": 0,
    })
    STATE["download_started"].clear()


def detect_local_proxy():
    """模拟 page_dl 的本地代理探测：返回 STATE["detected_proxy"]。"""
    STATE["detect_proxy_calls"] += 1
    return STATE["detected_proxy"]


def parse_page(url, cookie=None, proxy=None, max_items=500):
    STATE["parse_calls"] += 1
    STATE["parse_thread_id"] = threading.get_ident()
    STATE["last_cookie"] = cookie
    STATE["last_proxy"] = proxy
    STATE["last_max_items"] = max_items
    if STATE["parse_error"]:
        raise PageInputError(str(STATE["parse_error"]))
    lowered = str(url).lower()
    if "garbage" in lowered or not lowered.startswith(("http://", "https://")):
        raise PageInputError(f"无法从“{url}”解析出页面媒体")
    return DEFAULT_BUNDLE


def download_page(bundle, save_dir=".", zip_output=True, progress=None, cancel=None,
                  proxy=None, cookie=None):
    STATE["download_calls"] += 1
    STATE["download_thread_id"] = threading.get_ident()
    STATE["download_started"].set()
    STATE["last_bundle"] = bundle
    STATE["last_save_dir"] = save_dir
    STATE["last_zip_output"] = zip_output
    STATE["last_proxy"] = proxy
    STATE["last_download_cookie"] = cookie
    STATE["last_cancel_hook"] = cancel is not None
    if STATE["download_error"]:
        raise PageDownloadError(str(STATE["download_error"]))
    items = list(getattr(bundle, "items", []) or [])
    total = max(1, len(items))
    if progress is not None:
        progress("download", 0, total)
    for index in range(1, total + 1):
        if cancel is not None and cancel():
            raise PageCancelledError()
        if progress is not None:
            progress("download", index, total)
        time.sleep(STATE["download_sleep_seconds"])
    if cancel is not None and cancel():
        raise PageCancelledError()
    if progress is not None:
        progress("packing", 0, 0)
    time.sleep(STATE["download_sleep_seconds"])
    zip_path = Path(STATE["zip_path"] or (Path(save_dir) / "视图打包.zip"))
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("manifest.txt", "\n".join(item.filename for item in items))
    if progress is not None:
        progress("done", total, total)
    return str(zip_path)
