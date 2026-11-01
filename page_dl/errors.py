"""page_dl 错误类型定义：message 均为可直接展示给用户的中文。"""


class PageDLError(Exception):
    """page_dl 所有错误的基类。"""


class PageInputError(PageDLError):
    """输入/Cookie 参数非法。"""


class PageDownloadError(PageDLError):
    """页面抓取、媒体下载或打包失败。"""


class PageCancelledError(PageDLError):
    """用户通过 cancel 回调取消了下载。"""


__all__ = ["PageDLError", "PageInputError", "PageDownloadError", "PageCancelledError"]
