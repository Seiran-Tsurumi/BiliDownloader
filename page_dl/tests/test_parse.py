"""page_dl.parse 离线单测：全部 mock 掉网络，不联网。"""

import os
import tempfile
import unittest
from unittest import mock

import requests

import page_dl
from page_dl import MediaItem, PageBundle, PageDLError, PageDownloadError, PageInputError, parse_page
from page_dl import parse as parse_mod
from page_dl.tests.fakes import FakeResponse

PAGE_URL = "https://example.com/page/index.html"

FULL_HTML = """<!DOCTYPE html>
<html>
<head>
<title>
  测试 &amp; 页面 | 站点
</title>
<style>
  body { background: url('/bg/body.png'); }
  .x { background-image: url("https://cdn.example.com/bg/x.jpg"); }
</style>
</head>
<body>
  <img src="/img/a.jpg">
  <img data-src="b.png">
  <img data-original="https://cdn.example.com/c.webp">
  <img data-lazy-src="d.gif">
  <img srcset="e1.jpg 1x, e2.jpg 2x">
  <picture><source srcset="f.webp 480w"><img src="g.jpg"></picture>
  <video src="v/clip.mp4" poster="p/poster.jpg"></video>
  <source src="clip2.webm">
  <audio src="au/song.mp3"></audio>
  <a href="files/doc.zip">压缩包</a>
  <a href="files/movie.mkv">电影</a>
  <div style="background-image:url(./bg/inline.png)"></div>
  <a href="javascript:void(0)">js</a>
  <a href="mailto:a@b.c">mail</a>
  <a href="#top">anchor</a>
  <img src="data:image/png;base64,AAAA">
  <img src="/img/a.jpg">
</body>
</html>
"""

EXPECTED_URLS = [
    "https://example.com/bg/body.png",
    "https://cdn.example.com/bg/x.jpg",
    "https://example.com/img/a.jpg",
    "https://example.com/page/b.png",
    "https://cdn.example.com/c.webp",
    "https://example.com/page/d.gif",
    "https://example.com/page/e1.jpg",
    "https://example.com/page/e2.jpg",
    "https://example.com/page/f.webp",
    "https://example.com/page/g.jpg",
    "https://example.com/page/v/clip.mp4",
    "https://example.com/page/p/poster.jpg",
    "https://example.com/page/clip2.webm",
    "https://example.com/page/au/song.mp3",
    "https://example.com/page/files/movie.mkv",
    "https://example.com/page/bg/inline.png",
]


def is_chinese(text):
    return any("\u4e00" <= char <= "\u9fff" for char in str(text))


