"""B 站 wbi 签名：nav 取密钥对派生 mixin_key，按官方算法对参数排序、过滤特殊字符后 md5。"""
import hashlib
import time
import urllib.parse

from .errors import ApiError
from .net import http_get_json, make_headers

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_FILTER_CHARS = "!'()*"
_CACHE_TTL_SECONDS = 3600
_mixin_key_cache = None  # (mixin_key, fetched_at)


def mixin_key_from(img_url, sub_url):
    """按官方算法由 img_url/sub_url 的文件名派生 mixin_key。"""
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def get_mixin_key(cookie=None):
    """调用 nav 接口获取 wbi 密钥对并派生 mixin_key（进程内缓存，1 小时 TTL）。"""
    global _mixin_key_cache
    if _mixin_key_cache is not None and time.time() - _mixin_key_cache[1] < _CACHE_TTL_SECONDS:
        return _mixin_key_cache[0]
    data = http_get_json(NAV_URL, headers=make_headers(cookie), context="获取 wbi 签名密钥")
    wbi_img = ((data or {}).get("data") or {}).get("wbi_img") or {}
    img_url = wbi_img.get("img_url") or ""
    sub_url = wbi_img.get("sub_url") or ""
    if not img_url or not sub_url:
        raise ApiError("获取 wbi 签名密钥失败：接口未返回 img_url/sub_url")
    _mixin_key_cache = (mixin_key_from(img_url, sub_url), time.time())
    return _mixin_key_cache[0]


def wbi_sign(params, mixin_key):
    """官方签名算法：加 wts、按 key 升序、过滤值中的 !'()* 字符、urlencode 后 md5。"""
    signed = {str(key): str(value) for key, value in params.items()}
    signed["wts"] = str(int(time.time()))
    ordered = {key: signed[key] for key in sorted(signed)}
    cleaned = {key: "".join(ch for ch in value if ch not in _FILTER_CHARS) for key, value in ordered.items()}
    query = urllib.parse.urlencode(cleaned)
    w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return f"{query}&w_rid={w_rid}"
