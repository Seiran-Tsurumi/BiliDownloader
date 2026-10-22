"""网络基础：请求头、带重试的 JSON 请求与流式下载（逐块检查取消）。"""
import os
import time

import requests

from .errors import ApiError, CancelledError, DownloadError

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REFERER = "https://www.bilibili.com"

_RETRY_TIMES = 2
_CHUNK_SIZE = 64 * 1024


def make_headers(cookie=None):
    headers = {"User-Agent": USER_AGENT, "Referer": REFERER}
    if cookie:
        headers["Cookie"] = cookie
    return headers


def check_cancel(cancel):
    if cancel is not None and cancel():
        raise CancelledError("下载已取消")


def http_get_json(url, params=None, headers=None, context="接口请求"):
    """GET 并解析 JSON；网络失败自动重试 2 次（指数退避 1s/2s），HTTP 412 视为风控。"""
    with requests.Session() as session:
        for attempt in range(_RETRY_TIMES + 1):
            try:
                resp = session.get(url, params=params, headers=headers, timeout=(10, 30))
                if resp.status_code == 412:
                    raise ApiError("请求被 B 站风控拦截（HTTP 412），请稍后重试或更换网络环境")
                if resp.status_code != 200:
                    if resp.status_code >= 500:
                        raise requests.RequestException(f"HTTP {resp.status_code}")
                    raise ApiError(f"{context}失败：HTTP 状态码 {resp.status_code}")
                try:
                    payload = resp.json()
                    if not isinstance(payload, dict):
                        raise requests.RequestException("响应不是 JSON 对象")
                    return payload
                except ValueError:
                    raise requests.RequestException("响应不是合法 JSON")
            except ApiError:
                raise
            except requests.RequestException:
                if attempt < _RETRY_TIMES:
                    time.sleep(2 ** attempt)
    raise ApiError(f"{context}失败：网络异常（已重试 {_RETRY_TIMES} 次），请检查网络后重试")


def download_segments(urls, tmp_path, cookie=None, total=0, stage="video", progress=None, cancel=None):
    """把若干 URL 依次下载/追加进 tmp_path；支持断点续传，每写完一个数据块检查 cancel。"""
    with requests.Session() as session:
        pos = 0
        for url in urls:
            no_range = False
            for attempt in range(_RETRY_TIMES + 1):
                check_cancel(cancel)
                on_disk = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
                headers = make_headers(cookie)
                use_range = not no_range and on_disk > 0
                if use_range:
                    headers["Range"] = f"bytes={on_disk}-"
                try:
                    with session.get(url, headers=headers, stream=True, timeout=(10, 60)) as resp:
                        if resp.status_code == 416 and use_range:
                            # 服务器不支持断点续传：丢弃本段已下部分，从头重试本段
                            no_range = True
                            with open(tmp_path, "r+b") as fh:
                                fh.truncate(pos)
                            raise requests.RequestException("服务器不支持断点续传，回退为重新下载")
                        if resp.status_code not in (200, 206):
                            raise DownloadError(f"下载失败：HTTP 状态码 {resp.status_code}")
                        if resp.status_code == 200:
                            keep = min(pos, on_disk)
                            if on_disk > keep:
                                with open(tmp_path, "r+b") as fh:
                                    fh.truncate(keep)
                            pos = keep
                            mode = "ab" if keep > 0 else "wb"
                        else:
                            pos = on_disk
                            mode = "ab" if on_disk > 0 else "wb"
                        content_length = resp.headers.get("Content-Length")
                        if content_length and content_length.isdigit():
                            if resp.status_code == 200:
                                total = int(content_length)
                            else:
                                total = max(total, pos + int(content_length))
                        with open(tmp_path, mode) as fh:
                            for chunk in resp.iter_content(_CHUNK_SIZE):
                                if not chunk:
                                    continue
                                check_cancel(cancel)
                                fh.write(chunk)
                                pos += len(chunk)
                                if progress is not None:
                                    progress(stage, pos, total)
                    break
                except CancelledError:
                    raise
                except DownloadError:
                    raise
                except requests.RequestException:
                    if attempt < _RETRY_TIMES:
                        time.sleep(2 ** attempt)
                        continue
            else:
                raise DownloadError(f"下载失败：网络异常（已重试 {_RETRY_TIMES} 次），请检查网络后重试")
        return pos
