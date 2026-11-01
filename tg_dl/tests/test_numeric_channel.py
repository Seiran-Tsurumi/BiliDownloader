"""web.telegram.org 链接归一化与数字 ID 在对话列表中解析的测试。"""

import unittest
from unittest import mock

import tg_dl


class NormalizeChannelTest(unittest.TestCase):
    def test_web_link_numeric(self):
        self.assertEqual(
            tg_dl._normalize_channel("https://web.telegram.org/k/#-2927538994"),
            -2927538994,
        )

    def test_web_link_username(self):
        self.assertEqual(
            tg_dl._normalize_channel("https://web.telegram.org/a/#@somechannel"),
            "somechannel",
        )

    def test_tme_link_still_works(self):
        self.assertEqual(tg_dl._normalize_channel("https://t.me/foo"), "foo")

    def test_plain_numeric_id(self):
        self.assertEqual(tg_dl._normalize_channel("-1002927538994"), -1002927538994)


class DialogFallbackTest(unittest.TestCase):
    def test_numeric_id_found_in_dialogs(self):
        client = mock.Mock()
        client.get_entity.side_effect = ValueError("Cannot find any entity")
        entity = mock.Mock(id=2927538994)
        client.iter_dialogs.return_value = [
            mock.Mock(entity=mock.Mock(id=1)),
            mock.Mock(entity=entity),
        ]
        self.assertIs(tg_dl._resolve_entity(client, "-2927538994"), entity)

    def test_missing_numeric_id_raises(self):
        client = mock.Mock()
        client.get_entity.side_effect = ValueError("Cannot find any entity")
        client.iter_dialogs.return_value = []
        with self.assertRaises(tg_dl.TgDLError):
            tg_dl._resolve_entity(client, "-2927538994")


if __name__ == "__main__":
    unittest.main()