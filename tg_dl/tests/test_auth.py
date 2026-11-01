"""qr_login 的离线测试：成功、超时、两步验证、取消、异常包装、二维码刷新。"""

import asyncio
import datetime
import threading
from types import SimpleNamespace

import tg_dl
from tg_dl import TgAuthError, TgCancelledError, TgDownloadError, TgInputError
from tg_dl.tests.fakes import FakeClient, FakeProxyType, FakeQR, TgClientTestCase, fake_socks


class QrLoginSuccessTest(TgClientTestCase):
    def test_returns_true_and_emits_qr(self):
        qr = FakeQR(url="tg://login?token=abc")
        FakeClient.qr = qr
        seen = []
        config = self.session_config()

        result = tg_dl.qr_login(config, on_qr=lambda url, matrix: seen.append((url, matrix)))

        self.assertTrue(result)
        self.assertEqual(seen[0][0], "tg://login?token=abc")
        self.assertEqual(seen[0][1], tg_dl.qr_matrix("tg://login?token=abc"))
        self.assertGreaterEqual(len(seen[0][1]), 23)
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(qr.waits), 1)
        self.assertGreater(qr.waits[0], 170)
        self.assertLessEqual(qr.waits[0], 180)
        self.assertTrue(self.client.connected)
        self.assertTrue(self.client.disconnected)

    def test_on_qr_is_optional(self):
        FakeClient.qr = FakeQR()
        self.assertTrue(tg_dl.qr_login(self.session_config()))

    def test_client_gets_session_and_proxy(self):
        FakeClient.qr = FakeQR()
        with fake_socks():
            config = self.session_config(proxy="socks5://127.0.0.1:1080")
            self.assertTrue(tg_dl.qr_login(config))
        self.assertEqual(self.client.session_path, config.session_path)
        self.assertEqual(self.client.api_id, 12345)
        self.assertEqual(self.client.api_hash, "hash-value")
        self.assertEqual(self.client.proxy, (FakeProxyType.SOCKS5, "127.0.0.1", 1080))

    def test_no_proxy_passes_none(self):
        FakeClient.qr = FakeQR()
        tg_dl.qr_login(self.session_config())
        self.assertIsNone(self.client.proxy)


class QrLoginTimeoutTest(TgClientTestCase):
    def test_wait_timeout_raises_chinese_error(self):
        FakeClient.qr = FakeQR(actions=("timeout",))
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.qr_login(self.session_config(), timeout=5)
        self.assertEqual(str(ctx.exception), "扫码登录超时")
        self.assertFalse(ctx.exception.password_required)
        self.assertTrue(self.client.disconnected)

    def test_expired_deadline_does_not_wait(self):
        qr = FakeQR()
        FakeClient.qr = qr
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.qr_login(self.session_config(), timeout=0)
        self.assertEqual(str(ctx.exception), "扫码登录超时")
        self.assertEqual(qr.waits, [])
        self.assertTrue(self.client.disconnected)


class QrLoginPasswordTest(TgClientTestCase):
    def test_password_required_without_password(self):
        FakeClient.qr = FakeQR(actions=("password",))
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.qr_login(self.session_config())
        self.assertIn("两步验证", str(ctx.exception))
        self.assertTrue(ctx.exception.password_required)
        self.assertEqual(self.client.sign_in_passwords, [])
        self.assertTrue(self.client.disconnected)

    def test_password_needed_signs_in(self):
        FakeClient.qr = FakeQR(actions=("password",))
        seen = []
        self.assertTrue(
            tg_dl.qr_login(self.session_config(), on_qr=lambda u, m: seen.append(u), password="secret")
        )
        self.assertEqual(self.client.sign_in_passwords, ["secret"])
        self.assertEqual(len(seen), 1)

    def test_wrong_password_is_reported(self):
        FakeClient.qr = FakeQR(actions=("password",))
        FakeClient.sign_in_error = RuntimeError("PASSWORD_HASH_INVALID")
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.qr_login(self.session_config(), password="bad")
        self.assertIn("两步验证密码错误", str(ctx.exception))
        self.assertTrue(ctx.exception.password_required)
        self.assertTrue(self.client.disconnected)


class QrLoginCancelTest(TgClientTestCase):
    def test_event_cancel(self):
        event = threading.Event()
        event.set()
        qr = FakeQR()
        FakeClient.qr = qr
        with self.assertRaises(TgCancelledError) as ctx:
            tg_dl.qr_login(self.session_config(), cancel=event)
        self.assertIn("取消", str(ctx.exception))
        self.assertEqual(qr.waits, [])
        self.assertTrue(self.client.disconnected)

    def test_callable_cancel(self):
        FakeClient.qr = FakeQR()
        with self.assertRaises(TgCancelledError):
            tg_dl.qr_login(self.session_config(), cancel=lambda: True)


class QrLoginFailureTest(TgClientTestCase):
    def test_connect_failure(self):
        FakeClient.connect_error = OSError("网络不可达")
        with self.assertRaises(TgDownloadError) as ctx:
            tg_dl.qr_login(self.session_config())
        self.assertIn("连接 Telegram 失败", str(ctx.exception))
        self.assertTrue(self.client.disconnected)

    def test_qr_request_failure(self):
        FakeClient.qr_error = RuntimeError("RPC 出错")
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.qr_login(self.session_config())
        self.assertIn("获取登录二维码失败", str(ctx.exception))
        self.assertTrue(self.client.disconnected)

    def test_wait_failure_is_wrapped(self):
        FakeClient.qr = FakeQR(actions=("error",))
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.qr_login(self.session_config())
        self.assertIn("扫码登录失败", str(ctx.exception))

    def test_requires_config_instance(self):
        with self.assertRaises(TgInputError):
            tg_dl.qr_login(object())


class SyncBridgeTest(TgClientTestCase):
    """telethon.sync 不会同步化 QRLogin，_await 必须自己把协程跑完。"""

    def test_runs_coroutine_on_client_loop(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        client = SimpleNamespace(loop=loop)

        async def coro():
            return "user"

        self.assertEqual(tg_dl._await(client, coro()), "user")
        self.assertEqual(tg_dl._await(client, 5), 5)


class QrLoginRefreshTest(TgClientTestCase):
    def test_expired_token_is_recreated(self):
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)
        qr = FakeQR(actions=("timeout", "ok"), expires=past)
        FakeClient.qr = qr
        seen = []
        self.assertTrue(
            tg_dl.qr_login(
                self.session_config(), on_qr=lambda url, matrix: seen.append(url), timeout=30
            )
        )
        self.assertEqual(qr.recreates, 1)
        self.assertEqual(len(qr.waits), 2)
        self.assertEqual(len(seen), 2)
        self.assertTrue(self.client.disconnected)
