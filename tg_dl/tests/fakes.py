"""tg_dl 单测用的假对象（全程离线，不联网）。

所有用例统一通过 mock.patch("tg_dl.TelegramClient", FakeClient) 注入替身，
tg_dl 内部的网络调用因此全部落到 FakeClient 上。
"""

import datetime
import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import tg_dl
from telethon.errors import FloodWaitError, SessionPasswordNeededError


def flood_error(seconds):
    """构造一个带指定等待秒数的 FloodWaitError。"""
    exc = FloodWaitError(request=SimpleNamespace(seconds=0))
    exc.seconds = seconds
    return exc


class FakeFile:
    def __init__(self, name=None, size=None, ext=None):
        self.name = name
        self.size = size
        self.ext = ext


class FakeMessage:
    """最小可用的 telethon Message 替身。"""

    def __init__(
        self,
        message_id,
        kind="photo",
        name=None,
        size=None,
        ext=None,
        date=None,
        with_file=True,
    ):
        self.id = message_id
        self.photo = None
        self.video = None
        self.audio = None
        self.document = None
        if kind in ("photo", "video", "audio", "document"):
            setattr(self, kind, object())
        self.file = FakeFile(name=name, size=size, ext=ext) if with_file else None
        self.date = date or (
            datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
            + datetime.timedelta(seconds=message_id)
        )


class FakeEntity:
    def __init__(self, title="测试频道", username="test_channel"):
        self.title = title
        self.username = username


class FakeUser:
    def __init__(self, user_id=42):
        self.id = user_id


class FakeMessageIterator:
    """可在开头发射一次 FloodWaitError / 直接报错的迭代器。"""

    def __init__(self, messages, flood_seconds=0, error=None):
        self._messages = list(messages)
        self._index = 0
        self._flood = flood_seconds
        self._error = error
        self._raised = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._error is not None and not self._raised:
            self._raised = True
            raise self._error
        if self._flood and not self._raised:
            self._raised = True
            raise flood_error(self._flood)
        if self._index >= len(self._messages):
            raise StopIteration
        message = self._messages[self._index]
        self._index += 1
        return message


class FakeQR:
    """QRLogin 替身：按 actions 依次决定每次 wait 的结果。"""

    def __init__(self, url="tg://login?token=fake-token", actions=("ok",), expires=None):
        self.url = url
        self.expires = expires
        self.actions = list(actions)
        self.waits = []
        self.recreates = 0

    def wait(self, timeout=None):
        self.waits.append(timeout)
        action = self.actions.pop(0) if self.actions else "ok"
        if action == "password":
            raise SessionPasswordNeededError(None)
        if action == "timeout":
            raise TimeoutError("QR code expired")
        if action == "error":
            raise RuntimeError("网络中断")
        return FakeUser()

    def recreate(self):
        self.recreates += 1
        return self


_DEFAULTS = {
    "authorized": True,
    "connect_error": None,
    "entity": None,
    "entity_error": None,
    "messages": (),
    "iter_error": None,
    "iter_flood_seconds": 0,
    "qr": None,
    "qr_error": None,
    "sign_in_error": None,
    "download_error": None,
    "download_flood_seconds": 0,
    "fail_message_ids": (),
    "write_files": True,
    "download_result": None,
}


