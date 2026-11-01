"""list_channel_media 的离线测试：分类、过滤、limit、频道归一化、鉴权、限流、取消。"""

import threading
import unittest
from unittest import mock

from telethon.errors import AuthKeyUnregisteredError

import tg_dl
from tg_dl import TgAuthError, TgCancelledError, TgDownloadError, TgInputError
from tg_dl.tests.fakes import FakeClient, FakeEntity, FakeMessage, TgClientTestCase, fake_clock


class _CancelAfter:
    """第 n 次被询问后才返回 True，用于模拟「遍历中途取消」。"""

    def __init__(self, allowed):
        self.allowed = allowed
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.calls > self.allowed


class ListMediaTest(TgClientTestCase):
    def test_classifies_kinds_and_skips_other_media(self):
        FakeClient.messages = [
            FakeMessage(1, kind="photo", ext="jpg"),
            FakeMessage(2, kind="video", name="clip.mp4", size=2048),
            FakeMessage(3, kind="audio", name="song.mp3", size=4096),
            FakeMessage(4, kind="document", name="doc.pdf", size=512),
            FakeMessage(5, kind="other"),
        ]
        info = tg_dl.list_channel_media(self.session_config(), "@test_channel")

        self.assertEqual([item.kind for item in info.items], ["photo", "video", "audio", "document"])
        self.assertEqual([item.message_id for item in info.items], [1, 2, 3, 4])
        self.assertEqual(info.items[0].filename, "1.jpg")
        self.assertEqual(info.items[1].filename, "clip.mp4")
        self.assertEqual(info.items[1].size, 2048)
        self.assertEqual(info.items[0].size, 0)
        self.assertEqual(info.total, 4)
        self.assertEqual(info.title, "测试频道")
        self.assertEqual(info.username, "test_channel")
        self.assertEqual(info.items[0].date, int(FakeClient.messages[0].date.timestamp()))

    def test_missing_file_info_uses_fallbacks(self):
        FakeClient.messages = [FakeMessage(9, kind="video", with_file=False)]
        info = tg_dl.list_channel_media(self.session_config(), "chan")
        self.assertEqual(info.items[0].filename, "9.bin")
        self.assertEqual(info.items[0].size, 0)

    def test_media_types_subset(self):
        FakeClient.messages = [
            FakeMessage(1, "photo"),
            FakeMessage(2, "video"),
            FakeMessage(3, "document"),
        ]
        info = tg_dl.list_channel_media(self.session_config(), "chan", media_types={"video", "document"})
        self.assertEqual([item.kind for item in info.items], ["video", "document"])

    def test_media_types_accepts_single_string(self):
        FakeClient.messages = [FakeMessage(1, "photo"), FakeMessage(2, "video")]
        info = tg_dl.list_channel_media(self.session_config(), "chan", media_types="photo")
        self.assertEqual([item.kind for item in info.items], ["photo"])

    def test_empty_media_types_means_all(self):
        FakeClient.messages = [FakeMessage(1, "photo"), FakeMessage(2, "video")]
        info = tg_dl.list_channel_media(self.session_config(), "chan", media_types=set())
        self.assertEqual(len(info.items), 2)

    def test_unknown_media_type_rejected(self):
        with self.assertRaises(TgInputError) as ctx:
            tg_dl.list_channel_media(self.session_config(), "chan", media_types={"gif"})
        self.assertIn("gif", str(ctx.exception))

    def test_limit_counts_media_items(self):
        FakeClient.messages = [FakeMessage(1, "other")] + [
            FakeMessage(index, "photo") for index in range(2, 6)
        ]
        info = tg_dl.list_channel_media(self.session_config(), "chan", limit=2)
        self.assertEqual([item.message_id for item in info.items], [2, 3])
        self.assertEqual(info.total, 2)
        self.assertEqual(self.client.iter_calls[0][1], None)

    def test_limit_zero_returns_everything(self):
        FakeClient.messages = [FakeMessage(index, "photo") for index in range(1, 6)]
        info = tg_dl.list_channel_media(self.session_config(), "chan", limit=0)
        self.assertEqual(info.total, 5)

    def test_negative_limit_rejected(self):
        with self.assertRaises(TgInputError) as ctx:
            tg_dl.list_channel_media(self.session_config(), "chan", limit=-1)
        self.assertIn("limit", str(ctx.exception))

    def test_empty_channel_returns_empty_info(self):
        info = tg_dl.list_channel_media(self.session_config(), "chan")
        self.assertEqual(info.total, 0)
        self.assertEqual(info.items, [])
        self.assertTrue(self.client.disconnected)

    def test_iter_messages_receives_resolved_entity(self):
        FakeClient.entity = FakeEntity(title="某频道", username="chan")
        FakeClient.messages = [FakeMessage(1, "photo")]
        tg_dl.list_channel_media(self.session_config(), "@chan")
        self.assertEqual(self.client.iter_calls[0][0], "chan")


