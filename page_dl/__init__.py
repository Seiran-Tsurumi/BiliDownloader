"""page_dl —— 页面图片/视频/音频抓取与 ZIP 打包核心（纯 Python、无 UI、可独立复用）。

约定：
- 所有异常 message 均为可直接展示的中文。
- Cookie 仅经参数传入、仅存内存，绝不落盘。
- 进度回调 progress(stage, done, total)，stage 仅用 "download" / "packing" / "done"。
"""

from .download import download_page
from .errors import PageCancelledError, PageDLError, PageDownloadError, PageInputError
from .models import MediaItem, PageBundle
from .parse import parse_page

__version__ = "1.0.0"

__all__ = [
    "parse_page",
    "download_page",
    "PageBundle",
    "MediaItem",
    "PageDLError",
    "PageInputError",
    "PageDownloadError",
    "PageCancelledError",
]
