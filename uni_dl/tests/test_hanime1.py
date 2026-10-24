"""hanime1.me 站点预解析离线测试。"""

import unittest
from unittest import mock

import requests

import uni_dl
from uni_dl import UniDownloadError, _resolve_hanime1, _resolve_site_media, parse_input

_ORIGINAL_CURL_CFFI = uni_dl._curl_cffi_requests


def setUpModule():
    uni_dl._curl_cffi_requests = None


def tearDownModule():
    uni_dl._curl_cffi_requests = _ORIGINAL_CURL_CFFI


PAGE = """<html><head><title>[dlaldn] Azur Lane II&nbsp;-&nbsp;H动漫&nbsp;-&nbsp;Hanime1.me</title></head>
<body>
<script>var u = "https://vdownload-8.hembed.com/166410-720p.mp4?token=a&amp;expires=1";</script>
<script>var u = "https://vdownload-8.hembed.com/166410-480p.mp4?token=b&amp;expires=1";</script>
<script>var u = "https://vdownload-8.hembed.com/166410-1080p.mp4?token=c&amp;expires=1";</script>
</body></html>"""

PAGE_NO_1080 = """<html><head><title>Demo&nbsp;-&nbsp;Hanime1.me</title></head><body>
<script>var u = "https://vdownload-8.hembed.com/1-480p.mp4?token=x";</script>
<script>var u = "https://vdownload-8.hembed.com/1-720p.mp4?token=y";</script>
</body></html>"""

BEST = "https://vdownload-8.hembed.com/166410-1080p.mp4?token=c&expires=1"


class HanimeResolveTest(unittest.TestCase):
    def test_picks_highest_quality_and_unescapes(self):
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = PAGE
            result = _resolve_hanime1("https://hanime1.me/watch?v=166410")
        self.assertEqual(result["media_url"], BEST)
        self.assertEqual(result["title"], "[dlaldn] Azur Lane II")
        self.assertEqual(result["extractor"], "hanime1")

    def test_second_best_when_no_1080(self):
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = PAGE_NO_1080
            result = _resolve_hanime1("https://hanime1.me/watch?v=1")
        self.assertIn("720p", result["media_url"])

    def test_proxy_forwarded(self):
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = PAGE
            _resolve_hanime1("https://hanime1.me/watch?v=1", proxy="http://127.0.0.1:7890")
        kwargs = get.call_args.kwargs
        self.assertEqual(kwargs["proxies"], {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"})

    def test_403_cloudflare_message(self):
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 403
            get.return_value.text = ""
            with self.assertRaises(UniDownloadError) as ctx:
                _resolve_hanime1("https://hanime1.me/watch?v=1")
        self.assertIn("Cloudflare", str(ctx.exception))

    def test_request_error_message(self):
        with mock.patch("uni_dl.requests.get", side_effect=requests.RequestException("boom")):
            with self.assertRaises(UniDownloadError) as ctx:
                _resolve_hanime1("https://hanime1.me/watch?v=1")
        self.assertIn("无法访问站点页面", str(ctx.exception))

    def test_no_media_message(self):
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = "<html><body>empty</body></html>"
            with self.assertRaises(UniDownloadError) as ctx:
                _resolve_hanime1("https://hanime1.me/watch?v=1")
        self.assertIn("未在该页面找到视频源", str(ctx.exception))

    def test_site_matching(self):
        self.assertIsNone(_resolve_site_media("https://example.com/v"))
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = PAGE
            result = _resolve_site_media("https://www.hanime1.me/watch?v=1")
        self.assertEqual(result["extractor"], "hanime1")


class HanimeParseIntegrationTest(unittest.TestCase):
    def test_parse_uses_resolved_direct_url(self):
        with mock.patch("uni_dl.requests.get") as get, mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls:
            get.return_value.status_code = 200
            get.return_value.text = PAGE
            ydl_cls.return_value.extract_info.return_value = {"id": "x", "title": "166410-1080p", "duration": 300}
            meta = parse_input("https://hanime1.me/watch?v=166410")
        self.assertEqual(meta.url, BEST)
        self.assertEqual(meta.title, "[dlaldn] Azur Lane II")
        self.assertEqual(meta.webpage_url, "https://hanime1.me/watch?v=166410")
        self.assertEqual(meta.extractor, "hanime1")
        ydl_cls.return_value.extract_info.assert_called_once_with(BEST, download=False, process=True)

    def test_parse_falls_back_when_ytdlp_fails(self):
        with mock.patch("uni_dl.requests.get") as get, mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls:
            get.return_value.status_code = 200
            get.return_value.text = PAGE
            ydl_cls.return_value.extract_info.side_effect = uni_dl.yt_dlp.utils.DownloadError("boom")
            meta = parse_input("https://hanime1.me/watch?v=166410")
        self.assertEqual(meta.url, BEST)
        self.assertEqual(meta.title, "[dlaldn] Azur Lane II")
        self.assertEqual(meta.extractor, "hanime1")
        self.assertEqual(meta.duration, 0)


class ImpersonationFetchTest(unittest.TestCase):
    def setUp(self):
        self._orig = uni_dl._curl_cffi_requests

    def tearDown(self):
        uni_dl._curl_cffi_requests = self._orig

    def test_prefers_impersonated_200(self):
        fake = mock.Mock()
        fake.get.return_value = mock.Mock(status_code=200, text="ok")
        with mock.patch.object(uni_dl, "_curl_cffi_requests", fake):
            resp = uni_dl._fetch_page("https://hanime1.me/watch?v=1")
        self.assertEqual(resp.text, "ok")
        self.assertTrue(fake.get.called)

    def test_falls_back_to_requests_when_impersonation_fails(self):
        fake = mock.Mock()
        fake.get.return_value = mock.Mock(status_code=403, text="")
        with mock.patch.object(uni_dl, "_curl_cffi_requests", fake), mock.patch("uni_dl.requests.get") as get:
            get.return_value = mock.Mock(status_code=200, text="via requests")
            resp = uni_dl._fetch_page("https://hanime1.me/watch?v=1")
        self.assertEqual(resp.text, "via requests")


if __name__ == "__main__":
    unittest.main()
