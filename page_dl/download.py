"""page_dl.download —— 4 线程并发下载页面媒体，并打包为 ZIP（或目录）。"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlsplit

import requests

from .errors import PageCancelledError, PageDownloadError, PageInputError
from .models import MediaItem, PageBundle
from .naming import (
    KIND_DIRS,
    KIND_OTHER,
    MANIFEST_NAME,
    ext_of_url,
    is_keep_ext,
    sanitize_filename,
    unique_name,
)
from .netutil import describe_error, media_headers, proxy_map
from .parse import _cookie_file, _cookie_header

__all__ = ["download_page"]

_log = logging.getLogger(__name__)

_MAX_WORKERS = 4
_CHUNK_SIZE = 64 * 1024
_TMP_PREFIX = ".pack_tmp_"
_TIMEOUT = (10, 60)
_PROGRESS_STAGES = ("download", "packing", "done")

#: 明显不是媒体内容的 Content-Type（很多站点图片接口会返回这些）
_NON_MEDIA_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/json",
    "text/plain",
    "text/css",
    "application/javascript",
    "text/javascript",
    "application/xml",
    "text/xml",
}
_MEDIA_TYPE_PREFIXES = ("image/", "video/", "audio/")
#: 小于该字节数的图片视为图标/占位，直接跳过
_MIN_IMAGE_BYTES = 4 * 1024
_MEDIA_TYPES_EXTRA = {
    "application/octet-stream",
    "binary/octet-stream",
    "application/mp4",
    "application/x-mpegurl",
    "application/vnd.apple.mpegurl",
}


def _is_media_content_type(content_type: str) -> bool:
    """按响应头判断是否媒体内容；未知/空类型放行，避免误杀。"""
    value = (content_type or "").split(";")[0].strip().lower()
    if not value:
        return True
    if value.startswith(_MEDIA_TYPE_PREFIXES):
        return True
    if value in _MEDIA_TYPES_EXTRA:
        return True
    return value not in _NON_MEDIA_TYPES


# -- 小工具 -----------------------------------------------------------------
def _check_cancel(cancel: Optional[Callable[[], bool]]) -> None:
    if cancel is None:
        return
    try:
        flag = bool(cancel())
    except Exception:  # noqa: BLE001 - 回调异常视为未取消
        _log.debug("cancel 回调异常", exc_info=True)
        return
    if flag:
        raise PageCancelledError("已取消下载")


def _emit(progress: Optional[Callable[[str, int, int], None]], stage: str, done: int, total: int) -> None:
    if progress is None:
        return
    try:
        progress(stage, int(done), int(total))
    except Exception:  # noqa: BLE001 - 进度回调异常不影响下载
        _log.debug("进度回调异常", exc_info=True)


def _silent_remove(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        _log.debug("删除临时文件失败：%s", path, exc_info=True)


def _temp_ext(url: str) -> str:
    ext = ext_of_url(url)
    if not ext or len(ext) > 10 or not ext.isalnum():
        return ""
    return "." + ext


def _content_length(resp) -> int:
    try:
        return max(int((resp.headers or {}).get("Content-Length") or 0), 0)
    except (TypeError, ValueError):
        return 0


# -- 下载 -------------------------------------------------------------------
def _download_all(
    items: Sequence[MediaItem],
    tmpdir: str,
    proxies: Optional[Dict[str, str]],
    progress: Optional[Callable[[str, int, int], None]],
    cancel: Optional[Callable[[], bool]],
    default_referer: str = "",
    cookie_path: Optional[str] = None,
) -> Tuple[List[Optional[str]], Dict[int, str]]:
    """并发下载全部条目；单条失败只记录不中断，取消则整体中断。"""
    paths: List[Optional[str]] = [None] * len(items)
    errors: Dict[int, str] = {}
    lock = threading.Lock()
    stop = threading.Event()
    flags = {"cancelled": False}
    state = {"bytes": 0, "total": 0}

    def worker(index: int, item: MediaItem) -> None:
        if stop.is_set():
            return
        try:
            _check_cancel(cancel)
        except PageCancelledError:
            flags["cancelled"] = True
            stop.set()
            return

        dest = os.path.join(tmpdir, f"{index:04d}{_temp_ext(item.url)}")
        try:
            headers = media_headers(item.referer or default_referer)
            if cookie_path:
                cookie_value = _cookie_header(cookie_path, item.url)
                if cookie_value:
                    headers["Cookie"] = cookie_value
            kwargs: Dict[str, object] = {
                "headers": headers,
                "stream": True,
                "timeout": _TIMEOUT,
            }
            if proxies:
                kwargs["proxies"] = proxies
            resp = requests.get(item.url, **kwargs)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type") or ""
            if not is_keep_ext(ext_of_url(item.url)) and not _is_media_content_type(content_type):
                raise PageDownloadError(
                    f"跳过：非媒体内容（{content_type.split(';')[0].strip()}）"
                )
            if content_type.split(";")[0].strip().lower().startswith("image/"):
                length = _content_length(resp)
                if 0 < length < _MIN_IMAGE_BYTES:
                    raise PageDownloadError(f"跳过：图片过小（{length} 字节）")
            with lock:
                state["total"] += _content_length(resp)

            written = 0
            with open(dest, "wb") as handle:
                for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
                    if not chunk:
                        continue
                    if stop.is_set():
                        raise PageCancelledError("已取消下载")
                    _check_cancel(cancel)
                    handle.write(chunk)
                    written += len(chunk)
                    with lock:
                        state["bytes"] += len(chunk)
                        done, total = state["bytes"], state["total"]
                    _emit(progress, "download", done, max(total, done))
            if written <= 0:
                raise PageDownloadError("响应内容为空")
            paths[index] = dest
        except PageCancelledError:
            flags["cancelled"] = True
            stop.set()
            _silent_remove(dest)
        except Exception as exc:  # noqa: BLE001 - 单条失败跳过
            with lock:
                errors[index] = describe_error(exc)
            _log.debug("下载失败：%s（%s）", item.url, exc)
            _silent_remove(dest)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="page-dl") as pool:
        futures = [pool.submit(worker, index, item) for index, item in enumerate(items)]
        for future in futures:
            try:
                future.result()
            except Exception:  # noqa: BLE001 - 兜底，避免线程异常吞掉整体流程
                _log.debug("下载线程异常", exc_info=True)

    if flags["cancelled"] or stop.is_set():
        raise PageCancelledError("已取消下载")
    return paths, errors


# -- 打包 -------------------------------------------------------------------
def _bundle_base(bundle: PageBundle) -> str:
    """打包名：清理后的标题 + " [host]"。"""
    title = sanitize_filename(bundle.title or "", max_len=80) or "页面"
    host = ""
    try:
        parts = urlsplit(bundle.url)
        host = parts.hostname or parts.netloc or ""
    except ValueError:
        host = ""
    host = sanitize_filename(host, max_len=60) or "page"
    return f"{title} [{host}]"


def _unique_target(root: str, base: str, suffix: str = "") -> str:
    candidate = os.path.join(root, base + suffix)
    index = 1
    while os.path.exists(candidate):
        candidate = os.path.join(root, f"{base} ({index}){suffix}")
        index += 1
    return candidate


def _build_entries(
    bundle: PageBundle,
    items: Sequence[MediaItem],
    paths: Sequence[Optional[str]],
    errors: Dict[int, str],
) -> Tuple[List[Tuple[str, str]], List[str]]:
    """构造 (临时文件, zip 内路径) 列表与清单文本行。"""
    used: Dict[str, Set[str]] = {}
    entries: List[Tuple[str, str]] = []
    manifest: List[str] = []
    for index, item in enumerate(items):
        source = paths[index] if index < len(paths) else None
        folder = KIND_DIRS.get(item.kind, KIND_DIRS[KIND_OTHER])
        suggested = item.filename or ""
        if source is None:
            reason = str(errors.get(index, ""))
            status = "跳过" if reason.startswith("跳过") else "失败"
            manifest.append("\t".join([folder, status, item.url, suggested or "-"]))
            continue
        ext = os.path.splitext(source)[1]
        name = sanitize_filename(suggested) or f"{index + 1}{ext}"
        if ext and not os.path.splitext(name)[1]:
            name = name + ext
        bucket = used.setdefault(folder, set())
        final = unique_name(name, bucket)
        entries.append((source, f"{folder}/{final}"))
        manifest.append("\t".join([folder, "成功", item.url, final]))
    return entries, manifest


def _pack_zip(
    bundle: PageBundle,
    items: Sequence[MediaItem],
    paths: Sequence[Optional[str]],
    errors: Dict[int, str],
    root: str,
    progress: Optional[Callable[[str, int, int], None]],
    cancel: Optional[Callable[[], bool]],
) -> str:
    entries, manifest = _build_entries(bundle, items, paths, errors)
    target = _unique_target(root, _bundle_base(bundle), ".zip")
    _emit(progress, "packing", 0, 0)
    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for source, arcname in entries:
                _check_cancel(cancel)
                archive.write(source, arcname)
            _check_cancel(cancel)
            archive.writestr(MANIFEST_NAME, "\n".join(manifest) + "\n")
    except PageCancelledError:
        _silent_remove(target)
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        _silent_remove(target)
        raise PageDownloadError(f"打包 ZIP 失败：{describe_error(exc)}") from exc
    except BaseException:
        _silent_remove(target)
        raise

    size = os.path.getsize(target)
    _emit(progress, "done", size, size)
    return os.path.abspath(target)


def _pack_dir(
    bundle: PageBundle,
    items: Sequence[MediaItem],
    paths: Sequence[Optional[str]],
    errors: Dict[int, str],
    root: str,
    progress: Optional[Callable[[str, int, int], None]],
    cancel: Optional[Callable[[], bool]],
) -> str:
    entries, manifest = _build_entries(bundle, items, paths, errors)
    target = _unique_target(root, _bundle_base(bundle))
    _emit(progress, "packing", 0, 0)
    total = 0
    try:
        os.makedirs(target, exist_ok=True)
        for source, arcname in entries:
            _check_cancel(cancel)
            dest = os.path.join(target, *arcname.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(source, dest)
            total += os.path.getsize(dest)
        _check_cancel(cancel)
        with open(os.path.join(target, MANIFEST_NAME), "w", encoding="utf-8", newline="") as handle:
            handle.write("\n".join(manifest) + "\n")
    except PageCancelledError:
        shutil.rmtree(target, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise PageDownloadError(f"保存文件失败：{describe_error(exc)}") from exc

    _emit(progress, "done", total, total)
    return os.path.abspath(target)


# -- 对外入口 ---------------------------------------------------------------
def download_page(
    bundle: PageBundle,
    save_dir: str = ".",
    zip_output: bool = True,
    progress: Optional[Callable[[str, int, int], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
    proxy: Optional[str] = None,
    cookie: Optional[dict] = None,
) -> str:
    """下载 bundle 内全部媒体并打包；返回 ZIP 绝对路径（zip_output=False 时返回目录绝对路径）。"""
    if not isinstance(bundle, PageBundle):
        raise PageInputError("bundle 参数无效：应为 PageBundle（可先用 parse_page 解析页面）")
    if not isinstance(save_dir, (str, os.PathLike)):
        raise PageInputError("保存目录无效：save_dir 应为路径字符串")

    items = list(bundle.items or [])
    proxies = proxy_map(proxy)
    cookie_path = _cookie_file(cookie)
    _check_cancel(cancel)
    if not items:
        raise PageDownloadError("未下载到任何媒体文件")

    root = os.path.abspath(os.path.expanduser(os.fspath(save_dir)))
    try:
        os.makedirs(root, exist_ok=True)
    except OSError as exc:
        raise PageDownloadError(f"无法创建保存目录：{root}") from exc

    tmpdir = tempfile.mkdtemp(prefix=_TMP_PREFIX, dir=root)
    try:
        paths, errors = _download_all(
            items, tmpdir, proxies, progress, cancel, bundle.url, cookie_path
        )
        if not any(paths):
            raise PageDownloadError("未下载到任何媒体文件")
        if zip_output:
            return _pack_zip(bundle, items, paths, errors, root, progress, cancel)
        return _pack_dir(bundle, items, paths, errors, root, progress, cancel)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
