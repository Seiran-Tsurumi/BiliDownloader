"""非媒体附件（.attach）保留与 Content-Type 过滤测试。"""

import tempfile
import unittest
import zipfile
from unittest import mock

from page_dl import MediaItem, PageBundle, download_page, parse_page
from page_dl import parse as parse_mod
from page_dl.tests.fakes import FakeResponse


class AttachParseTest(unittest.TestCase):
    def test_attach_anchor_kept(self):
        html = (
            "<html><head><title>附件页</title></head><body>"
            '<a href="files/a.attach">附件</a>'
            '<a href="page.html">页面</a>'
            "</body></html>"
        )
        with mock.patch.object(parse_mod, "_curl_cffi_requests", None), mock.patch(
            "page_dl.parse.requests.get", return_value=FakeResponse(html)
        ):
            bundle = parse_page("https://example.com/page")
        names = [item.filename for item in bundle.items]
        self.assertIn("a.attach", names)
        self.assertNotIn("page.html", names)


class ContentFilterTest(unittest.TestCase):
    def _bundle(self, items):
        return PageBundle(url="https://example.com/p", title="t", items=items)

    def test_html_response_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle([
                MediaItem("https://example.com/bad.png", "image", "bad.png"),
                MediaItem("https://example.com/good.png", "image", "good.png"),
            ])

            def fake_get(url, **kwargs):
                if url.endswith("bad.png"):
                    return FakeResponse(b"<html>", headers={"Content-Type": "text/html"})
                return FakeResponse(b"P" * 5000, headers={"Content-Type": "image/png"})

            with mock.patch("page_dl.download.requests.get", side_effect=fake_get):
                path = download_page(bundle, save_dir=tmp)
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                manifest = archive.read("清单.txt").decode("utf-8")
            self.assertIn("图片/good.png", names)
            self.assertNotIn("图片/bad.png", names)
            self.assertIn("跳过", manifest)

    def test_attach_kept_even_if_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self._bundle([
                MediaItem("https://example.com/a.attach", "other", "a.attach"),
            ])
            with mock.patch(
                "page_dl.download.requests.get",
                return_value=FakeResponse(b"<html>", headers={"Content-Type": "text/html"}),
            ):
                path = download_page(bundle, save_dir=tmp)
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
            self.assertIn("其他/a.attach", names)


if __name__ == "__main__":
    unittest.main()