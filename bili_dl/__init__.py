"""bili_dl —— B 站单视频下载核心（纯 Python、无 UI、同步实现）。"""
from .download import download_video, list_qualities
from .errors import ApiError, BiliDLError, CancelledError, DownloadError, InputError
from .models import Quality, VideoMeta
from .parse import parse_input

__version__ = "2.0.0"

__all__ = [
    "parse_input",
    "list_qualities",
    "download_video",
    "InputError",
    "ApiError",
    "DownloadError",
    "CancelledError",
    "BiliDLError",
    "VideoMeta",
    "Quality",
]
