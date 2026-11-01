"""登录页识别与媒体下载 Cookie 透传的离线测试。"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import page_dl
from page_dl import MediaItem, PageBundle, PageDownloadError, download_page, parse_page
from page_dl import parse as parse_mod
from page_dl.tests.fakes import FakeResponse

LOGIN_HTML = """<html><head><title>登录 - 示例站点</title></head><body>
<input type="password" name="pw"><button>登录</button></body></html>"""


def _cookies_file(tmp: Path, domain="example.com") -> Path:
    path = tmp / "cookies.txt"
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        + f"{domain}\tTRUE\t/\tFALSE\t2147483647\tsession\tSECRET\n",
        encoding="utf-8",
    )
    return path


class LoginDetectionTest(unittest.TestCase):
    def _parse(self, html, url="https://example.com/login"):
        with mock.patch.object(parse_mod, "_curl_cffi_requests", None), mock.patch(
            "page_dl.parse.requests.get", return_value=FakeResponse(html)
        ):
            return parse_page(url)

    def test_login_page_raises_chinese_hint(self):
        with self.assertRaises(PageDownloadError) as ctx:
            self._parse(LOGIN_HTML)
        self.assertIn("需要登录", str(ctx.exception))

    def test_password_field_on_normal_page_not_flagged(self):
        html = "<html><head><title>文章</title></head><body><input type=password><img src=a.png></body></html>"
        bundle = self._parse(html, url="https://example.com/article")
        self.assertEqual(bundle.image_count, 1)


class MediaCookieTest(unittest.TestCase):
    def test_cookie_header_sent_for_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie_path = _cookies_file(Path(tmp))
            bundle = PageBundle(
                url="https://example.com/page",
                title="demo",
                items=[MediaItem("https://example.com/img/a.png", "image", "a.png", "https://example.com/page")],
                image_count=1,
            )
            calls = []

            def fake_get(url, **kwargs):
                calls.append(kwargs)
                return FakeResponse(b"PNGDATA")

            with mock.patch("page_dl.download.requests.get", side_effect=fake_get):
                path = download_page(bundle, save_dir=tmp, cookie={"cookiefile": str(cookie_path)})
            self.assertTrue(Path(path).exists())
            self.assertTrue(calls)
            self.assertEqual(calls[0]["headers"].get("Cookie"), "session=SECRET")

    def test_invalid_cookie_dict_rejected(self):
        bundle = PageBundle(
            url="https://example.com/p",
            title="t",
            items=[MediaItem("https://example.com/a.png", "image", "a.png")],
        )
        with self.assertRaises(page_dl.PageInputError):
            download_page(bundle, save_dir=".", cookie={"foo": "bar"})


if __name__ == "__main__":
    unittest.main()