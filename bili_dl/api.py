"""B 站接口：view（元数据）与 playurl（播放流），均带 wbi 签名。Cookie 只经参数传入、仅存内存。"""
from .errors import ApiError
from .models import VideoMeta
from .net import http_get_json, make_headers
from .wbi import get_mixin_key, wbi_sign

VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_URL = "https://api.bilibili.com/x/player/wbi/playurl"


def fetch_view(bvid, cookie=None):
    params = wbi_sign({"bvid": bvid}, get_mixin_key(cookie))
    data = http_get_json(VIEW_URL, params=params, headers=make_headers(cookie), context="获取视频信息")
    if data.get("code") != 0:
        raise ApiError(_view_error_message(data))
    info = data.get("data") or {}
    owner = info.get("owner") or {}
    if not info.get("bvid"):
        raise ApiError("获取视频信息失败：接口未返回有效数据")
    return VideoMeta(
        bvid=str(info.get("bvid")),
        aid=int(info.get("aid") or 0),
        cid=int(info.get("cid") or 0),
        title=str(info.get("title") or ""),
        owner_name=str(owner.get("name") or ""),
        duration=int(info.get("duration") or 0),
    )


def fetch_playurl(meta, qn, cookie=None, fnval="4048"):
    params = wbi_sign(
        {
            "bvid": meta.bvid,
            "cid": str(meta.cid),
            "qn": str(qn),
            "fnval": fnval,
            "fnver": "0",
            "fourk": "1",
        },
        get_mixin_key(cookie),
    )
    data = http_get_json(PLAYURL_URL, params=params, headers=make_headers(cookie), context="获取播放地址")
    if data.get("code") != 0:
        raise ApiError(_playurl_error_message(data))
    return data.get("data") or {}


def _view_error_message(data):
    code = data.get("code")
    message = str(data.get("message") or "")
    if code == -404:
        return "视频不存在或已被删除"
    if code == -403:
        return "没有权限访问该视频（可能是私密视频或地区限制）"
    if code == -352:
        return "B 站风控校验失败，请稍后重试或更换网络环境"
    return f"获取视频信息失败：{message or '未知错误'}（code {code}）"


def _playurl_error_message(data):
    code = data.get("code")
    message = str(data.get("message") or "")
    if code == -404:
        return "视频不存在或已被删除"
    if code == -403:
        return "没有权限访问该视频（可能是私密视频或地区限制）"
    if code == -10403:
        return "该视频为付费/大会员专享内容，无法获取该画质"
    if code == -101:
        return "登录状态已失效，请重新获取 Cookie"
    return f"获取播放地址失败：{message or '未知错误'}（code {code}）"
