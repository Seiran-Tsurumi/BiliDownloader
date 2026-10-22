import unittest
from unittest import mock

from bili_dl import ApiError, VideoMeta
from bili_dl.download import list_qualities

META = VideoMeta(bvid="BV1GJ411x7h7", aid=1, cid=1, title="t", owner_name="u", duration=10)


def play_payload():
    return {
        "quality": 64,
        "accept_quality": [127, 120, 116, 112, 80, 74, 64, 32, 16],
        "accept_description": [
            "8K 超高清", "4K 超清", "1080P 60帧", "1080P 高码率",
            "1080P 高清", "720P 60帧", "720P 高清", "480P 清晰", "360P 流畅",
        ],
        "dash": {
            "video": [{"id": q, "baseUrl": f"http://example/{q}.m4s"} for q in (80, 64, 32, 16)],
            "audio": [{"id": 30280, "baseUrl": "http://example/a.m4s", "codecs": "mp4a.40.2"}],
        },
    }


class ListQualitiesTest(unittest.TestCase):
    def test_sorted_desc_with_descriptions(self):
        with mock.patch("bili_dl.download.fetch_playurl", return_value=play_payload()) as fetch:
            result = list_qualities(META)
        fetch.assert_called_once_with(META, 127, None)
        qns = [q.qn for q in result]
        self.assertEqual(qns, sorted(qns, reverse=True))
        self.assertEqual(result[0].qn, 127)
        self.assertEqual(result[0].desc, "8K 超高清")
        by_qn = {q.qn: q.desc for q in result}
        self.assertEqual(by_qn[80], "1080P 高清")

    def test_fallback_description_map(self):
        payload = play_payload()
        payload["accept_description"] = []
        payload["accept_quality"] = [80, 64, 32, 16]
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            result = list_qualities(META)
        self.assertEqual([q.desc for q in result], ["1080P 高清", "720P 高清", "480P 清晰", "360P 流畅"])

    def test_fallback_to_dash_ids_when_no_accept_list(self):
        payload = play_payload()
        payload["accept_quality"] = []
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            result = list_qualities(META)
        self.assertEqual([q.qn for q in result], [80, 64, 32, 16])

    def test_api_error_propagates(self):
        with mock.patch(
            "bili_dl.download.fetch_playurl",
            side_effect=ApiError("获取播放地址失败：风控校验失败（code -352）"),
        ):
            with self.assertRaises(ApiError):
                list_qualities(META)

    def test_bad_cookie_raises_chinese_api_error(self):
        with mock.patch("bili_dl.download.fetch_playurl") as fetch:
            with self.assertRaises(ApiError) as ctx:
                list_qualities(META, cookie="SESSDATA=bad")
            self.assertIn("Cookie 无效", str(ctx.exception))
        fetch.assert_not_called()
