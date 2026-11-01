"""page_dl 命名工具：媒体分类、文件名清理与重名处理。"""

from __future__ import annotations

import os
import posixpath
import re
from typing import Set
from urllib.parse import unquote, urlsplit

IMAGE_EXTS = frozenset({"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "avif", "ico"})
VIDEO_EXTS = frozenset({"mp4", "webm", "mov", "mkv", "flv", "m4v", "ts"})
AUDIO_EXTS = frozenset({"mp3", "m4a", "aac", "ogg", "wav", "flac", "opus"})

#: 非媒体、但需要保留的附件扩展名（如论坛/Discuz 的 .attach）
EXTRA_KEEP_EXTS = frozenset({"attach"})

KIND_IMAGE = "image"
KIND_VIDEO = "video"
KIND_AUDIO = "audio"
KIND_OTHER = "other"

#: ZIP/目录内按类型分目录
KIND_DIRS = {KIND_IMAGE: "图片", KIND_VIDEO: "视频", KIND_AUDIO: "音频", KIND_OTHER: "其他"}

MANIFEST_NAME = "清单.txt"
MAX_NAME_LEN = 120

_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_WS_RE = re.compile(r"\s+")


def ext_of_url(url: str) -> str:
    """取 URL 路径的扩展名（小写、不含点）；没有则返回空串。"""
    try:
        path = urlsplit(url).path
    except ValueError:
        return ""
    return posixpath.splitext(path)[1].lstrip(".").lower()


def classify_ext(ext: str) -> str:
    """按扩展名分类，未知归 "other"。"""
    value = (ext or "").lower()
    if value in IMAGE_EXTS:
        return KIND_IMAGE
    if value in VIDEO_EXTS:
        return KIND_VIDEO
    if value in AUDIO_EXTS:
        return KIND_AUDIO
    return KIND_OTHER


def is_media_ext(ext: str) -> bool:
    return classify_ext(ext) != KIND_OTHER


def is_keep_ext(ext: str) -> bool:
    """是否为需要保留的非媒体附件扩展名（如 .attach）。"""
    return (ext or "").lower() in EXTRA_KEEP_EXTS


def is_downloadable_ext(ext: str) -> bool:
    """解析阶段是否保留该扩展名的链接：媒体或显式保留的附件。"""
    return is_media_ext(ext) or is_keep_ext(ext)


def sanitize_filename(name: str, max_len: int = MAX_NAME_LEN) -> str:
    """清理文件名：替换非法/控制字符、压缩空白、去首尾点与空白、按上限截断（保留扩展名）。"""
    text = str(name or "")
    text = _ILLEGAL_RE.sub("_", text)
    text = _WS_RE.sub(" ", text).strip().strip(". ")
    if not text:
        return ""
    stem, ext = os.path.splitext(text)
    if len(ext) > 16:  # 太长的“扩展名”视为普通文本，不做保留
        stem, ext = text, ""
    limit = max(int(max_len), 8)
    room = limit - len(ext)
    if room < 1:
        return stem[:limit]
    if len(stem) > room:
        return stem[:room] + ext
    return text


def filename_from_url(url: str) -> str:
    """取 URL 最后一段（已 unquote）并清理；为空则返回空串。"""
    try:
        path = urlsplit(url).path
    except ValueError:
        return ""
    tail = posixpath.basename(unquote(path))
    return sanitize_filename(tail)


def unique_name(name: str, used: Set[str]) -> str:
    """同名时追加 " (1)"、" (2)"……（保留扩展名），并把结果记入 used（小写）。"""
    candidate = name
    stem, ext = os.path.splitext(name)
    index = 1
    while candidate.lower() in used:
        candidate = f"{stem} ({index}){ext}"
        index += 1
    used.add(candidate.lower())
    return candidate


__all__ = [
    "IMAGE_EXTS",
    "VIDEO_EXTS",
    "AUDIO_EXTS",
    "EXTRA_KEEP_EXTS",
    "KIND_IMAGE",
    "KIND_VIDEO",
    "KIND_AUDIO",
    "KIND_OTHER",
    "KIND_DIRS",
    "MANIFEST_NAME",
    "MAX_NAME_LEN",
    "ext_of_url",
    "classify_ext",
    "is_media_ext",
    "is_keep_ext",
    "is_downloadable_ext",
    "sanitize_filename",
    "filename_from_url",
    "unique_name",
]
