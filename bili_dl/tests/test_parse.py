import unittest
from unittest import mock

import bili_dl.parse as parse_mod
from bili_dl import ApiError, InputError, VideoMeta

VALID_CASES = [
    "BV1GJ411x7h7",
    "  BV1GJ411x7h7  ",
    "https://www.bilibili.com/video/BV1GJ411x7h7",
    "https://www.bilibili.com/video/BV1GJ411x7h7?p=1&t=60&vd_source=abc123",
    "https://www.bilibili.com/video/BV1GJ411x7h7/",
    "http://www.bilibili.com/video/BV1xx411c7mD?spm_id_from=333.337",
]

INVALID_CASES = [
    ("", "空串"),
    ("   ", "纯空白"),
    ("hello world", "垃圾串"),
    ("av170001", "av号"),
    ("BV123", "太短"),
    ("BV1GJ411x7h", "9位"),
    ("BV1GJ411x7h70", "11位"),
    ("BV0GJ411x7h7", "含字符0"),
    ("BVIlO0xxxxxx", "含非法字符"),
    ("bv1GJ411x7h7", "小写前缀"),
    ("BV1GJ411x7h7 尾巴", "BV带尾巴"),
    ("https://www.bilibili.com/video/av170001", "av链接"),
    ("https://www.bilibili.com/video/BV1GJ411x7h70", "链接BV非法"),
    ("https://www.bilibili.com/", "主页"),
    ("https://space.bilibili.com/2", "空间主页"),
    ("https://www.bilibili.com/list/ml123", "合集"),
    ("https://www.bilibili.com/medialist/detail/ml123", "收藏夹列表"),
    ("https://www.bilibili.com/cheese/play/ss123", "课程"),
    ("https://www.bilibili.com/bangumi/play/ep123", "番剧"),
    ("https://www.bilibili.com/live/123", "直播路径"),
    ("https://live.bilibili.com/123", "直播域名"),
    ("https://bangumi.bilibili.com/anime", "番剧域名"),
    ("https://b23.tv/abc123", "短链接"),
    ("https://example.com/video/BV1GJ411x7h7", "非B站域名"),
    ("www.bilibili.com/video/BV1GJ411x7h7", "无协议"),
]


class ParseInputTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch(
            "bili_dl.parse.fetch_view",
            side_effect=lambda bvid, cookie=None: VideoMeta(
                bvid=bvid, aid=170001, cid=226518431, title="测试标题", owner_name="示例UP主", duration=213
            ),
        )
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)

    def test_valid_inputs(self):
        for text in VALID_CASES:
            with self.subTest(text=text):
                meta = parse_mod.parse_input(text)
                self.assertIsInstance(meta, VideoMeta)
                self.assertRegex(meta.bvid, r"^BV[1-9A-HJ-NP-Za-km-z]{10}$")
                self.assertEqual(meta.aid, 170001)
                self.assertEqual(meta.duration, 213)

    def test_invalid_inputs_rejected_without_network(self):
        for text, label in INVALID_CASES:
            with self.subTest(label=label):
                with self.assertRaises(InputError) as ctx:
                    parse_mod.parse_input(text)
                self.assertTrue(str(ctx.exception), label)
        self.assertEqual(self.fetch.call_count, 0)

    def test_api_error_propagates(self):
        self.fetch.side_effect = ApiError("视频不存在或已被删除")
        with self.assertRaises(ApiError) as ctx:
            parse_mod.parse_input("BV1GJ411x7h7")
        self.assertEqual(str(ctx.exception), "视频不存在或已被删除")
