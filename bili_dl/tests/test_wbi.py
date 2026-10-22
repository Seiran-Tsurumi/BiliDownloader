import hashlib
import unittest
from unittest import mock

import bili_dl.wbi as wbi

MIXIN_KEY = "ea1db124af3c7062474693fa704f4ff8"
IMG_URL = "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png"
SUB_URL = "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png"


class WbiSignTest(unittest.TestCase):
    def test_mixin_key_from_nav_urls_matches_official_example(self):
        self.assertEqual(wbi.mixin_key_from(IMG_URL, SUB_URL), MIXIN_KEY)

    def test_wbi_sign_matches_official_example(self):
        with mock.patch("bili_dl.wbi.time.time", return_value=1702204169):
            query = wbi.wbi_sign({"foo": "114", "bar": "514", "zab": "1919810"}, MIXIN_KEY)
        base = "bar=514&foo=114&wts=1702204169&zab=1919810"
        expected_rid = hashlib.md5((base + MIXIN_KEY).encode("utf-8")).hexdigest()
        self.assertEqual(query, f"{base}&w_rid={expected_rid}")
        self.assertEqual(expected_rid, "8f6f2b5b3d485fe1886cec6a0be8c5d4")

    def test_wbi_sign_filters_special_chars(self):
        with mock.patch("bili_dl.wbi.time.time", return_value=1702204169):
            query = wbi.wbi_sign({"foo": "11!4", "bar": "5(1'4)*"}, MIXIN_KEY)
        base = query.split("&w_rid=")[0]
        self.assertEqual(base, "bar=514&foo=114&wts=1702204169")

    def test_get_mixin_key_uses_nav_and_caches(self):
        payload = {"code": 0, "data": {"wbi_img": {"img_url": IMG_URL, "sub_url": SUB_URL}}}
        wbi._mixin_key_cache = None
        with mock.patch("bili_dl.wbi.http_get_json", return_value=payload) as mocked:
            self.assertEqual(wbi.get_mixin_key(), MIXIN_KEY)
            self.assertEqual(wbi.get_mixin_key(), MIXIN_KEY)
        self.assertEqual(mocked.call_count, 1)
