"""输入解析：识别播放页 URL 或裸 BV 号，再调用 view 接口取元数据。"""
import re
from urllib.parse import urlsplit

from .api import fetch_view
from .errors import InputError

# B 站 BV 号字符集：0-9A-Za-z 去掉 0、I、O、l（大小写敏感，前缀必须为大写 BV）
_BV_BODY = r"[1-9A-HJ-NP-Za-km-z]{10}"
BV_RE = re.compile(rf"^BV{_BV_BODY}$")
_VIDEO_PATH_RE = re.compile(rf"^/video/(BV{_BV_BODY})/?$")


def parse_input(text):
    if not isinstance(text, str):
        raise InputError("输入无效：请提供 B 站视频链接或 BV 号")
    text = text.strip()
    if not text:
        raise InputError("请输入 B 站视频链接或 BV 号")
    if "://" in text:
        bvid = _extract_from_url(text)
    elif BV_RE.match(text):
        bvid = text
    else:
        raise InputError("无法识别输入：请提供视频播放页完整链接（https://www.bilibili.com/video/BV...）或 BV 号")
    return fetch_view(bvid)


def _extract_from_url(text):
    parts = urlsplit(text)
    host = (parts.netloc or "").lower()
    path = parts.path or "/"
    lowered = path.lower()
    if host != "www.bilibili.com":
        if host == "space.bilibili.com":
            raise InputError("暂不支持用户主页/空间链接，请打开单个视频页面")
        if host == "live.bilibili.com":
            raise InputError("暂不支持直播链接，请使用普通单视频链接")
        if host == "bangumi.bilibili.com":
            raise InputError("暂不支持番剧/影视链接，请使用普通单视频链接")
        if host.endswith("b23.tv"):
            raise InputError("暂不支持短链接，请使用 www.bilibili.com 的完整视频链接")
        raise InputError("仅支持 www.bilibili.com 的视频播放页链接")
    if "/list" in lowered or "medialist" in lowered or "collection" in lowered:
        raise InputError("暂不支持合集/列表链接，请打开合集中的单个视频页面")
    if "/cheese" in lowered:
        raise InputError("暂不支持课程内容，请使用普通单视频链接")
    if "/bangumi" in lowered:
        raise InputError("暂不支持番剧/影视内容，请使用普通单视频链接")
    if "/live" in lowered:
        raise InputError("暂不支持直播内容，请使用普通单视频链接")
    match = _VIDEO_PATH_RE.match(path)
    if not match:
        raise InputError("仅支持单视频播放页链接：https://www.bilibili.com/video/BV...")
    return match.group(1)
