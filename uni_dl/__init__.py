"""uni_dl —— 基于 yt-dlp 的通用视频/播放列表解析与下载核心（纯 Python，无 UI）。

约定：
- 所有异常 message 均为可直接展示的中文。
- Cookie 仅经函数参数传入、仅存内存，绝不落盘。
- 进度回调 progress(stage, downloaded, total)，stage 仅用 "video" / "merging" / "done"。
"""

from __future__ import annotations

import base64
import html
import logging
import os
import re
import socket
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import unquote, urlsplit

import requests

try:  # curl_cffi：浏览器 TLS 指纹伪装，用于绕过 Cloudflare 类反爬（可选依赖）
    from curl_cffi import requests as _curl_cffi_requests
except ImportError:  # pragma: no cover - 可选依赖缺失时退回 requests
    _curl_cffi_requests = None

import yt_dlp
from imageio_ffmpeg import get_ffmpeg_exe

__all__ = [
    "parse_input",
    "download_video",
    "has_accelerator",
    "detect_local_proxy",
    "UniversalMeta",
    "UniDLError",
    "UniInputError",
    "UniDownloadError",
    "UniCancelledError",
    "FORMAT_PRESETS",
    "DEFAULT_FORMAT",
]

FORMAT_PRESETS = [
    ("最高可用", "bestvideo*+bestaudio/best"),
    ("最高画质+最佳音质", "bestvideo+bestaudio/best"),
    ("单一文件（免合并）", "best/bestvideo+bestaudio"),
    ("最低画质", "worst"),
]
DEFAULT_FORMAT = FORMAT_PRESETS[0][1]

_BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")

_YHDM_HOST = "yhdmtv.cc"
_YHDM_MEDIA_RE = re.compile(r"[.]m3u8")
_HANIME_HOST = "hanime1.me"
_HANIME_MEDIA_RE = re.compile(r"https://vdownload-\d+\.hembed\.com/[^\"'<> ]+")
_HANIME_QUALITY_RE = re.compile(r"-(\d+)p\.mp4")
_PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}
_PAGE_RETRIES = 3


_ARIA2_REL_PATH = os.path.join("tools", "aria2", "aria2c.exe")
_ARIA2_ARGS = [
    "-x", "8",
    "-s", "8",
    "-k", "1M",
    "--file-allocation=none",
    "--console-log-level=warn",
    "--retry-wait=1",
    "--max-tries=5",
    "--connect-timeout=10",
    "--timeout=20",
]

_PROXY_HOST = "127.0.0.1"
_PROXY_PROBE_TIMEOUT = 0.2
_PROXY_CANDIDATES = (
    (12334, "http"),
    (7890, "http"),
    (7891, "socks5"),
    (10809, "http"),
    (10808, "socks5"),
    (1080, "socks5"),
    (2080, "http"),
    (8889, "http"),
    (20171, "http"),
)

_MAX_ATTEMPTS = 3
_RERESOLVE_HINTS = ("403", "410", "forbidden", "gone", "expired", "令牌")


