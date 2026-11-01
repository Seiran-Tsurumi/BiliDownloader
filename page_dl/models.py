"""page_dl 对外数据模型。"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class MediaItem:
    """页面上的单个媒体条目。"""

    url: str
    kind: str
    filename: str
    referer: str = ""


@dataclass
class PageBundle:
    """一次页面解析的结果。"""

    url: str
    title: str
    items: List[MediaItem] = field(default_factory=list)
    image_count: int = 0
    video_count: int = 0
    audio_count: int = 0
    other_count: int = 0
    skipped: int = 0


__all__ = ["MediaItem", "PageBundle"]
