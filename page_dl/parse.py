"""page_dl.parse —— 页面抓取与媒体条目解析（标准库 html.parser，不依赖 bs4/lxml）。"""

from __future__ import annotations

import html
import logging
import os
import re
import time
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from .errors import PageDownloadError, PageInputError
from .models import MediaItem, PageBundle
from .naming import classify_ext, ext_of_url, filename_from_url, is_downloadable_ext, is_media_ext
from .netutil import describe_error, page_headers, proxy_map

__all__ = ["parse_page"]

try:  # curl_cffi：浏览器 TLS 指纹伪装（可选依赖，缺失时回退 requests）
    from curl_cffi import requests as _curl_cffi_requests
except ImportError:  # pragma: no cover - 可选依赖缺失时回退 requests
    _curl_cffi_requests = None

_log = logging.getLogger(__name__)

_PAGE_ATTEMPTS = 3  # 首次 + 重试 2 次
_RETRY_DELAY = 0.5
_TIMEOUT = (10, 30)

#: 这些前缀的链接直接跳过（内联数据、脚本、邮件、锚点等）
_SKIP_PREFIXES = ("data:", "javascript:", "mailto:", "tel:", "blob:", "about:", "#")

_CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_SEP_RUN_RE = re.compile(r"\s*[-_|｜—–·~]{2,}\s*")
_TITLE_EDGE_RE = re.compile(r"^[\s\-_|｜—–·~]+|[\s\-_|｜—–·~]+$")

#: <img> 上可能承载图片地址的属性
_IMG_ATTRS = ("src", "data-src", "data-original", "data-lazy-src", "data-echo")
#: Discuz 等站点的懒加载大图属性（优先于 src 占位图）
_IMG_LAZY_ATTRS = ("zoomfile", "data-zoomfile", "file", "data-file")
#: 站点 UI 资源路径（Discuz 等）：主题图标、表情、头像、插件图片，不属于页面内容
_UI_PATH_HINTS = (
    "/static/image/",
    "/template/",
    "/source/plugin/",
    "/uc_server/avatar",
    "/data/avatar/",
)

#: 同一图片的缩略图/尺寸变体后缀（用于去重）
_VARIANT_RE = re.compile(
    r"\.(?:thumb|small|big|middle|\d+x\d+)\.(?:jpe?g|png|gif|webp|bmp|avif)$", re.IGNORECASE
)


