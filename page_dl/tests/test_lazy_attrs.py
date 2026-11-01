"""Discuz 懒加载属性与图片尺寸变体去重测试。"""

import unittest
from unittest import mock

from page_dl import parse_page
from page_dl import parse as parse_mod
from page_dl.tests.fakes import FakeResponse

PAGE = """<html><head><title>懒加载页</title></head><body>
<img src="static/image/common/none.gif" file="https://cdn.example.com/a.jpg.thumb.jpg" zoomfile="https://cdn.example.com/a.jpg.1500x1500.jpg">
<img src="static/image/common/none.gif" file="https://cdn.example.com/b.jpg.thumb.jpg">
<img src="https://cdn.example.com/c.jpg">
<a href="https://cdn.example.com/d.jpg">原图</a>
<a href="https://cdn.example.com/d.jpg.1500x1500.jpg">大图</a>
</body></html>"""


class LazyAttrTest(unittest.TestCase):
    def _parse(self):
        with mock.patch.object(parse_mod, "_curl_cffi_requests", None), mock.patch(
            "page_dl.parse.requests.get", return_value=FakeResponse(PAGE)
        ):
            return parse_page("https://example.com/thread-1-1.html")

    def test_zoomfile_preferred_over_placeholder(self):
        urls = [item.url for item in self._parse().items]
        self.assertIn("https://cdn.example.com/a.jpg.1500x1500.jpg", urls)
        self.assertNotIn("https://cdn.example.com/a.jpg.thumb.jpg", urls)
        self.assertFalse(any("none.gif" in url for url in urls))

    def test_file_used_when_no_zoomfile(self):
        urls = [item.url for item in self._parse().items]
        self.assertIn("https://cdn.example.com/b.jpg.thumb.jpg", urls)

    def test_plain_src_kept(self):
        urls = [item.url for item in self._parse().items]
        self.assertIn("https://cdn.example.com/c.jpg", urls)

    def test_variant_duplicate_merged(self):
        urls = [item.url for item in self._parse().items]
        self.assertEqual(sum(1 for url in urls if "d.jpg" in url), 1)


if __name__ == "__main__":
    unittest.main()