class ParseBase(unittest.TestCase):
    """统一打桩：禁用 curl_cffi、函数内 sleep，便于离线断言。"""

    def setUp(self):
        patchers = [
            mock.patch.object(parse_mod, "_curl_cffi_requests", None),
            mock.patch.object(parse_mod.time, "sleep", lambda *args, **kwargs: None),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_parse(self, html=FULL_HTML, url=PAGE_URL, side_effect=None, response=None, **kwargs):
        get = mock.patch.object(parse_mod.requests, "get").start()
        self.addCleanup(get.stop)
        if side_effect is not None:
            get.side_effect = side_effect
        elif response is not None:
            get.return_value = response
        else:
            get.return_value = FakeResponse(html)
        return parse_page(url, **kwargs), get


class InputValidationTest(ParseBase):
    def test_rejects_non_http(self):
        for bad in ("ftp://example.com/a", "file:///c:/a.html", "example.com/page", "", "   ", None, 123):
            with self.subTest(bad=bad):
                with self.assertRaises(PageInputError) as ctx:
                    parse_page(bad)
                self.assertTrue(is_chinese(ctx.exception))

    def test_rejects_bad_max_items(self):
        for bad in (0, -1, "5", 1.5, True):
            with self.subTest(bad=bad):
                with self.assertRaises(PageInputError):
                    parse_page(PAGE_URL, max_items=bad)

    def test_rejects_bad_proxy(self):
        with self.assertRaises(PageInputError):
            parse_page(PAGE_URL, proxy=123)

    def test_rejects_bad_cookie(self):
        cases = [
            "cookies.txt",
            {"browser": "chrome"},
            {"cookiefile": ""},
            {"cookiefile": 42},
            {"cookiefile": "definitely-missing-cookies.txt"},
        ]
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(PageInputError) as ctx:
                    parse_page(PAGE_URL, cookie=bad)
                self.assertTrue(is_chinese(ctx.exception))

    def test_accepts_empty_proxy(self):
        bundle, get = self.run_parse(proxy="   ")
        self.assertTrue(bundle.items)
        self.assertNotIn("proxies", get.call_args.kwargs)


class ParseContentTest(ParseBase):
    def test_collects_all_sources_in_order(self):
        bundle, _get = self.run_parse()
        self.assertEqual([item.url for item in bundle.items], EXPECTED_URLS)

    def test_classification_and_counts(self):
        bundle, _get = self.run_parse()
        kinds = {item.url: item.kind for item in bundle.items}
        self.assertEqual(kinds["https://example.com/img/a.jpg"], "image")
        self.assertEqual(kinds["https://example.com/page/v/clip.mp4"], "video")
        self.assertEqual(kinds["https://example.com/page/clip2.webm"], "video")
        self.assertEqual(kinds["https://example.com/page/files/movie.mkv"], "video")
        self.assertEqual(kinds["https://example.com/page/au/song.mp3"], "audio")
        self.assertEqual(kinds["https://example.com/page/p/poster.jpg"], "image")
        self.assertEqual(bundle.image_count, 12)
        self.assertEqual(bundle.video_count, 3)
        self.assertEqual(bundle.audio_count, 1)
        self.assertEqual(bundle.other_count, 0)
        self.assertEqual(bundle.skipped, 0)
        self.assertEqual(len(bundle.items), 16)

    def test_title_cleaned(self):
        bundle, _get = self.run_parse()
        self.assertEqual(bundle.title, "测试 & 页面 | 站点")
        self.assertEqual(bundle.url, PAGE_URL)

    def test_title_collapses_separator_runs(self):
        bundle, _get = self.run_parse("<title>  多个    空格 --- 分隔 | 符  </title><img src='a.jpg'>")
        self.assertEqual(bundle.title, "多个 空格 分隔 | 符")

    def test_title_fallback_to_host(self):
        bundle, _get = self.run_parse("<html><body><img src='a.jpg'></body></html>")
        self.assertEqual(bundle.title, "example.com")

    def test_skips_non_media_links_and_pseudo_schemes(self):
        bundle, _get = self.run_parse()
        urls = [item.url for item in bundle.items]
        self.assertNotIn("https://example.com/page/files/doc.zip", urls)
        for url in urls:
            self.assertFalse(url.startswith(("data:", "javascript:", "mailto:")))
            self.assertFalse(url.endswith("#top"))

    def test_dedupes_by_final_url(self):
        bundle, _get = self.run_parse('<img src="/img/a.jpg"><img src="https://example.com/img/a.jpg">')
        self.assertEqual([item.url for item in bundle.items], ["https://example.com/img/a.jpg"])

    def test_relative_and_protocol_relative(self):
        bundle, _get = self.run_parse(
            '<img src="../img/x.png"><img src="//cdn.example.com/y.jpg"><a href="#top">t</a>'
        )
        self.assertEqual(
            [item.url for item in bundle.items],
            ["https://example.com/img/x.png", "https://cdn.example.com/y.jpg"],
        )

    def test_filenames(self):
        bundle, _get = self.run_parse(
            '<img src="/img/%E4%B8%AD%E6%96%87%20pic.jpg"><img src="/download/">'
        )
        self.assertEqual(bundle.items[0].filename, "中文 pic.jpg")
        self.assertEqual(bundle.items[1].filename, "")
        self.assertEqual(bundle.items[1].kind, "other")

    def test_referer_is_page_url(self):
        bundle, _get = self.run_parse()
        self.assertTrue(all(item.referer == PAGE_URL for item in bundle.items))

    def test_max_items_truncates_and_counts_skipped(self):
        bundle, _get = self.run_parse(max_items=5)
        self.assertEqual(len(bundle.items), 5)
        self.assertEqual(bundle.items[0].url, EXPECTED_URLS[0])
        self.assertEqual(bundle.skipped, len(EXPECTED_URLS) - 5)

    def test_unknown_extension_is_other(self):
        bundle, _get = self.run_parse('<a href="files/a.xyz">x</a><img src="b.xyz">')
        self.assertEqual(bundle.other_count, 1)
        self.assertEqual(bundle.items[0].url, "https://example.com/page/b.xyz")

    def test_unclosed_style_block(self):
        bundle, _get = self.run_parse("<style>.a{background:url(/x/only.png)}")
        self.assertEqual([item.url for item in bundle.items], ["https://example.com/x/only.png"])


class RequestTest(ParseBase):
    def test_browser_headers(self):
        bundle, get = self.run_parse()
        headers = get.call_args.kwargs["headers"]
        self.assertIn("Mozilla/5.0", headers["User-Agent"])
        self.assertIn("text/html", headers["Accept"])
        self.assertEqual(get.call_args.args[0], PAGE_URL)

    def test_proxy_passthrough(self):
        proxy = "http://127.0.0.1:7890"
        bundle, get = self.run_parse(proxy=proxy)
        self.assertEqual(get.call_args.kwargs["proxies"], {"http": proxy, "https": proxy})

    def test_cookie_file_header(self):
        cookie_file = self.make_cookie_file(
            [
                "# Netscape HTTP Cookie File",
                "\t".join([".example.com", "TRUE", "/", "FALSE", "1893456000", "sess", "abc123"]),
                "\t".join([".example.com", "TRUE", "/", "FALSE", "1893456000", "uid", "42"]),
                "\t".join(["other.com", "FALSE", "/", "FALSE", "0", "other", "zzz"]),
            ]
        )
        bundle, get = self.run_parse(cookie={"cookiefile": cookie_file})
        self.assertEqual(get.call_args.kwargs["headers"]["Cookie"], "sess=abc123; uid=42")
        self.assertTrue(bundle.items)

    def make_cookie_file(self, lines):
        handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        handle.write("\n".join(lines) + "\n")
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
        return handle.name


class FetchFallbackTest(ParseBase):
    def test_curl_cffi_preferred(self):
        fake = mock.Mock()
        fake.get.return_value = FakeResponse(FULL_HTML)
        with mock.patch.object(parse_mod, "_curl_cffi_requests", fake):
            with mock.patch.object(parse_mod.requests, "get") as get:
                bundle = parse_page(PAGE_URL)
        get.assert_not_called()
        self.assertEqual(fake.get.call_args.kwargs["impersonate"], "chrome")
        self.assertEqual(len(bundle.items), 16)

    def test_curl_cffi_error_falls_back(self):
        fake = mock.Mock()
        fake.get.side_effect = RuntimeError("boom")
        with mock.patch.object(parse_mod, "_curl_cffi_requests", fake):
            with mock.patch.object(parse_mod.requests, "get", return_value=FakeResponse(FULL_HTML)) as get:
                bundle = parse_page(PAGE_URL)
        get.assert_called_once()
        self.assertTrue(bundle.items)

    def test_curl_cffi_bad_status_falls_back(self):
        fake = mock.Mock()
        fake.get.return_value = FakeResponse("blocked", status_code=403)
        with mock.patch.object(parse_mod, "_curl_cffi_requests", fake):
            with mock.patch.object(parse_mod.requests, "get", return_value=FakeResponse(FULL_HTML)) as get:
                bundle = parse_page(PAGE_URL)
        get.assert_called_once()
        self.assertTrue(bundle.items)


class RetryTest(ParseBase):
    def test_retries_twice_then_raises_chinese_error(self):
        with mock.patch.object(parse_mod.requests, "get", side_effect=requests.ConnectionError("net down")) as get:
            with self.assertRaises(PageDownloadError) as ctx:
                parse_page(PAGE_URL)
        self.assertEqual(get.call_count, 3)
        message = str(ctx.exception)
        self.assertIn("页面抓取失败", message)
        self.assertTrue(is_chinese(message))

    def test_recovers_on_second_attempt(self):
        get = mock.patch.object(parse_mod.requests, "get").start()
        self.addCleanup(get.stop)
        get.side_effect = [requests.ConnectionError("x"), FakeResponse(FULL_HTML)]
        bundle = parse_page(PAGE_URL)
        self.assertEqual(get.call_count, 2)
        self.assertTrue(bundle.items)

    def test_http_error_status_is_retried(self):
        with mock.patch.object(parse_mod.requests, "get", return_value=FakeResponse("nope", status_code=500)) as get:
            with self.assertRaises(PageDownloadError):
                parse_page(PAGE_URL)
        self.assertEqual(get.call_count, 3)


class ModelTest(unittest.TestCase):
    def test_defaults(self):
        item = MediaItem("https://example.com/a.jpg", "image", "a.jpg")
        self.assertEqual(item.referer, "")
        bundle = PageBundle(url="https://example.com/", title="t", items=[])
        self.assertEqual(
            (bundle.image_count, bundle.video_count, bundle.audio_count, bundle.other_count, bundle.skipped),
            (0, 0, 0, 0, 0),
        )


if __name__ == "__main__":
    unittest.main()