class _PageHTMLParser(HTMLParser):
    """收集页面内的候选媒体地址，保持出现顺序。

    candidates 的每项为 (原始地址, 是否仅接受常见媒体扩展名)：
    <a href> 只有在扩展名属于常见媒体时才收，其它来源全收（未知类型归 other）。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: List[Tuple[str, bool]] = []
        self._title_parts: List[str] = []
        self._style_parts: List[str] = []
        self._in_title = False
        self._in_style = False

    @property
    def title(self) -> str:
        return "".join(self._title_parts)

    # -- 收集 -----------------------------------------------------------
    def _add(self, value: Optional[str], anchor_only: bool = False) -> None:
        if not value:
            return
        text = str(value).strip()
        if text:
            self.candidates.append((text, anchor_only))

    def _add_srcset(self, value: Optional[str], anchor_only: bool = False) -> None:
        if not value:
            return
        for part in str(value).split(","):
            piece = part.strip()
            if piece:
                self._add(piece.split()[0], anchor_only)

    def _add_css(self, text: str) -> None:
        if not text:
            return
        for match in _CSS_URL_RE.finditer(text):
            self._add(match.group(2))

    # -- HTMLParser 回调 -------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        values: Dict[str, str] = {}
        for key, value in attrs:
            if value is not None and key not in values:
                values[key] = value

        if tag == "img":
            lazy = next((values.get(key) for key in _IMG_LAZY_ATTRS if values.get(key)), None)
            if lazy:
                # 懒加载站点：src 常是占位图，优先取 file/zoomfile 的真实地址
                self._add(lazy)
            else:
                for key in _IMG_ATTRS:
                    self._add(values.get(key))
                self._add_srcset(values.get("srcset"))
        elif tag in ("source", "picture"):
            self._add(values.get("src"))
            self._add_srcset(values.get("srcset"))
        elif tag == "video":
            self._add(values.get("src"))
            self._add(values.get("poster"))
        elif tag == "audio":
            self._add(values.get("src"))
        elif tag == "a":
            self._add(values.get("href"), anchor_only=True)
        elif tag == "title":
            self._in_title = True
        elif tag == "style":
            self._in_style = True
            self._style_parts = []

        self._add_css(values.get("style", ""))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "style":
            if self._in_style:
                self._add_css("".join(self._style_parts))
            self._in_style = False
            self._style_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_style:
            self._style_parts.append(data)

    def finish(self) -> None:
        """收尾：处理未闭合的 <style>。"""
        if self._in_style:
            self._add_css("".join(self._style_parts))
            self._in_style = False
            self._style_parts = []
        self._in_title = False


# -- 参数校验 ---------------------------------------------------------------
def _validate_url(url: object) -> str:
    if not isinstance(url, str) or not url.strip():
        raise PageInputError("页面地址无效：请输入 http/https 链接")
    text = url.strip()
    try:
        parts = urlsplit(text)
    except ValueError as exc:
        raise PageInputError(f"页面地址无效：{text}") from exc
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        raise PageInputError("页面地址无效：仅支持 http/https 链接")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _validate_max_items(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PageInputError("max_items 无效：应为正整数")
    return int(value)


def _cookie_file(cookie: object) -> Optional[str]:
    """校验 cookie 参数：None 或 {"cookiefile": "<Netscape cookies.txt 路径>"}。"""
    if cookie is None:
        return None
    if not isinstance(cookie, dict):
        raise PageInputError('Cookie 参数无效：应为 None 或 {"cookiefile": "<cookies.txt 路径>"}')
    extra = set(cookie) - {"cookiefile"}
    if extra:
        raise PageInputError('Cookie 参数无效：仅支持 {"cookiefile": "<cookies.txt 路径>"}')
    path = cookie.get("cookiefile")
    if not isinstance(path, str) or not path.strip():
        raise PageInputError("Cookie 文件路径无效：cookiefile 应为非空字符串")
    target = os.path.expanduser(path.strip())
    if not os.path.isfile(target):
        raise PageInputError(f"Cookie 文件不存在：{target}")
    return target


def _cookie_header(path: str, url: str) -> str:
    """读取 Netscape cookies.txt，仅取与目标域名匹配的 Cookie。"""
    host = (urlsplit(url).hostname or "").lower()
    pairs: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                if line.lower().startswith("#httponly_"):
                    line = line[len("#HttpOnly_"):]
                elif line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) < 7:
                    continue
                domain = fields[0].lstrip(".").lower()
                name, value = fields[5], fields[6]
                if not name:
                    continue
                if domain and host and host != domain and not host.endswith("." + domain):
                    continue
                pairs.append(f"{name}={value}")
    except OSError as exc:
        raise PageInputError(f"读取 Cookie 文件失败：{path}") from exc
    return "; ".join(pairs)


# -- 抓取 -------------------------------------------------------------------
def _response_text(resp) -> str:
    encoding = (getattr(resp, "encoding", None) or "utf-8").lower()
    if encoding in ("iso-8859-1", "latin-1", "ascii"):
        encoding = (getattr(resp, "apparent_encoding", None) or "utf-8").lower()
    content = getattr(resp, "content", None)
    if content is not None:
        try:
            return content.decode(encoding, errors="replace")
        except LookupError:
            return content.decode("utf-8", errors="replace")
    return getattr(resp, "text", "") or ""


def _page_get(url: str, headers: Dict[str, str], proxies: Optional[Dict[str, str]]) -> str:
    """抓取页面：curl_cffi 可用时优先伪装浏览器，失败回退 requests。"""
    if _curl_cffi_requests is not None:
        try:
            resp = _curl_cffi_requests.get(
                url, headers=headers, impersonate="chrome", proxies=proxies, timeout=30
            )
            if 200 <= int(getattr(resp, "status_code", 0)) < 300:
                return _response_text(resp)
        except Exception:  # noqa: BLE001 - 任何失败都回退 requests
            _log.debug("curl_cffi 抓取失败，回退 requests", exc_info=True)

    kwargs: Dict[str, object] = {"headers": headers, "timeout": _TIMEOUT}
    if proxies:
        kwargs["proxies"] = proxies
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return _response_text(resp)


def _fetch_html(url: str, headers: Dict[str, str], proxies: Optional[Dict[str, str]]) -> str:
    last_error: Optional[BaseException] = None
    for attempt in range(_PAGE_ATTEMPTS):
        try:
            return _page_get(url, headers, proxies)
        except Exception as exc:  # noqa: BLE001 - 统一转为中文错误
            last_error = exc
            _log.debug("抓取页面失败（第 %d 次）：%s", attempt + 1, exc)
            if attempt + 1 < _PAGE_ATTEMPTS:
                time.sleep(_RETRY_DELAY)
    reason = describe_error(last_error) if last_error is not None else "未知原因"
    raise PageDownloadError(f"页面抓取失败：{url}（{reason}）") from last_error


# -- 解析 -------------------------------------------------------------------
_LOGIN_URL_HINTS = ("login", "signin", "sign-in", "passport", "auth")
_LOGIN_TITLE_HINTS = ("登录", "登陆", "sign in", "log in", "login")


def _looks_like_login(text: str, url: str, title: str) -> bool:
    """粗判是否被重定向/要求登录：密码框 + URL/标题登录特征。"""
    low_url = (url or "").lower()
    low_title = (title or "").lower()
    low = (text or "").lower()
    url_hint = any(hint in low_url for hint in _LOGIN_URL_HINTS)
    title_hint = any(hint in low_title for hint in _LOGIN_TITLE_HINTS)
    has_password = 'type="password"' in low or "type='password'" in low or "type=password" in low
    return (has_password and (url_hint or title_hint)) or (url_hint and title_hint)


def _clean_title(text: str) -> str:
    value = html.unescape(text or "")
    value = _WS_RE.sub(" ", value)
    value = _SEP_RUN_RE.sub(" ", value)
    value = _WS_RE.sub(" ", value).strip()
    value = _TITLE_EDGE_RE.sub("", value).strip()
    return value


def _resolve(base: str, raw: str) -> Optional[str]:
    """把候选地址解析成绝对 http/https 地址；非法或需跳过的返回 None。"""
    text = html.unescape(raw or "").strip()
    if not text or text.lower().startswith(_SKIP_PREFIXES):
        return None
    try:
        absolute = urljoin(base, text)
        parts = urlsplit(absolute)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _is_ui_asset(url: str) -> bool:
    """按路径判断是否为站点 UI 资源（图标/表情/头像/主题图），这类不打包。"""
    try:
        path = (urlsplit(url).path or "").lower()
    except ValueError:
        return False
    return any(hint in path for hint in _UI_PATH_HINTS)


def _variant_key(url: str) -> str:
    """把 Discuz 类 `x.jpg.thumb.jpg` / `x.jpg.1500x1500.jpg` 归一，避免同图重复下载。"""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    path = _VARIANT_RE.sub("", parts.path)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def _collect(
    candidates: List[Tuple[str, bool]], page_url: str, limit: int
) -> Tuple[List[MediaItem], int]:
    items: List[MediaItem] = []
    seen: Set[str] = set()
    skipped = 0
    for raw, anchor_only in candidates:
        resolved = _resolve(page_url, raw)
        if resolved is None:
            continue
        if _is_ui_asset(resolved):
            continue
        key = _variant_key(resolved)
        if key in seen:
            continue
        ext = ext_of_url(resolved)
        if anchor_only and not is_downloadable_ext(ext):
            continue
        seen.add(key)
        if len(items) >= limit:
            skipped += 1
            continue
        items.append(
            MediaItem(
                url=resolved,
                kind=classify_ext(ext),
                filename=filename_from_url(resolved),
                referer=page_url,
            )
        )
    return items, skipped


def parse_page(
    url: str,
    cookie: Optional[dict] = None,
    proxy: Optional[str] = None,
    max_items: int = 500,
) -> PageBundle:
    """抓取指定页面并解析出所有图片/视频/音频条目。"""
    page_url = _validate_url(url)
    cookie_path = _cookie_file(cookie)
    proxies = proxy_map(proxy)
    limit = _validate_max_items(max_items)

    headers = page_headers(cookie=_cookie_header(cookie_path, page_url) if cookie_path else "")
    text = _fetch_html(page_url, headers, proxies)

    parser = _PageHTMLParser()
    try:
        parser.feed(text)
        parser.close()
        parser.finish()
    except Exception as exc:  # noqa: BLE001 - HTMLParser 极少抛出，兜底为中文错误
        raise PageDownloadError(f"页面解析失败：{page_url}") from exc

    parts = urlsplit(page_url)
    host = parts.hostname or parts.netloc
    title = _clean_title(parser.title) or host
    items, skipped = _collect(parser.candidates, page_url, limit)
    if _looks_like_login(text, page_url, title):
        raise PageDownloadError(
            "该页面需要登录：请在「Cookie 文件」中选择登录后导出的 cookies.txt 再解析"
        )

    counts = {"image": 0, "video": 0, "audio": 0, "other": 0}
    for item in items:
        counts[item.kind] = counts.get(item.kind, 0) + 1

    return PageBundle(
        url=page_url,
        title=title,
        items=items,
        image_count=counts["image"],
        video_count=counts["video"],
        audio_count=counts["audio"],
        other_count=counts["other"],
        skipped=skipped,
    )