class ChannelNormalizeTest(TgClientTestCase):
    CASES = (
        ("@test_channel", "test_channel"),
        ("t.me/test_channel", "test_channel"),
        ("https://t.me/test_channel", "test_channel"),
        ("http://t.me/test_channel?single=1", "test_channel"),
        ("test_channel", "test_channel"),
        ("https://t.me/test_channel/45", "test_channel"),
        ("123456789", 123456789),
        ("-1001234567890", -1001234567890),
        (-1001234567890, -1001234567890),
    )

    def test_channel_forms_are_normalized(self):
        FakeClient.messages = [FakeMessage(1, "photo")]
        for raw, expected in self.CASES:
            with self.subTest(channel=raw):
                tg_dl.list_channel_media(self.session_config(), raw)
                self.assertEqual(self.client.entity_arg, expected)

    def test_blank_channel_rejected(self):
        for bad in ("", "   ", None, "@", "https://t.me/"):
            with self.subTest(channel=bad):
                with self.assertRaises(TgInputError) as ctx:
                    tg_dl.list_channel_media(self.session_config(), bad)
                self.assertIn("频道", str(ctx.exception))


class ListAuthTest(TgClientTestCase):
    def test_unauthorized_raises_chinese_error(self):
        FakeClient.authorized = False
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.list_channel_media(self.session_config(), "chan")
        self.assertEqual(str(ctx.exception), "尚未登录或会话已失效")
        self.assertTrue(self.client.disconnected)

    def test_is_user_authorized_failure(self):
        with mock.patch.object(
            FakeClient, "is_user_authorized", side_effect=AuthKeyUnregisteredError(None)
        ):
            with self.assertRaises(TgAuthError) as ctx:
                tg_dl.list_channel_media(self.session_config(), "chan")
        self.assertEqual(str(ctx.exception), "尚未登录或会话已失效")

    def test_session_expires_while_iterating(self):
        FakeClient.iter_error = AuthKeyUnregisteredError(None)
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.list_channel_media(self.session_config(), "chan")
        self.assertEqual(str(ctx.exception), "尚未登录或会话已失效")
        self.assertTrue(self.client.disconnected)


class ListErrorTest(TgClientTestCase):
    def test_entity_resolution_failure(self):
        FakeClient.entity_error = ValueError("Cannot find any entity")
        with self.assertRaises(TgDownloadError) as ctx:
            tg_dl.list_channel_media(self.session_config(), "missing_channel")
        self.assertIn("无法解析频道", str(ctx.exception))
        self.assertTrue(self.client.disconnected)

    def test_flood_wait_under_limit_continues(self):
        FakeClient.messages = [FakeMessage(1, "photo"), FakeMessage(2, "video")]
        FakeClient.iter_flood_seconds = 30
        with fake_clock():
            info = tg_dl.list_channel_media(self.session_config(), "chan")
        self.assertEqual(len(info.items), 2)

    def test_flood_wait_over_limit_raises_with_seconds(self):
        FakeClient.messages = [FakeMessage(1, "photo")]
        FakeClient.iter_flood_seconds = 120
        with self.assertRaises(TgDownloadError) as ctx:
            tg_dl.list_channel_media(self.session_config(), "chan")
        self.assertIn("120", str(ctx.exception))

    def test_cancel_before_start_does_not_connect(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(TgCancelledError):
            tg_dl.list_channel_media(self.session_config(), "chan", cancel=event)
        self.assertEqual(FakeClient.instances, [])

    def test_cancel_during_iteration(self):
        FakeClient.messages = [FakeMessage(1, "photo"), FakeMessage(2, "photo")]
        with self.assertRaises(TgCancelledError) as ctx:
            tg_dl.list_channel_media(self.session_config(), "chan", cancel=_CancelAfter(2))
        self.assertIn("取消", str(ctx.exception))
        self.assertTrue(self.client.disconnected)

    def test_title_falls_back_to_username_then_target(self):
        FakeClient.messages = []
        FakeClient.entity = FakeEntity(title="", username="only_name")
        self.assertEqual(tg_dl.list_channel_media(self.session_config(), "chan").title, "only_name")

        FakeClient.entity = FakeEntity(title="", username="")
        info = tg_dl.list_channel_media(self.session_config(), "chan")
        self.assertEqual(info.title, "chan")
        self.assertEqual(info.username, "")
