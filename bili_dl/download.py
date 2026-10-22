"""画质列表与下载主流程：选流、下载、ffmpeg 封装合并（-c copy，不转码）。"""
import re
import secrets
import subprocess
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe

from .api import fetch_playurl
from .errors import ApiError, DownloadError, InputError
from .models import Quality
from .net import check_cancel, download_segments

_QUALITY_NAMES = {
    127: "8K 超高清",
    126: "杜比视界",
    125: "HDR 真彩",
    120: "4K 超清",
    116: "1080P 60帧",
    112: "1080P 高码率",
    80: "1080P 高清",
    74: "720P 60帧",
    64: "720P 高清",
    32: "480P 清晰",
    16: "360P 流畅",
    6: "240P 极速",
}

_INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
_SESSDATA_RE = re.compile(r"(?:^|;\s*)SESSDATA=([^;]*)")
_CODEC_PREF = {7: 0, 12: 1, 13: 2}


def list_qualities(meta, cookie=None):
    cookie = validate_cookie(cookie)
    data = fetch_playurl(meta, 127, cookie)
    accept_quality = [int(q) for q in (data.get("accept_quality") or [])]
    accept_description = [str(d) for d in (data.get("accept_description") or [])]
    if not accept_quality:
        dash = data.get("dash") or {}
        ids = {int(v.get("id")) for v in (dash.get("video") or []) if v.get("id")}
        if ids:
            accept_quality = sorted(ids, reverse=True)
        elif data.get("quality"):
            accept_quality = [int(data.get("quality"))]
    if not accept_quality:
        raise ApiError("获取可用画质失败：接口未返回画质列表")
    description_map = {}
    if accept_description and len(accept_description) == len(accept_quality):
        description_map = dict(zip(accept_quality, accept_description))
    result = []
    for qn in sorted(set(accept_quality), reverse=True):
        desc = description_map.get(qn) or _QUALITY_NAMES.get(qn) or f"画质 {qn}"
        result.append(Quality(qn=qn, desc=desc))
    return result


def download_video(meta, cookie=None, quality="max", save_dir=".", progress=None, cancel=None):
    check_cancel(cancel)
    cookie = validate_cookie(cookie)
    qn = _resolve_quality_arg(quality)
    if not getattr(meta, "bvid", None) or not getattr(meta, "cid", None):
        raise ApiError("视频信息无效：缺少 bvid/cid，请重新解析视频")
    if progress is not None:
        progress("fetching", 0, 0)

    play = fetch_playurl(meta, 127 if qn is None else qn, cookie)
    fetch_durl = None
    if cookie is None:
        def fetch_durl():
            return fetch_playurl(meta, 127, None, fnval="1")

    choice = _pick_stream(play, qn, cookie is not None, fetch_durl)

    try:
        save_path = Path(save_dir).expanduser()
        save_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise DownloadError(f"无法创建保存目录：{save_dir}")
    output = _final_path(save_path, meta)
    token = secrets.token_hex(4)
    tmp_files = []

    try:
        if choice["mode"] == "dash":
            tmp_video = save_path / f".{meta.bvid}_{meta.cid}_{token}_video.m4s"
            tmp_audio = save_path / f".{meta.bvid}_{meta.cid}_{token}_audio.m4s"
            tmp_files = [tmp_video, tmp_audio]
            _remove(tmp_files)
            download_segments(choice["video_urls"], tmp_video, cookie=cookie, total=choice["video_size"], stage="video", progress=progress, cancel=cancel)
            check_cancel(cancel)
            download_segments(choice["audio_urls"], tmp_audio, cookie=cookie, total=choice["audio_size"], stage="audio", progress=progress, cancel=cancel)
            check_cancel(cancel)
            _merge([tmp_video, tmp_audio], output, progress)
        else:
            tmp_video = save_path / f".{meta.bvid}_{meta.cid}_{token}_video.flv"
            tmp_files = [tmp_video]
            _remove(tmp_files)
            download_segments(choice["segment_urls"], tmp_video, cookie=cookie, total=choice["total_size"], stage="video", progress=progress, cancel=cancel)
            if progress is not None:
                progress("audio", 0, 0)
            check_cancel(cancel)
            _merge([tmp_video], output, progress)
        size = output.stat().st_size
    except BaseException:
        _remove([output])
        raise
    finally:
        _remove(tmp_files)

    if progress is not None:
        progress("done", size, size)
    return output.resolve()


def validate_cookie(cookie):
    """Cookie 只经函数参数传入、仅存内存；无效 SESSDATA 尽早报中文错误。"""
    if cookie is None:
        return None
    if not isinstance(cookie, str):
        raise ApiError("Cookie 无效：应为字符串或 None，请重新获取 Cookie")
    cookie = cookie.strip()
    if not cookie:
        return None
    match = _SESSDATA_RE.search(cookie)
    if match and len(match.group(1).strip()) < 20:
        raise ApiError("Cookie 无效：SESSDATA 值不正确，请重新获取 Cookie")
    return cookie


def _resolve_quality_arg(quality):
    if quality == "max":
        return None
    if isinstance(quality, bool) or not isinstance(quality, int):
        raise InputError("画质参数无效：请传整数 qn 或字符串 \"max\"")
    if quality <= 0:
        raise InputError("画质参数无效：qn 必须为正整数")
    return quality