class FakeClient:
    """telethon.sync.TelegramClient 的替身：记录调用、按类属性决定行为。"""

    instances = []

    @classmethod
    def reset(cls):
        cls.instances = []
        for name, value in _DEFAULTS.items():
            setattr(cls, name, value)

    def __init__(self, session_path, api_id, api_hash, proxy=None):
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        self.proxy = proxy
        self.connected = False
        self.disconnected = False
        self.entity_arg = None
        self.iter_calls = []
        self.downloads = []
        self.sign_in_passwords = []
        self.qr_calls = 0
        self._download_flood_done = False
        FakeClient.instances.append(self)

    # ---- 生命周期
    def connect(self):
        self.connected = True
        if FakeClient.connect_error is not None:
            raise FakeClient.connect_error

    def disconnect(self):
        self.disconnected = True

    def is_user_authorized(self):
        return FakeClient.authorized

    # ---- 实体与消息
    def get_entity(self, target):
        self.entity_arg = target
        if FakeClient.entity_error is not None:
            raise FakeClient.entity_error
        entity = FakeClient.entity
        return entity if entity is not None else FakeEntity()

    def iter_messages(self, entity, limit=None):
        self.iter_calls.append((entity, limit))
        if FakeClient.iter_error is not None:
            return FakeMessageIterator((), error=FakeClient.iter_error)
        return FakeMessageIterator(FakeClient.messages, FakeClient.iter_flood_seconds)

    # ---- 登录
    def qr_login(self):
        self.qr_calls += 1
        if FakeClient.qr_error is not None:
            raise FakeClient.qr_error
        return FakeClient.qr if FakeClient.qr is not None else FakeQR()

    def sign_in(self, password=None):
        self.sign_in_passwords.append(password)
        if FakeClient.sign_in_error is not None:
            raise FakeClient.sign_in_error
        return FakeUser()

    # ---- 下载
    def download_media(self, message, file=None, progress_callback=None):
        message_id = getattr(message, "id", None)
        self.downloads.append((message_id, file))
        if progress_callback is not None:
            progress_callback(50, 100)
        if FakeClient.download_flood_seconds and not self._download_flood_done:
            self._download_flood_done = True
            raise flood_error(FakeClient.download_flood_seconds)
        if FakeClient.download_error is not None:
            raise FakeClient.download_error
        if message_id in FakeClient.fail_message_ids:
            raise RuntimeError("下载失败")
        if FakeClient.write_files and file:
            path = Path(file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fake")
            return file
        return FakeClient.download_result if FakeClient.download_result else file


for _name, _value in _DEFAULTS.items():
    setattr(FakeClient, _name, _value)


class FakeProxyType:
    """python_socks.ProxyType 的替身（本机未安装 python-socks）。"""

    HTTP = "proxy-http"
    SOCKS5 = "proxy-socks5"


@contextmanager
def fake_socks(enabled=True):
    """让 tg_dl 以为自己装了 / 没装 python-socks。"""
    with mock.patch.object(tg_dl, "_HAS_PYTHON_SOCKS", enabled), mock.patch.object(
        tg_dl, "ProxyType", FakeProxyType if enabled else None
    ):
        yield


@contextmanager
def fake_clock():
    """把 tg_dl 的限流等待换成瞬时假时钟，避免测试真睡眠。"""
    state = {"now": 1000.0}

    def fake_sleep(seconds):
        state["now"] += float(seconds)

    def fake_monotonic():
        return state["now"]

    with mock.patch.object(tg_dl.time, "sleep", side_effect=fake_sleep), mock.patch.object(
        tg_dl.time, "monotonic", side_effect=fake_monotonic
    ):
        yield state


class TgClientTestCase(unittest.TestCase):
    """统一注入 FakeClient 的用例基类。"""

    def setUp(self):
        FakeClient.reset()
        mock.patch("tg_dl.TelegramClient", FakeClient).start()
        self.addCleanup(mock.patch.stopall)

    @property
    def client(self):
        self.assertTrue(FakeClient.instances, "TelegramClient 未被创建")
        return FakeClient.instances[-1]

    def make_config(self, session_path="telegram.session", proxy=None):
        return tg_dl.TgConfig(
            api_id=12345, api_hash="hash-value", session_path=session_path, proxy=proxy
        )

    def session_config(self, proxy=None):
        return tg_dl.TgConfig(
            api_id=12345,
            api_hash="hash-value",
            session_path=os.path.join(self.temp_dir(), "telegram.session"),
            proxy=proxy,
        )

    def temp_dir(self):
        directory = tempfile.mkdtemp(prefix="tg_dl_test_")
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory
