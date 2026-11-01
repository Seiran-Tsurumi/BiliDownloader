"""tg_dl —— 飞机模式：基于 Telethon 的 Telegram 频道媒体下载核心（纯 Python，无 UI）。

约定：
- 所有异常 message 均为可直接展示的中文。
- 网络调用一律走模块级 TelegramClient（telethon.sync），测试中可用
  mock.patch("tg_dl.TelegramClient") 整体替换，全程离线。
- 进度回调 progress(stage, current, total)，stage 仅用 "download" / "skip" / "done"。
- cancel 支持 threading.Event、无参可调用对象或布尔值。
"""

from __future__ import annotations

import asyncio
import datetime
import inspect
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, List, Optional, Set, Tuple

import qrcode
from telethon import utils as tg_utils
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    SessionPasswordNeededError,
    UnauthorizedError,
)
from telethon.sync import TelegramClient

try:  # python-socks：Telethon 代理的底层实现，缺失时无法使用代理
    from python_socks import ProxyType

    _HAS_PYTHON_SOCKS = True
except ImportError:  # pragma: no cover - 取决于运行环境
    ProxyType = None  # type: ignore[assignment]
    _HAS_PYTHON_SOCKS = False

__all__ = [
    "TgConfig",
    "TgMediaItem",
    "TgChannelInfo",
    "TgDLError",
    "TgInputError",
    "TgAuthError",
    "TgDownloadError",
    "TgCancelledError",
    "qr_login",
    "list_channel_media",
    "download_channel_media",
    "logout",
    "default_session_path",
    "qr_matrix",
]

_MEDIA_KINDS = ("photo", "video", "audio", "document")
_KIND_DIRS = {"photo": "图片", "video": "视频", "audio": "音频", "document": "文件"}
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PROXY_RE = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*)://(?P<host>[^/?#:\s]+):(?P<port>\d{1,5})/?$"
)
_PROXY_TYPES = {"http": "HTTP", "https": "HTTP", "socks5": "SOCKS5", "socks5h": "SOCKS5"}
_FLOOD_WAIT_LIMIT = 60.0
_MAX_NAME_LEN = 120


# --------------------------------------------------------------------------- 异常


class TgDLError(Exception):
    """tg_dl 所有异常的基类，message 为可直接展示的中文。"""


class TgInputError(TgDLError):
    """输入参数或代理参数非法。"""


class TgAuthError(TgDLError):
    """登录、会话或两步验证相关问题。"""

    def __init__(self, message: str, password_required: bool = False) -> None:
        super().__init__(message)
        self.password_required = password_required


class TgDownloadError(TgDLError):
    """网络、限流或下载失败。"""


class TgCancelledError(TgDLError):
    """用户取消。"""


# --------------------------------------------------------------------------- 数据模型


@dataclass
class TgMediaItem:
    """频道中的一条可下载媒体。"""

    message_id: int
    kind: str
    filename: str
    size: int
    date: int


@dataclass
class TgChannelInfo:
    """频道媒体清单。"""

    title: str
    username: str
    total: int
    items: List[TgMediaItem]


# --------------------------------------------------------------------------- 配置与工具


def _validate_api_id(value: Any) -> int:
    if isinstance(value, bool):
        raise TgInputError("api_id 必须是正整数")
    if isinstance(value, int):
        if value <= 0:
            raise TgInputError("api_id 必须是正整数")
        return value
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        if number > 0:
            return number
    raise TgInputError("api_id 必须是正整数")