def _pick_stream(play, qn, has_cookie, fetch_durl=None):
    """优先 DASH；无 Cookie 且 durl 实际提供更高画质时允许回退 durl（按需二次拉取 durl 分段确认）。"""
    dash = play.get("dash") or {}
    videos = [v for v in (dash.get("video") or []) if _entry_url(v)]
    audios = [a for a in (dash.get("audio") or []) if _entry_url(a)]
    durl = play.get("durl") or []
    durl_quality = int(play.get("quality") or 0)
    dash_max = max((int(v.get("id") or 0) for v in videos), default=0)

    if not has_cookie and fetch_durl is not None and durl_quality > dash_max and not durl:
        durl_data = fetch_durl()
        durl = durl_data.get("durl") or []
        durl_quality = int(durl_data.get("quality") or 0)

    if qn is None:
        prefer_durl = not has_cookie and bool(durl) and durl_quality > dash_max
        if videos and not prefer_durl:
            video = _pick_video(videos, None)
            audio = _pick_audio(audios)
            if video is not None and audio is not None:
                return _dash_choice(video, audio)
        if durl:
            return _durl_choice(durl)
        if not videos:
            raise ApiError("未获取到可下载的播放流：该视频可能为付费/番剧/互动内容，或画质受限")
        raise ApiError("未获取到完整的音视频流，该视频可能不支持下载")

    video = _pick_video(videos, qn)
    if video is not None:
        audio = _pick_audio(audios)
        if audio is not None:
            return _dash_choice(video, audio)
        if durl and not has_cookie and durl_quality >= qn:
            return _durl_choice(durl)
        raise ApiError("未获取到音频流，无法下载该视频")
    if durl and not has_cookie and durl_quality >= qn and qn > dash_max:
        return _durl_choice(durl)
    raise ApiError("该画质不可用，请检查登录/会员状态")


def _dash_choice(video, audio):
    return {
        "mode": "dash",
        "video_urls": _entry_urls(video),
        "audio_urls": _entry_urls(audio),
        "video_size": 0,
        "audio_size": 0,
    }


def _durl_choice(durl):
    return {
        "mode": "durl",
        "segment_urls": [str(seg.get("url")) for seg in durl if seg.get("url")],
        "total_size": sum(int(seg.get("size") or 0) for seg in durl),
    }


def _entry_url(entry):
    return bool(entry.get("baseUrl") or entry.get("base_url"))


def _entry_urls(entry):
    base = entry.get("baseUrl") or entry.get("base_url") or ""
    urls = [base] if base else []
    backups = entry.get("backupUrl") or entry.get("backup_url") or []
    urls.extend(u for u in backups if u)
    return urls


def _pick_video(videos, qn):
    candidates = videos if qn is None else [v for v in videos if int(v.get("id") or 0) == qn]
    if not candidates:
        return None
    top = max(int(v.get("id") or 0) for v in candidates)
    candidates = [v for v in candidates if int(v.get("id") or 0) == top]
    candidates.sort(key=lambda v: _CODEC_PREF.get(int(v.get("codecid") or 99), 9))
    return candidates[0]


def _pick_audio(audios):
    if not audios:
        return None

    def preference(entry):
        codecs = str(entry.get("codecs") or "")
        return (0 if codecs.startswith("mp4a") else 1, -int(entry.get("id") or 0))

    return sorted(audios, key=preference)[0]


def _merge(inputs, output, progress):
    """用 imageio_ffmpeg 提供的 ffmpeg 以 -c copy 封装合并，不转码。"""
    if progress is not None:
        progress("merging", 0, 0)
    try:
        ffmpeg = get_ffmpeg_exe()
    except Exception as exc:
        raise DownloadError(f"无法定位 ffmpeg 可执行文件：{exc}") from exc
    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    for item in inputs:
        cmd += ["-i", str(item)]
    cmd += ["-c", "copy", "-movflags", "+faststart", str(output)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=7200)
    except subprocess.TimeoutExpired:
        raise DownloadError("音视频合并超时，请重试")
    except OSError as exc:
        raise DownloadError(f"音视频合并失败：无法启动 ffmpeg（{exc}）") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        tail = detail[-300:] if len(detail) > 300 else detail
        raise DownloadError(f"音视频合并失败：ffmpeg 返回错误：{tail}")


def _final_path(save_dir, meta):
    title = _clean_title(meta.title or meta.bvid)
    stem = f"{title} {meta.bvid}"
    base = save_dir / f"{stem}.mp4"
    if not base.exists():
        return base
    n = 1
    while True:
        candidate = save_dir / f"{stem} ({n}).mp4"
        if not candidate.exists():
            return candidate
        n += 1


def _clean_title(title):
    cleaned = []
    for ch in str(title):
        if ch in _INVALID_FILENAME_CHARS or ord(ch) < 32:
            cleaned.append("_")
        else:
            cleaned.append(ch)
    result = "".join(cleaned).strip().rstrip(" .")
    if len(result) > 180:
        result = result[:180].rstrip(" .")
    return result or "视频"


def _remove(paths):
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