def _aria2_candidates() -> list[str]:
    """aria2c.exe 候选路径：打包后的 sys._MEIPASS 优先，其次项目根目录。"""
    paths: list[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(os.path.join(meipass, _ARIA2_REL_PATH))
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths.append(os.path.join(project_root, _ARIA2_REL_PATH))
    return paths


def _aria2c_path() -> Optional[str]:
    for path in _aria2_candidates():
        if os.path.isfile(path):
            return path
    return None


def has_accelerator() -> bool:
    """本机是否存在 aria2c.exe（存在即可启用多线程外部下载器）。"""
    return _aria2c_path() is not None


def detect_local_proxy() -> Optional[str]:
    """探测本机常见代理端口，返回第一个可连接的代理 URL；全部不可用返回 None。"""
    for port, scheme in _PROXY_CANDIDATES:
        sock = None
        try:
            sock = socket.create_connection((_PROXY_HOST, port), timeout=_PROXY_PROBE_TIMEOUT)
        except Exception:
            continue
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        return f"{scheme}://{_PROXY_HOST}:{port}"
    return None


def _proxy_url(proxy: Optional[str]) -> Optional[str]:
    """规范化代理参数：空白字符串视为未设置。"""
    if proxy is None:
        return None
    if not isinstance(proxy, str):
        raise UniInputError("代理参数无效：应为字符串，例如 http://127.0.0.1:7890")
    return proxy.strip() or None


def _request_proxies(proxy: Optional[str]) -> Optional[dict]:
    return {"http": proxy, "https": proxy} if proxy else None


_IMPERSONATE_TARGETS = ("chrome", "edge")


def _fetch_impersonated(
    url: str, headers: dict, proxies: Optional[dict], validate: Optional[Callable[[str], bool]] = None
) -> Any:
    """用 curl_cffi 浏览器指纹伪装抓页面；通过内容校验的 200 响应才返回。"""
    if _curl_cffi_requests is None:
        return None
    for target in _IMPERSONATE_TARGETS:
        try:
            resp = _curl_cffi_requests.get(
                url, headers=headers, impersonate=target, proxies=proxies, timeout=30
            )
        except Exception:
            continue
        if getattr(resp, "status_code", 0) != 200:
            continue
        text = getattr(resp, "text", "") or ""
        if validate is None or validate(text):
            return resp
    return None


def _fetch_page(
    url: str,
    proxy: Optional[str] = None,
    referer: str = "",
    validate: Optional[Callable[[str], bool]] = None,
) -> Any:
    """抓取站点页面：先 curl_cffi 伪装（可选），再 requests；内容校验失败也会重试。"""
    headers = dict(_PAGE_HEADERS)
    if referer:
        headers["Referer"] = referer
    proxy = _proxy_url(proxy)
    last_exc: Optional[Exception] = None
    last_resp: Any = None

    def _attempt(with_proxy: Optional[str]) -> Any:
        nonlocal last_exc, last_resp
        proxies = _request_proxies(with_proxy)
        kwargs: dict = {"headers": headers, "timeout": (10, 20)}
        if proxies:
            kwargs["proxies"] = proxies
        for attempt in range(_PAGE_RETRIES):
            impersonated = _fetch_impersonated(url, headers, proxies, validate)
            if impersonated is not None:
                return impersonated
            try:
                resp = requests.get(url, **kwargs)
            except requests.RequestException as exc:
                last_exc = exc
            else:
                last_resp = resp
                text = getattr(resp, "text", "") or ""
                if getattr(resp, "status_code", 0) == 200 and (validate is None or validate(text)):
                    return resp
            if attempt < _PAGE_RETRIES - 1:
                time.sleep(0.3 * (attempt + 1))
        return None

    found = _attempt(proxy)
    if found is not None:
        return found
    if proxy:
        # 代理不可用时兜底直连，避免因代理失效导致整次解析失败
        found = _attempt(None)
        if found is not None:
            return found
    if last_resp is not None:
        return last_resp
    raise UniDownloadError(
        f"解析失败：无法访问站点页面（{last_exc.__class__.__name__ if last_exc else '页面未返回有效内容'}），请重试或更换代理"
    ) from last_exc


def _resolve_site_media(url: str, proxy: Optional[str] = None) -> Optional[dict]:
    """内置站点预解析：把已知站点页面解析成 yt-dlp 可直接下载的直链。

    返回 None 表示该站点无内置解析，继续走 yt-dlp 原生提取器。
    """
    host = (urlsplit(url).netloc or "").lower().split(":")[0]
    if host == _YHDM_HOST or host.endswith("." + _YHDM_HOST):
        return _resolve_yhdmtv(url, proxy=proxy)
    if host == _HANIME_HOST or host.endswith("." + _HANIME_HOST):
        return _resolve_hanime1(url, proxy=proxy)
    return None


def _resolve_yhdmtv(url: str, proxy: Optional[str] = None) -> dict:
    """yhdmtv.cc：页面内嵌 Base64 编码的 m3u8 直链，yt-dlp 原生无法识别。"""
    resp = _fetch_page(url, proxy=proxy, validate=lambda text: bool(_YHDM_MEDIA_RE.search(text) or "curPlaylineId" in text))
    if resp.status_code != 200:
        raise UniDownloadError(f"解析失败：站点页面请求失败（HTTP {resp.status_code}）")
    media_url, episode = _extract_yhdmtv_media(resp.text)
    if not media_url:
        raise UniDownloadError("解析失败：未在该页面找到视频源")
    drama = ""
    matched = re.search(r"《([^》]+)》", resp.text)
    if matched:
        drama = matched.group(1).strip()
    title = f"{drama} {episode}".strip() if drama else (episode or "视频")
    return {"media_url": media_url, "title": title, "extractor": "yhdmtv"}


def _resolve_hanime1(url: str, proxy: Optional[str] = None) -> dict:
    """hanime1.me：页面直出 vdownload 签名直链；yt-dlp 会被 Cloudflare 403，故自行抓页面。"""
    resp = _fetch_page(
        url, proxy=proxy, referer="https://hanime1.me/", validate=lambda text: bool(_HANIME_MEDIA_RE.search(text))
    )
    if resp.status_code == 403:
        raise UniDownloadError("解析失败：站点启用了 Cloudflare 反爬，请稍后重试或在“代理”中选择可用代理")
    if resp.status_code != 200:
        raise UniDownloadError(f"解析失败：站点页面请求失败（HTTP {resp.status_code}）")
    candidates = _hanime_media_candidates(resp.text)
    if not candidates:
        raise UniDownloadError("解析失败：未在该页面找到视频源")
    media_url = max(candidates, key=_hanime_quality_rank)
    return {"media_url": media_url, "title": _hanime_page_title(resp.text), "extractor": "hanime1"}


def _hanime_media_candidates(page: str) -> list[str]:
    seen: list[str] = []
    for raw in _HANIME_MEDIA_RE.findall(page):
        value = html.unescape(raw).rstrip(");,")
        if value not in seen:
            seen.append(value)
    return seen


def _hanime_quality_rank(media_url: str) -> int:
    matched = _HANIME_QUALITY_RE.search(media_url)
    return int(matched.group(1)) if matched else 0


def _hanime_page_title(page: str) -> str:
    matched = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    if not matched:
        return "视频"
    title = html.unescape(matched.group(1)).replace("\xa0", " ").strip()
    title = re.split(r"\s+-\s+", title, maxsplit=1)[0].strip()
    return title or "视频"


def _extract_yhdmtv_media(page_html: str) -> tuple[str, str]:
    """从 yhdmtv.cc 页面提取当前集的 m3u8 直链与集数名。"""
    media_url = ""
    episode = ""
    cur = re.search(r"var\s+curPlaylineId\s*=\s*[\"'](\d+)[\"']", page_html)
    if cur:
        cur_id = cur.group(1)
        id_pos = page_html.find('"id":' + cur_id)
        if id_pos != -1:
            files_before = re.findall(r'"file":"([^"]+)"', page_html[:id_pos])
            if files_before:
                media_url = _decode_yhdmtv_file(files_before[-1])
            tail = page_html[id_pos + len('"id":' + cur_id): id_pos + 800]
            name = re.search(r'"name":"([^"]+)"', tail)
            if name:
                episode = name.group(1)
    if not media_url:
        matched = re.search(r"https?://[^\"'<> ]+?[.]m3u8[^\"'<> ]*", page_html)
        if matched:
            value = matched.group(0)
            media_url = unquote(value.split("url=", 1)[1]) if "url=" in value else value
            name = re.search(r"var\s+[A-Za-z_][A-Za-z0-9_]*player\s*=\s*\{[^}]*?name:\s*'([^']+)'", page_html)
            if name:
                episode = name.group(1)
    return media_url, episode


def _decode_yhdmtv_file(raw: str) -> str:
    """file 字段 = 3 位随机前缀 + Base64(URL编码的播放地址)。"""
    if len(raw) <= 3:
        return ""
    payload = raw[3:]
    pad = (-len(payload)) % 4
    try:
        decoded = base64.b64decode(payload + "=" * pad, validate=False)
        return unquote(decoded.decode("utf-8", "replace"))
    except Exception:
        return ""

_log = logging.getLogger("uni_dl")
if not _log.handlers:
    _log.addHandler(logging.NullHandler())


class UniDLError(Exception):
    """uni_dl 统一异常基类。"""


class UniInputError(UniDLError):
    """输入非法。"""


class UniDownloadError(UniDLError):
    """解析/下载失败（页面找不到视频、站点不支持、网络失败、合并失败等）。"""


class UniCancelledError(UniDLError, yt_dlp.utils.DownloadCancelled):
    """用户取消下载；同时继承 yt-dlp 的 DownloadCancelled 以保证取消能穿透其播放列表循环。"""


@dataclass
class UniversalMeta:
    url: str = ""
    title: str = ""
    uploader: str = ""
    duration: float = 0
    is_playlist: bool = False
    entry_count: int = 1
    webpage_url: str = ""
    extractor: str = ""


class _CollectingLogger:
    """yt-dlp logger 参数适配器：静默所有日志，仅收集错误/警告摘要。"""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def _fmt(self, msg: Any, args: tuple) -> str:
        text = str(msg)
        if args:
            try:
                text = text % args
            except Exception:
                text = " ".join([text, *(str(a) for a in args)])
        return text

    def debug(self, msg: Any, *args: Any) -> None:
        return

    def warning(self, msg: Any, *args: Any) -> None:
        self.warnings.append(self._fmt(msg, args))

    def error(self, msg: Any, *args: Any) -> None:
        self.errors.append(self._fmt(msg, args))


_ERROR_HINTS = (
    (("unsupported url", "unsupported"), "站点暂不支持该链接"),
    (("video unavailable", "no video", "not available"), "页面找不到视频或视频不可用"),
    (("ffmpeg", "merge"), "视频合并/后处理失败"),
    (("http error 410", "410 gone", "gone"), "下载链接已失效（站点令牌过期），已尝试重新解析"),
    (("http error 403", "forbidden"), "站点拒绝访问（可能触发风控或限流，请稍后重试）"),
    (("http error 404", "not found"), "视频不存在或已被删除"),
    (("incompleteread", "connection broken", "incomplete read"), "连接被站点中途断开，已自动分块重试；如仍失败请稍后重试"),
    (("timed out", "timeout", "getaddrinfo", "network", "connection", "reset", "refused"), "网络连接失败，请检查网络后重试"),
    (("cookie",), "Cookie 无效或已过期"),
    (("private", "members-only", "login", "sign in"), "需要登录或账号无权限访问该视频"),
    (("no video formats", "no formats", "format"), "没有可下载的画质/格式"),
)


def _chinese_reason(msg: Any) -> str:
    low = (str(msg) or "").lower()
    for keys, zh in _ERROR_HINTS:
        if any(key in low for key in keys):
            return zh
    return ""


def _to_chinese(prefix: str, msg: Any, fallback: str) -> str:
    return prefix + (_chinese_reason(msg) or fallback)


def _should_re_resolve(detail: Any) -> bool:
    """错误是否像“直链令牌过期/被拒”，值得重新解析页面拿新直链。"""
    low = str(detail or "").lower()
    return any(hint in low for hint in _RERESOLVE_HINTS)


def _re_resolve_media(page_url: str, proxy: Optional[str] = None) -> Optional[str]:
    """用内置站点解析器重新解析页面，返回新的媒体直链；无法重新解析返回 None。"""
    if not page_url:
        return None
    try:
        resolved = _resolve_site_media(page_url, proxy=proxy)
    except UniDLError:
        _log.debug("重新解析页面失败：%s", page_url, exc_info=True)
        return None
    except Exception:
        _log.debug("重新解析页面异常：%s", page_url, exc_info=True)
        return None
    if not resolved:
        return None
    media_url = resolved.get("media_url")
    return media_url if isinstance(media_url, str) and media_url else None


def _cookie_params(cookie: Optional[dict]) -> dict:
    """把 uni_dl 的 cookie 参数形态转换为 yt-dlp 参数；Cookie 仅存内存，绝不落盘。"""
    if cookie is None:
        return {}
    if not isinstance(cookie, dict):
        raise UniInputError('Cookie 参数无效：应为 dict，例如 {"cookiefile": "<cookies.txt 路径>"} 或 {"browser": "<浏览器名>"}')
    if "cookiefile" in cookie and "browser" in cookie:
        raise UniInputError("Cookie 参数无效：cookiefile 与 browser 只能提供其一")
    if "cookiefile" in cookie:
        path = cookie.get("cookiefile")
        if not isinstance(path, str) or not path.strip():
            raise UniInputError("Cookie 文件路径无效：cookiefile 应为非空字符串")
        return {"cookiefile": path}
    if "browser" in cookie:
        browser = cookie.get("browser")
        if not isinstance(browser, str) or browser not in _BROWSERS:
            raise UniInputError(f"浏览器名无效：{browser}（支持：{'、'.join(_BROWSERS)}）")
        return {"cookiesfrombrowser": (browser, None, None, None)}
    raise UniInputError('Cookie 参数无效：仅支持 {"cookiefile": "<cookies.txt 路径>"} 或 {"browser": "<chrome|edge|firefox|brave|opera|vivaldi>"}')


def _close_without_saving_cookies(ydl: Any) -> None:
    """关闭 yt-dlp 实例，但禁止其把内存 cookiejar 写回磁盘。"""
    try:
        ydl.save_cookies = lambda: None
    except Exception:
        pass
    ydl.close()


def _is_http_url(text: str) -> bool:
    return urlsplit(text).scheme.lower() in ("http", "https")


def _meta_from_info(info: dict, url: str) -> UniversalMeta:
    is_playlist = info.get("_type") in ("playlist", "multi_video")
    entries = info.get("entries")
    if is_playlist:
        if entries is None:
            entry_count = 1
        else:
            try:
                entry_count = len(entries)
            except TypeError:
                entry_count = sum(1 for _ in entries)
    else:
        entry_count = 1
    return UniversalMeta(
        url=url,
        title=info.get("title") or "",
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=info.get("duration") or 0,
        is_playlist=is_playlist,
        entry_count=entry_count,
        webpage_url=info.get("webpage_url") or url,
        extractor=info.get("extractor_key") or info.get("extractor") or "",
    )


def parse_input(text: str, cookie: Optional[dict] = None, proxy: Optional[str] = None) -> UniversalMeta:
    """解析任意 http/https 链接（单视频或播放列表），返回通用元数据。"""
    if not isinstance(text, str):
        raise UniInputError("输入无效：请提供视频或播放列表链接")
    url = text.strip()
    if not url:
        raise UniInputError("输入无效：请提供视频或播放列表链接")
    if not _is_http_url(url):
        raise UniInputError("输入无效：仅支持 http/https 链接")
    proxy = _proxy_url(proxy)

    resolved = _resolve_site_media(url, proxy=proxy)
    target_url = resolved["media_url"] if resolved else url

    params: dict = {"quiet": True, "no_warnings": True, "logger": _CollectingLogger()}
    params.update(_cookie_params(cookie))
    if proxy:
        params["proxy"] = proxy

    try:
        ydl = yt_dlp.YoutubeDL(params)
    except UniDLError:
        raise
    except Exception as exc:
        raise UniInputError("解析失败：无法初始化下载器") from exc

    info: Any = None
    try:
        info = ydl.extract_info(target_url, download=False, process=True)
    except UniDLError:
        raise
    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as exc:
        if not resolved:
            raise UniDownloadError(_to_chinese("解析失败：", exc, "网络异常或站点不可用")) from exc
        _log.debug("站点直链补充信息失败，回退站点元数据：%s", exc, exc_info=True)
    except Exception as exc:
        if not resolved:
            raise UniDownloadError(_to_chinese("解析失败：", exc, "网络异常或站点不可用")) from exc
        _log.debug("站点直链补充信息异常，回退站点元数据：%s", exc, exc_info=True)
    finally:
        try:
            _close_without_saving_cookies(ydl)
        except Exception:
            _log.debug("关闭 yt-dlp 解析实例失败", exc_info=True)

    if not isinstance(info, dict):
        if not resolved:
            raise UniDownloadError("解析失败：未获取到视频信息")
        return UniversalMeta(
            url=target_url,
            title=resolved.get("title") or "视频",
            is_playlist=False,
            entry_count=1,
            webpage_url=url,
            extractor=resolved.get("extractor") or "",
        )
    meta = _meta_from_info(info, target_url)
    if resolved:
        if resolved.get("title"):
            meta.title = resolved["title"]
        meta.webpage_url = url
        meta.extractor = resolved.get("extractor") or meta.extractor
    return meta


def download_video(
    meta: UniversalMeta,
    format_sel: Optional[str] = None,
    save_dir: str = ".",
    cookie: Optional[dict] = None,
    proxy: Optional[str] = None,
    accelerator: bool = True,
    progress: Optional[Callable[[str, int, int], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> list[str]:
    """下载 meta 对应的单视频或播放列表，返回成功条目的绝对路径列表。

    最多尝试 3 次：外部下载器（aria2c 多线程）→ 内置下载器 → 重新解析直链后内置下载器。
    """
    url = getattr(meta, "url", None)
    if not isinstance(url, str) or not url.strip():
        raise UniInputError("下载失败：视频元数据缺少有效链接")
    url = url.strip()
    if not _is_http_url(url):
        raise UniInputError("下载失败：仅支持 http/https 链接")
    if format_sel is None:
        format_sel = DEFAULT_FORMAT
    if not isinstance(format_sel, str) or not format_sel.strip():
        raise UniInputError("下载失败：画质/格式选择无效")
    proxy = _proxy_url(proxy)

    try:
        save_dir = os.path.expanduser(os.fspath(save_dir))
    except TypeError as exc:
        raise UniInputError("下载失败：保存目录无效") from exc
    try:
        os.makedirs(save_dir, exist_ok=True)
    except OSError as exc:
        raise UniDownloadError(f"下载失败：无法创建保存目录 {save_dir}") from exc

    state: dict = {"files": [], "cancelled": False, "done": set()}

    def _check_cancel() -> None:
        if cancel is not None and cancel():
            state["cancelled"] = True
            raise UniCancelledError("下载已取消")

    def _progress_hook(status: dict) -> None:
        _check_cancel()
        if progress is None:
            return
        if status.get("status") == "downloading":
            downloaded = int(status.get("downloaded_bytes") or 0)
            total = int(status.get("total_bytes") or status.get("total_bytes_estimate") or 0)
            progress("video", downloaded, total)

    def _postprocessor_hook(status: dict) -> None:
        _check_cancel()
        if progress is None:
            return
        if status.get("status") == "started":
            progress("merging", 0, 0)

    def _post_hook(filename: str) -> None:
        _check_cancel()
        path = os.path.abspath(filename)
        state["files"].append(path)
        if progress is None or path in state["done"]:
            return
        state["done"].add(path)
        try:
            size = int(os.path.getsize(filename))
        except OSError:
            size = 0
        progress("done", size, size)

    def _build_params(collector: _CollectingLogger, use_accel: bool) -> dict:
        params: dict = {
            "format": format_sel,
            "outtmpl": os.path.join(save_dir, "%(title)s [%(id)s].%(ext)s"),
            "merge_output_format": "mp4",
            "ffmpeg_location": get_ffmpeg_exe(),
            "noplaylist": False,
            "ignoreerrors": True,
            "logger": collector,
            "noprogress": True,
            "socket_timeout": 30,
            "retries": 10,
            "continuedl": True,
            "http_chunk_size": 10 * 1024 * 1024,
            "progress_hooks": [_progress_hook],
            "postprocessor_hooks": [_postprocessor_hook],
            "post_hooks": [_post_hook],
        }
        params.update(_cookie_params(cookie))
        if proxy:
            params["proxy"] = proxy
        aria2c = _aria2c_path() if use_accel else None
        if aria2c:
            params["external_downloader"] = {"http": aria2c}
            params["external_downloader_args"] = {"aria2c": list(_ARIA2_ARGS)}
        return params

    def _run_attempt(target_url: str, use_accel: bool) -> str:
        """执行一次下载，返回错误摘要（空字符串表示本次未记录错误）。"""
        collector = _CollectingLogger()
        params = _build_params(collector, use_accel)
        try:
            ydl = yt_dlp.YoutubeDL(params)
        except UniDLError:
            raise
        except Exception as exc:
            raise UniDownloadError("下载失败：无法初始化下载器") from exc
        detail = ""
        try:
            ydl.download([target_url])
        except UniCancelledError:
            raise
        except yt_dlp.utils.DownloadError as exc:
            detail = str(exc)
        except Exception as exc:
            detail = str(exc)
        finally:
            try:
                _close_without_saving_cookies(ydl)
            except Exception:
                _log.debug("关闭 yt-dlp 下载实例失败", exc_info=True)
        _check_cancel()
        return "\n".join(part for part in [detail, *collector.errors] if part.strip())

    use_accel = bool(accelerator) and has_accelerator()
    attempt_url = url
    error_lines: list[str] = []
    attempts = 0
    while attempts < _MAX_ATTEMPTS:
        _check_cancel()
        attempts += 1
        detail = _run_attempt(attempt_url, use_accel)
        if detail:
            error_lines.extend(line for line in detail.splitlines() if line.strip())
        if state["files"] or attempts >= _MAX_ATTEMPTS:
            break
        if attempts == 1:
            use_accel = False  # 第 2 次：外部下载器失败则回退内置下载器
            continue
        if not _should_re_resolve("\n".join(error_lines)):
            break
        new_url = _re_resolve_media(getattr(meta, "webpage_url", "") or "", proxy)
        if not new_url:
            break
        attempt_url = new_url  # 第 3 次：令牌过期后重新解析直链，用内置下载器下载
        use_accel = False

    if state["cancelled"]:
        raise UniCancelledError("下载已取消")
    if not state["files"]:
        for detail in error_lines[-3:]:
            _log.warning("yt-dlp 下载错误：%s", detail)
        reason = ""
        for detail in reversed(error_lines):
            reason = _chinese_reason(detail)
            if reason:
                break
        raise UniDownloadError(f"下载失败：{reason or '未获取到任何文件（可能被站点拒绝、链接已失效或触发风控）'}")
    return list(dict.fromkeys(state["files"]))
