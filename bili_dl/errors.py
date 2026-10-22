"""bili_dl 错误类型定义：message 均为可直接展示给用户的中文。"""


class BiliDLError(Exception):
    """bili_dl 所有错误的基类。"""


class InputError(BiliDLError):
    """输入非法（不是单视频链接或 BV 号）。"""


class ApiError(BiliDLError):
    """B 站接口调用失败（接口报错、风控、画质不可得等）。"""


class DownloadError(BiliDLError):
    """网络、磁盘或音视频合并失败。"""


class CancelledError(BiliDLError):
    """用户通过 cancel 回调取消了下载。"""


__all__ = ["BiliDLError", "InputError", "ApiError", "DownloadError", "CancelledError"]
