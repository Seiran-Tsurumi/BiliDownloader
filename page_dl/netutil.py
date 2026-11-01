"""page_dl 网络小工具：浏览器请求头、代理映射与错误描述。"""

from __future__ import annotations

from typing import Dict, Optional

from .errors import PageInputError

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en;q=0.7"


def page_headers(cookie: str = "", referer: str = "") -> Dict[str, str]:
    """浏览器风格的页面抓取请求头。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": _ACCEPT,
        "Accept-Language": _ACCEPT_LANGUAGE,
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    if cookie:
        headers["Cookie"] = cookie
    return headers


def media_headers(referer: str = "") -> Dict[str, str]:
    """媒体文件下载请求头（带 Referer 以通过防盗链）。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": _ACCEPT_LANGUAGE,
        "Accept-Encoding": "identity",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def proxy_map(proxy: Optional[str]) -> Optional[Dict[str, str]]:
    """把单个代理地址转换为 requests 的 proxies 字典；空值返回 None。"""
    if proxy is None:
        return None
    if not isinstance(proxy, str):
        raise PageInputError("代理参数无效：proxy 应为字符串，例如 http://127.0.0.1:7890")
    text = proxy.strip()
    if not text:
        return None
    return {"http": text, "https": text}


def describe_error(exc: BaseException) -> str:
    """把异常转成一行中文可读描述。"""
    text = str(exc).strip().replace("\n", " ")
    if not text:
        text = exc.__class__.__name__
    return text[:160]


__all__ = ["USER_AGENT", "page_headers", "media_headers", "proxy_map", "describe_error"]
