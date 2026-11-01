"""配置、代理、会话路径、二维码矩阵、退出登录、异常层次的离线测试。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import qrcode

import tg_dl
from tg_dl import TgChannelInfo, TgConfig, TgMediaItem
from tg_dl.tests.fakes import FakeProxyType, fake_socks


def _config(**overrides):
    kwargs = {"api_id": 12345, "api_hash": "hash-value", "session_path": "telegram.session"}
    kwargs.update(overrides)
    return TgConfig(**kwargs)


class PublicApiTest(unittest.TestCase):
    def test_all_matches_gui_contract(self):
        self.assertEqual(
            tg_dl.__all__,
            [
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
            ],
        )
        for name in tg_dl.__all__:
            self.assertTrue(hasattr(tg_dl, name), name)


class ConfigValidationTest(unittest.TestCase):
    def test_valid_config_keeps_fields(self):
        config = _config()
        self.assertEqual(config.api_id, 12345)
        self.assertEqual(config.api_hash, "hash-value")
        self.assertEqual(config.session_path, "telegram.session")
        self.assertIsNone(config.proxy)
        self.assertIsNone(config.proxy_tuple)

    def test_api_id_must_be_positive_integer(self):
        for bad in (0, -1, -100, "abc", "", None, 1.5, True, "0", "-5"):
            with self.subTest(api_id=bad):
                with self.assertRaises(tg_dl.TgInputError) as ctx:
                    _config(api_id=bad)
                self.assertIn("api_id", str(ctx.exception))

    def test_api_id_accepts_numeric_string(self):
        config = _config(api_id=" 987654 ")
        self.assertEqual(config.api_id, 987654)
        self.assertIsInstance(config.api_id, int)

    def test_api_hash_must_not_be_blank(self):
        for bad in ("", "   ", None):
            with self.subTest(api_hash=bad):
                with self.assertRaises(tg_dl.TgInputError) as ctx:
                    _config(api_hash=bad)
                self.assertIn("api_hash", str(ctx.exception))

    def test_session_path_must_not_be_blank(self):
        for bad in ("", "   ", None):
            with self.subTest(session_path=bad):
                with self.assertRaises(tg_dl.TgInputError) as ctx:
                    _config(session_path=bad)
                self.assertIn("session_path", str(ctx.exception))


class ProxyConversionTest(unittest.TestCase):
    def test_http_proxy_turns_into_tuple(self):
        with fake_socks():
            config = _config(proxy="http://127.0.0.1:7890")
        self.assertEqual(config.proxy, "http://127.0.0.1:7890")
        self.assertEqual(config.proxy_tuple, (FakeProxyType.HTTP, "127.0.0.1", 7890))

    def test_socks5_proxy_turns_into_tuple(self):
        with fake_socks():
            config = _config(proxy="socks5://proxy.local:1080")
        self.assertEqual(config.proxy_tuple, (FakeProxyType.SOCKS5, "proxy.local", 1080))

    def test_socks5h_and_https_aliases(self):
        with fake_socks():
            self.assertEqual(
                _config(proxy="socks5h://127.0.0.1:1080").proxy_tuple,
                (FakeProxyType.SOCKS5, "127.0.0.1", 1080),
            )
            self.assertEqual(
                _config(proxy="HTTPS://127.0.0.1:8080").proxy_tuple,
                (FakeProxyType.HTTP, "127.0.0.1", 8080),
            )

    def test_proxy_requires_python_socks(self):
        with fake_socks(enabled=False):
            with self.assertRaises(tg_dl.TgInputError) as ctx:
                _config(proxy="http://127.0.0.1:7890")
        message = str(ctx.exception)
        self.assertIn("python-socks", message)
        self.assertIn("代理", message)

    def test_proxy_stays_optional_without_python_socks(self):
        with fake_socks(enabled=False):
            config = _config()
        self.assertIsNone(config.proxy_tuple)

    def test_blank_proxy_means_no_proxy(self):
        with fake_socks():
            for blank in ("", "   ", None):
                with self.subTest(proxy=blank):
                    config = _config(proxy=blank)
                    self.assertIsNone(config.proxy)
                    self.assertIsNone(config.proxy_tuple)

    def test_invalid_proxy_formats(self):
        cases = (
            ("http://127.0.0.1", "格式"),
            ("127.0.0.1:7890", "格式"),
            ("http://:7890", "格式"),
            ("ftp://127.0.0.1:21", "协议"),
            ("socks4://127.0.0.1:1080", "协议"),
            ("http://127.0.0.1:0", "端口"),
            ("http://127.0.0.1:70000", "端口"),
        )
        with fake_socks():
            for proxy, keyword in cases:
                with self.subTest(proxy=proxy):
                    with self.assertRaises(tg_dl.TgInputError) as ctx:
                        _config(proxy=proxy)
                    self.assertIn(keyword, str(ctx.exception))


class RealProxyTypeTest(unittest.TestCase):
    """装了 python-socks 的环境里，用真实的 ProxyType 校验转换结果。"""

    def setUp(self):
        try:
            from python_socks import ProxyType as real_type
        except ImportError:  # pragma: no cover - 取决于运行环境
            self.skipTest("本机未安装 python-socks")
        self.real = real_type

    def test_http_and_socks5_use_real_proxy_type(self):
        self.assertEqual(
            _config(proxy="http://127.0.0.1:7890").proxy_tuple,
            (self.real.HTTP, "127.0.0.1", 7890),
        )
        self.assertEqual(
            _config(proxy="socks5://127.0.0.1:1080").proxy_tuple,
            (self.real.SOCKS5, "127.0.0.1", 1080),
        )


class SessionPathTest(unittest.TestCase):
    def test_uses_appdata(self):
        appdata = r"C:\Users\demo\AppData\Roaming"
        with mock.patch.dict(os.environ, {"APPDATA": appdata}):
            path = tg_dl.default_session_path()
        self.assertEqual(path, os.path.join(appdata, "BiliDownloader", "telegram.session"))

    def test_blank_appdata_falls_back_to_home(self):
        with mock.patch.dict(os.environ, {"APPDATA": "   "}):
            path = tg_dl.default_session_path()
        self.assertEqual(path, os.path.join(str(Path.home()), "BiliDownloader", "telegram.session"))

    def test_missing_appdata_falls_back_to_home(self):
        env = {k: v for k, v in os.environ.items() if k != "APPDATA"}
        with mock.patch.dict(os.environ, env, clear=True):
            path = tg_dl.default_session_path()
        self.assertTrue(path.startswith(str(Path.home())))
        self.assertTrue(path.endswith("telegram.session"))


class QrMatrixTest(unittest.TestCase):
    def test_matrix_is_square_and_typed(self):
        matrix = tg_dl.qr_matrix("tg://login?token=abcdef")
        self.assertGreaterEqual(len(matrix), 23)
        for row in matrix:
            self.assertEqual(len(row), len(matrix))
            for cell in row:
                self.assertIsInstance(cell, bool)

    def test_border_width_is_one(self):
        url = "tg://login?token=abcdef"
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        self.assertEqual(len(tg_dl.qr_matrix(url)), len(qr.modules) + 2)

    def test_border_is_quiet(self):
        matrix = tg_dl.qr_matrix("tg://login?token=abcdef")
        ring = list(matrix[0]) + list(matrix[-1])
        ring += [row[0] for row in matrix] + [row[-1] for row in matrix]
        self.assertFalse(any(ring))
        inner = [cell for row in matrix[1:-1] for cell in row[1:-1]]
        self.assertTrue(any(inner))

    def test_same_url_gives_same_matrix(self):
        self.assertEqual(
            tg_dl.qr_matrix("tg://login?token=abcdef"),
            tg_dl.qr_matrix("tg://login?token=abcdef"),
        )

    def test_empty_url_rejected(self):
        for bad in ("", "   ", None):
            with self.subTest(url=bad):
                with self.assertRaises(tg_dl.TgInputError):
                    tg_dl.qr_matrix(bad)


class LogoutTest(unittest.TestCase):
    def test_removes_existing_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "telegram.session")
            Path(path).write_bytes(b"sqlite")
            self.assertTrue(tg_dl.logout(_config(session_path=path)))
            self.assertFalse(Path(path).exists())

    def test_returns_false_when_session_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "telegram.session")
            self.assertFalse(tg_dl.logout(_config(session_path=path)))
            self.assertFalse(Path(path).exists())

    def test_rejects_non_config(self):
        with self.assertRaises(tg_dl.TgInputError):
            tg_dl.logout(object())


class ErrorTest(unittest.TestCase):
    def test_hierarchy(self):
        for cls in (
            tg_dl.TgInputError,
            tg_dl.TgAuthError,
            tg_dl.TgDownloadError,
            tg_dl.TgCancelledError,
        ):
            self.assertTrue(issubclass(cls, tg_dl.TgDLError))
        self.assertTrue(issubclass(tg_dl.TgDLError, Exception))

    def test_auth_error_password_flag(self):
        self.assertFalse(tg_dl.TgAuthError("尚未登录").password_required)
        self.assertTrue(tg_dl.TgAuthError("需要两步验证", password_required=True).password_required)

    def test_messages_are_chinese(self):
        with self.assertRaises(tg_dl.TgInputError) as ctx:
            _config(api_id=0)
        self.assertTrue(any("\u4e00" <= ch <= "\u9fff" for ch in str(ctx.exception)))


class ModelTest(unittest.TestCase):
    def test_media_item_fields(self):
        item = TgMediaItem(message_id=7, kind="video", filename="a.mp4", size=1024, date=1700000000)
        self.assertEqual(item.message_id, 7)
        self.assertEqual(item.kind, "video")
        self.assertEqual(item.filename, "a.mp4")
        self.assertEqual(item.size, 1024)
        self.assertEqual(item.date, 1700000000)

    def test_channel_info_fields(self):
        info = TgChannelInfo(title="频道", username="chan", total=0, items=[])
        self.assertEqual(info.title, "频道")
        self.assertEqual(info.username, "chan")
        self.assertEqual(info.total, 0)
        self.assertEqual(info.items, [])