def _require_text(value: Any, name: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise TgInputError(f"{name} 不能为空")
    return text


def _build_proxy(proxy: Optional[str]) -> Optional[Tuple[Any, str, int]]:
    """把 "http://host:port" / "socks5://host:port" 转成 Telethon 的 proxy 元组。"""
    if proxy is None:
        return None
    raw = str(proxy).strip()
    if not raw:
        return None
    if not _HAS_PYTHON_SOCKS or ProxyType is None:
        raise TgInputError("未安装 python-socks，无法使用代理，请先执行 pip install python-socks")
    match = _PROXY_RE.match(raw)
    if match is None:
        raise TgInputError(
            f"代理格式不正确：{raw}，应形如 http://127.0.0.1:7890 或 socks5://127.0.0.1:1080"
        )
    scheme = match.group("scheme").lower()
    if scheme not in _PROXY_TYPES:
        raise TgInputError(f"不支持的代理协议：{scheme}，仅支持 http 与 socks5")
    host = match.group("host")
    port = int(match.group("port"))
    if not 0 < port < 65536:
        raise TgInputError(f"代理端口超出范围：{port}")
    kind = getattr(ProxyType, _PROXY_TYPES[scheme])
    return (kind, host, port)


@dataclass
class TgConfig:
    """Telegram 登录与下载配置；构造时即完成全部校验。"""

    api_id: int
    api_hash: str
    session_path: str
    proxy: Optional[str] = None
    proxy_tuple: Optional[Tuple[Any, str, int]] = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        self.api_id = _validate_api_id(self.api_id)
        self.api_hash = _require_text(self.api_hash, "api_hash")
        self.session_path = _require_text(self.session_path, "session_path")
        if self.proxy is not None:
            self.proxy = str(self.proxy).strip() or None
        self.proxy_tuple = _build_proxy(self.proxy)


def default_session_path() -> str:
    """%APPDATA%/BiliDownloader/telegram.session；APPDATA 缺失时退回用户主目录。"""
    base = (os.environ.get("APPDATA") or "").strip()
    root = Path(base) if base else Path.home()
    return str(root / "BiliDownloader" / "telegram.session")


def qr_matrix(url: str) -> List[List[bool]]:
    """把登录 URL 编码为二维码矩阵（border=1）。"""
    text = (url or "").strip()
    if not text:
        raise TgInputError("二维码内容不能为空")
    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    qr.make(fit=True)
    return [[bool(cell) for cell in row] for row in qr.get_matrix()]


def _is_cancelled(cancel: Any) -> bool:
    if cancel is None:
        return False
    checker = getattr(cancel, "is_set", None)
    if callable(checker):
        return bool(checker())
    if callable(cancel):
        return bool(cancel())
    return bool(cancel)


def _check_cancel(cancel: Any, message: str) -> None:
    if _is_cancelled(cancel):
        raise TgCancelledError(message)


def _raise_flood(exc: FloodWaitError) -> None:
    seconds = int(getattr(exc, "seconds", 0) or 0)
    raise TgDownloadError(f"Telegram 限流，需要等待 {seconds} 秒，请稍后再试") from exc


def _wait_flood(exc: FloodWaitError, cancel: Any = None) -> None:
    """限流等待；超过 60 秒直接放弃，等待期间响应取消。"""
    seconds = float(getattr(exc, "seconds", 0) or 0)
    if seconds > _FLOOD_WAIT_LIMIT:
        _raise_flood(exc)
    deadline = time.monotonic() + max(seconds, 0.0)
    while True:
        _check_cancel(cancel, "操作已取消")
        remain = deadline - time.monotonic()
        if remain <= 0:
            return
        time.sleep(min(remain, 0.2))


def _translate_error(exc: Exception, message: str) -> None:
    if isinstance(exc, TgDLError):
        raise exc
    if isinstance(exc, SessionPasswordNeededError):
        raise TgAuthError("需要两步验证密码", password_required=True) from exc
    if isinstance(exc, FloodWaitError):
        _raise_flood(exc)
    if isinstance(exc, (UnauthorizedError, AuthKeyUnregisteredError)):
        raise TgAuthError("尚未登录或会话已失效") from exc
    raise TgDownloadError(f"{message}：{exc}") from exc


def _safe_disconnect(client: Any) -> None:
    try:
        client.disconnect()
    except Exception:
        pass


def _await(client: Any, value: Any) -> Any:
    """telethon.sync 不会同步化 QRLogin 的方法，这里把可能返回的协程跑完。"""
    if not inspect.isawaitable(value):
        return value
    loop = getattr(client, "loop", None)
    if loop is not None and not getattr(loop, "is_running", lambda: False)():
        return loop.run_until_complete(value)
    return asyncio.get_event_loop().run_until_complete(value)


def _require_config(config: Any) -> TgConfig:
    if not isinstance(config, TgConfig):
        raise TgInputError("配置参数非法，需要 TgConfig 实例")
    return config


def _ensure_session_dir(session_path: str) -> None:
    try:
        parent = Path(session_path).parent
        if str(parent) and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover - 目录不可创建时交由 Telethon 报错
        pass


def _make_client(config: TgConfig) -> Any:
    _ensure_session_dir(config.session_path)
    return TelegramClient(
        config.session_path, config.api_id, config.api_hash, proxy=config.proxy_tuple
    )


def _connect(config: TgConfig) -> Any:
    client = _make_client(config)
    try:
        client.connect()
    except Exception as exc:
        _safe_disconnect(client)
        _translate_error(exc, "连接 Telegram 失败")
    return client


def _ensure_authorized(client: Any) -> None:
    try:
        authorized = bool(client.is_user_authorized())
    except Exception as exc:
        raise TgAuthError("尚未登录或会话已失效") from exc
    if not authorized:
        raise TgAuthError("尚未登录或会话已失效")


# --------------------------------------------------------------------------- 媒体遍历


def _normalize_kinds(media_types: Optional[Iterable[str]]) -> Optional[Set[str]]:
    if media_types is None:
        return None
    if isinstance(media_types, str):
        values: List[Any] = [media_types]
    else:
        try:
            values = list(media_types)
        except TypeError as exc:
            raise TgInputError("media_types 必须是媒体类型集合") from exc
    kinds: Set[str] = set()
    for value in values:
        kind = str(value).strip().lower()
        if not kind:
            continue
        if kind not in _MEDIA_KINDS:
            raise TgInputError(
                f"不支持的媒体类型：{value}，仅支持 photo / video / audio / document"
            )
        kinds.add(kind)
    return kinds or None


def _normalize_limit(limit: Any) -> int:
    if limit is None:
        return 0
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise TgInputError("limit 必须是非负整数") from exc
    if value < 0:
        raise TgInputError("limit 必须是非负整数")
    return value


def _normalize_channel(channel: Any) -> Any:
    """把 @name / t.me/name / https://t.me/name / 纯用户名 / 数字 id 归一化。"""
    if isinstance(channel, int) and not isinstance(channel, bool):
        if channel == 0:
            raise TgInputError("频道不能为空")
        return channel
    text = str(channel or "").strip()
    if not text:
        raise TgInputError("频道不能为空")
    web_match = re.search(r"web\.telegram\.org/[^#\s]*#(@?[-\w]+)", text, re.IGNORECASE)
    if web_match:
        value = web_match.group(1)
        if value.startswith("@"):
            return value.lstrip("@")
        return int(value)
    lowered = text.lower()
    for prefix in ("https://", "http://"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    lowered = text.lower()
    if lowered.startswith("t.me/"):
        text = text[5:]
    elif lowered.startswith("telegram.me/"):
        text = text[len("telegram.me/") :]
    text = text.split("?", 1)[0].split("#", 1)[0]
    text = text.split("/", 1)[0].strip().lstrip("@")
    if not text:
        raise TgInputError(f"无法识别的频道：{channel}")
    if re.fullmatch(r"-?\d+", text):
        number = int(text)
        if number == 0:
            raise TgInputError(f"无法识别的频道：{channel}")
        return number
    return text


def _classify(message: Any) -> Optional[str]:
    if getattr(message, "photo", None) is not None:
        return "photo"
    if getattr(message, "video", None) is not None:
        return "video"
    if getattr(message, "audio", None) is not None:
        return "audio"
    if getattr(message, "document", None) is not None:
        return "document"
    return None


def _to_item(message: Any, kind: str) -> TgMediaItem:
    message_id = int(getattr(message, "id", 0) or 0)
    file_info = getattr(message, "file", None)
    name = getattr(file_info, "name", None) if file_info is not None else None
    ext = getattr(file_info, "ext", None) if file_info is not None else None
    size = getattr(file_info, "size", 0) if file_info is not None else 0
    filename = str(name) if name else f"{message_id}.{ext or 'bin'}"
    date_value = getattr(message, "date", None)
    stamp = int(date_value.timestamp()) if date_value is not None else 0
    return TgMediaItem(
        message_id=message_id,
        kind=kind,
        filename=filename,
        size=int(size or 0),
        date=stamp,
    )


def _iter_media(
    client: Any,
    target: Any,
    kinds: Optional[Set[str]],
    limit: int,
    cancel: Any,
) -> Iterator[Tuple[TgMediaItem, Any]]:
    # limit 按「媒体条数」计数，因此不把 limit 交给 iter_messages（0 在那里表示一条都不要）
    iterator = iter(client.iter_messages(target, limit=None))
    collected = 0
    while True:
        if limit and collected >= limit:
            return
        _check_cancel(cancel, "操作已取消")
        try:
            message = next(iterator)
        except StopIteration:
            return
        except FloodWaitError as exc:
            _wait_flood(exc, cancel)
            continue
        except Exception as exc:
            _translate_error(exc, "读取频道消息失败")
        kind = _classify(message)
        if kind is None:
            continue
        if kinds is not None and kind not in kinds:
            continue
        collected += 1
        yield _to_item(message, kind), message


def _numeric_target_ids(target: Any) -> Set[int]:
    """数字频道 ID 的候选形式：原值、绝对值、-100 前缀的 peer id。"""
    raw = str(target).strip()
    if not re.fullmatch(r"-?\d+", raw):
        return set()
    number = int(raw)
    absolute = abs(number)
    return {number, absolute, -absolute, int(f"-100{absolute}"), -1000000000000 - absolute}


def _find_dialog_entity(client: Any, target: Any) -> Any:
    """按数字 ID 在已加入的对话列表里查找实体（私有频道/群组）。"""
    wanted = _numeric_target_ids(target)
    if not wanted:
        return None
    try:
        dialogs = client.iter_dialogs(limit=None)
    except Exception:
        return None
    try:
        for dialog in dialogs:
            entity = getattr(dialog, "entity", None)
            if entity is None:
                continue
            entity_id = getattr(entity, "id", None)
            if isinstance(entity_id, int) and entity_id in wanted:
                return entity
            try:
                peer = tg_utils.get_peer_id(entity)
            except Exception:
                peer = None
            if isinstance(peer, int) and peer in wanted:
                return entity
    except Exception:
        return None
    return None


def _resolve_entity(client: Any, target: Any) -> Any:
    try:
        return client.get_entity(target)
    except Exception as exc:
        found = _find_dialog_entity(client, target)
        if found is not None:
            return found
        _translate_error(exc, f"无法解析频道：{target}")


def _entity_title(entity: Any, target: Any) -> str:
    for attr in ("title", "username"):
        value = getattr(entity, attr, None)
        if value:
            return str(value)
    return str(target)


# --------------------------------------------------------------------------- 二维码登录


def _sign_in_with_password(client: Any, password: Optional[str]) -> bool:
    if not password:
        raise TgAuthError(
            "该账号已开启两步验证，请输入两步验证密码后再登录", password_required=True
        )
    try:
        client.sign_in(password=password)
    except TgDLError:
        raise
    except Exception as exc:
        raise TgAuthError(f"两步验证密码错误：{exc}", password_required=True) from exc
    return True


def _wait_budget(qr: Any, remain: float) -> float:
    """单次 qr.wait 的等待上限：不超过整体剩余时间，也不超过二维码本身的有效期。"""
    expires = getattr(qr, "expires", None)
    if not isinstance(expires, datetime.datetime):
        return remain
    try:
        moment = expires
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        delta = (moment - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    except Exception:  # pragma: no cover - 时间对象异常时退回整体剩余时间
        return remain
    return min(remain, delta + 0.5) if delta > 0 else min(remain, 0.5)


def _emit_qr(on_qr: Optional[Callable[[str, List[List[bool]]], None]], qr: Any) -> None:
    if on_qr is None:
        return
    url = str(getattr(qr, "url", "") or "")
    if not url:
        return
    on_qr(url, qr_matrix(url))


def qr_login(
    config: TgConfig,
    on_qr: Optional[Callable[[str, List[List[bool]]], None]] = None,
    password: Optional[str] = None,
    cancel: Any = None,
    timeout: float = 180,
) -> bool:
    """扫码登录；成功后 session 落盘在 config.session_path。"""
    config = _require_config(config)
    client = _connect(config)
    try:
        try:
            qr = client.qr_login()
        except Exception as exc:
            raise TgAuthError(f"获取登录二维码失败：{exc}") from exc
        _emit_qr(on_qr, qr)
        deadline = time.monotonic() + max(float(timeout or 0), 0.0)
        while True:
            _check_cancel(cancel, "已取消扫码登录")
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise TgAuthError("扫码登录超时")
            budget = _wait_budget(qr, remain)
            try:
                _await(client, qr.wait(timeout=budget))
                return True
            except SessionPasswordNeededError:
                return _sign_in_with_password(client, password)
            except (asyncio.TimeoutError, TimeoutError) as exc:
                if budget >= remain or deadline - time.monotonic() <= 0:
                    raise TgAuthError("扫码登录超时") from exc
                try:
                    refreshed = _await(client, qr.recreate())
                except Exception as exc2:
                    raise TgAuthError(f"刷新登录二维码失败：{exc2}") from exc2
                qr = refreshed or qr
                _emit_qr(on_qr, qr)
            except TgDLError:
                raise
            except Exception as exc:
                raise TgAuthError(f"扫码登录失败：{exc}") from exc
    finally:
        _safe_disconnect(client)


# --------------------------------------------------------------------------- 媒体清单


def list_channel_media(
    config: TgConfig,
    channel: Any,
    media_types: Optional[Iterable[str]] = None,
    limit: int = 0,
    cancel: Any = None,
) -> TgChannelInfo:
    """列出频道媒体；limit 按媒体条数计数，0 表示全部。"""
    config = _require_config(config)
    kinds = _normalize_kinds(media_types)
    limit = _normalize_limit(limit)
    _check_cancel(cancel, "操作已取消")
    client = _connect(config)
    try:
        _ensure_authorized(client)
        target = _normalize_channel(channel)
        entity = _resolve_entity(client, target)
        items = [item for item, _ in _iter_media(client, target, kinds, limit, cancel)]
        return TgChannelInfo(
            title=_entity_title(entity, target),
            username=str(getattr(entity, "username", "") or ""),
            total=len(items),
            items=items,
        )
    finally:
        _safe_disconnect(client)


# --------------------------------------------------------------------------- 下载


def _safe_name(name: Any, limit: int = _MAX_NAME_LEN) -> str:
    text = _ILLEGAL_CHARS.sub("_", str(name or ""))
    text = text.strip().strip(".").strip()
    if not text:
        return ""
    if len(text) > limit:
        stem, suffix = os.path.splitext(text)
        if suffix and len(suffix) <= 20:
            text = stem[: max(limit - len(suffix), 1)] + suffix
        else:
            text = text[:limit]
    return text


def _unique_path(directory: Path, filename: str) -> Path:
    name = _safe_name(filename) or "media"
    stem, suffix = os.path.splitext(name)
    candidate = directory / name
    index = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def _make_progress_callback(
    progress: Optional[Callable[[str, int, int], None]],
    cancel: Any,
    completed: int,
    total: int,
) -> Callable[[int, int], None]:
    def callback(downloaded: int = 0, total_bytes: int = 0) -> None:
        _check_cancel(cancel, "下载已取消")
        if progress is not None:
            progress("download", completed, total)

    return callback


def _download_one(
    client: Any, message: Any, destination: Path, callback: Callable[[int, int], None], cancel: Any
) -> Any:
    kwargs = {"file": str(destination), "progress_callback": callback}
    try:
        return client.download_media(message, **kwargs)
    except FloodWaitError as exc:
        _wait_flood(exc, cancel)
        return client.download_media(message, **kwargs)


def download_channel_media(
    config: TgConfig,
    channel: Any,
    save_dir: str,
    media_types: Optional[Iterable[str]] = None,
    limit: int = 0,
    progress: Optional[Callable[[str, int, int], None]] = None,
    cancel: Any = None,
) -> List[str]:
    """下载频道媒体到 <save_dir>/<频道标题>/<类型目录>/，返回成功文件路径。"""
    config = _require_config(config)
    kinds = _normalize_kinds(media_types)
    limit = _normalize_limit(limit)
    root = Path(_require_text(save_dir, "保存目录")).expanduser()
    _check_cancel(cancel, "下载已取消")
    client = _connect(config)
    try:
        _ensure_authorized(client)
        target = _normalize_channel(channel)
        entity = _resolve_entity(client, target)
        folder = _safe_name(_entity_title(entity, target)) or "telegram"
        pairs = list(_iter_media(client, target, kinds, limit, cancel))
        total = len(pairs)
        saved: List[str] = []
        skipped = 0
        for item, message in pairs:
            _check_cancel(cancel, "下载已取消")
            directory = root / folder / _KIND_DIRS[item.kind]
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise TgDownloadError(f"无法创建保存目录：{directory}（{exc}）") from exc
            destination = _unique_path(directory, item.filename)
            callback = _make_progress_callback(progress, cancel, len(saved), total)
            try:
                result = _download_one(client, message, destination, callback, cancel)
            except TgDLError:
                raise
            except Exception:
                skipped += 1
                if progress is not None:
                    progress("skip", skipped, total)
                continue
            saved.append(str(result) if result else str(destination))
            if progress is not None:
                progress("download", len(saved), total)
        if not saved:
            raise TgDownloadError("未下载到任何媒体文件")
        if progress is not None:
            progress("done", len(saved), len(saved))
        return saved
    finally:
        _safe_disconnect(client)


# --------------------------------------------------------------------------- 退出登录


def logout(config: TgConfig) -> bool:
    """删除本地 session 文件；返回是否真的删除。"""
    config = _require_config(config)
    path = Path(config.session_path)
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError as exc:
        raise TgDLError(f"删除会话文件失败：{path}（{exc}）") from exc
    return False
