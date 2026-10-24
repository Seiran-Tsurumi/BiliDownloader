"""uni_dl 加速器/代理/自动重试离线测试：全部 mock，不联网。"""

import os
import sys
import tempfile
import unittest
from unittest import mock

import uni_dl
from uni_dl import (
    UniCancelledError,
    UniDownloadError,
    UniInputError,
    UniversalMeta,
    detect_local_proxy,
    download_video,
    has_accelerator,
    parse_input,
)
from uni_dl.tests.test_yhdmtv import MEDIA, _page_html

_ORIGINAL_CURL_CFFI = uni_dl._curl_cffi_requests


def setUpModule():
    # 离线测试：禁用 curl_cffi 伪装，避免真实网络请求
    uni_dl._curl_cffi_requests = None


def tearDownModule():
    uni_dl._curl_cffi_requests = _ORIGINAL_CURL_CFFI


PROXY = "http://127.0.0.1:7890"
ARIA2 = "E:/tools/aria2/aria2c.exe"
PAGE = "https://www.yhdmtv.cc/p/1033515/1/22254091"
ARIA2_ARGS = [
    "-x", "8",
    "-s", "8",
    "-k", "1M",
    "--file-allocation=none",
    "--console-log-level=warn",
    "--retry-wait=1",
    "--max-tries=5",
    "--connect-timeout=10",
    "--timeout=20",
]


def make_meta(url="https://example.com/video/1", **kwargs):
    data = {"url": url}
    data.update(kwargs)
    return UniversalMeta(**data)


def fake_connection(open_ports, calls):
    """模拟 socket.create_connection：仅在 open_ports 内的端口上成功。"""

    def connect(address, timeout=None):
        calls.append((address, timeout))
        if address[1] in open_ports:
            return mock.Mock()
        raise OSError("connection refused")

    return connect


class HasAcceleratorTest(unittest.TestCase):
    def test_found_when_candidate_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "aria2c.exe")
            with open(exe, "wb") as fh:
                fh.write(b"MZ")
            with mock.patch(
                "uni_dl._aria2_candidates",
                return_value=[os.path.join(tmp, "missing.exe"), exe],
            ):
                self.assertTrue(has_accelerator())
                self.assertEqual(uni_dl._aria2c_path(), exe)

    def test_missing_when_no_candidate_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "uni_dl._aria2_candidates",
                return_value=[os.path.join(tmp, "aria2c.exe")],
            ):
                self.assertFalse(has_accelerator())
                self.assertIsNone(uni_dl._aria2c_path())

    def test_candidates_put_packaged_dir_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sys, "_MEIPASS", tmp, create=True):
                paths = uni_dl._aria2_candidates()
        root = os.path.dirname(os.path.dirname(os.path.abspath(uni_dl.__file__)))
        expected_rel = os.path.join("tools", "aria2", "aria2c.exe")
        self.assertEqual(paths[0], os.path.join(tmp, expected_rel))
        self.assertEqual(paths[1], os.path.join(root, expected_rel))

    def test_repo_binary_is_detected(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(uni_dl.__file__)))
        exe = os.path.join(root, "tools", "aria2", "aria2c.exe")
        if not os.path.isfile(exe):
            self.skipTest("仓库未提供 tools/aria2/aria2c.exe")
        self.assertTrue(has_accelerator())


class DetectLocalProxyTest(unittest.TestCase):
    MAPPING = {
        12334: "http://127.0.0.1:12334",
        7890: "http://127.0.0.1:7890",
        7891: "socks5://127.0.0.1:7891",
        10809: "http://127.0.0.1:10809",
        10808: "socks5://127.0.0.1:10808",
        1080: "socks5://127.0.0.1:1080",
        2080: "http://127.0.0.1:2080",
        8889: "http://127.0.0.1:8889",
        20171: "http://127.0.0.1:20171",
    }

    def test_port_to_proxy_url_mapping(self):
        for port, expected in self.MAPPING.items():
            with self.subTest(port=port):
                calls = []
                with mock.patch(
                    "uni_dl.socket.create_connection",
                    side_effect=fake_connection({port}, calls),
                ):
                    self.assertEqual(detect_local_proxy(), expected)

    def test_probe_uses_localhost_and_short_timeout(self):
        calls = []
        with mock.patch(
            "uni_dl.socket.create_connection",
            side_effect=fake_connection(set(), calls),
        ):
            self.assertIsNone(detect_local_proxy())
        self.assertTrue(calls)
        for address, timeout in calls:
            self.assertEqual(address[0], "127.0.0.1")
            self.assertEqual(timeout, 0.2)

    def test_no_proxy_returns_none_after_all_ports(self):
        calls = []
        with mock.patch(
            "uni_dl.socket.create_connection",
            side_effect=fake_connection(set(), calls),
        ):
            self.assertIsNone(detect_local_proxy())
        self.assertEqual([address[1] for address, _ in calls], list(self.MAPPING))

    def test_first_available_port_wins(self):
        calls = []
        with mock.patch(
            "uni_dl.socket.create_connection",
            side_effect=fake_connection({12334, 7890, 10809}, calls),
        ):
            self.assertEqual(detect_local_proxy(), "http://127.0.0.1:12334")
        self.assertEqual(calls[0][0][1], 12334)

    def test_returned_socket_is_closed(self):
        sock = mock.Mock()
        with mock.patch("uni_dl.socket.create_connection", return_value=sock):
            self.assertEqual(detect_local_proxy(), "http://127.0.0.1:12334")
        sock.close.assert_called_once()


class DownloadHarness(unittest.TestCase):
    """mock yt-dlp 与 ffmpeg，记录每次 download 调用的 (url, params)。"""

    def setUp(self):
        patcher = mock.patch("uni_dl.yt_dlp.YoutubeDL")
        self.ydl_cls = patcher.start()
        self.addCleanup(patcher.stop)
        ffmpeg = mock.patch("uni_dl.get_ffmpeg_exe", return_value="FAKE_FFMPEG")
        ffmpeg.start()
        self.addCleanup(ffmpeg.stop)
        self.ydl = self.ydl_cls.return_value
        self.attempts = []

    def run_download(self, behavior, meta=None, **kwargs):
        def side_effect(urls):
            params = self.ydl_cls.call_args.args[0]
            index = len(self.attempts)
            self.attempts.append((urls[0], params))
            behavior(index, params)
            return 0

        self.ydl.download.side_effect = side_effect
        return download_video(meta or make_meta(), **kwargs)


class ProxyParamsTest(DownloadHarness):
    def test_parse_passes_proxy_to_ytdlp_and_requests(self):
        with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls, mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = _page_html()
            ydl_cls.return_value.extract_info.return_value = {"id": "x", "title": "index"}
            meta = parse_input(PAGE, proxy=PROXY)
            params = ydl_cls.call_args.args[0]
            get_kwargs = get.call_args.kwargs
        self.assertEqual(meta.url, MEDIA)
        self.assertEqual(params["proxy"], PROXY)
        self.assertEqual(get_kwargs["proxies"], {"http": PROXY, "https": PROXY})

    def test_parse_without_proxy_omits_proxy_params(self):
        with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls, mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = _page_html()
            ydl_cls.return_value.extract_info.return_value = {"id": "x", "title": "index"}
            parse_input(PAGE)
            params = ydl_cls.call_args.args[0]
            get_kwargs = get.call_args.kwargs
        self.assertNotIn("proxy", params)
        self.assertNotIn("proxies", get_kwargs)

    def test_blank_and_none_proxy_are_ignored(self):
        for blank in (None, "", "   "):
            with self.subTest(proxy=blank):
                with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls:
                    ydl_cls.return_value.extract_info.return_value = {"id": "x"}
                    parse_input("https://example.com/v", proxy=blank)
                    self.assertNotIn("proxy", ydl_cls.call_args.args[0])

    def test_invalid_proxy_type_rejected(self):
        with self.assertRaises(UniInputError):
            parse_input("https://example.com/v", proxy=123)

    def test_download_passes_proxy(self):
        self.run_download(
            lambda index, params: params["post_hooks"][0]("out.mp4"),
            proxy=PROXY,
            accelerator=False,
        )
        self.assertEqual(self.attempts[0][1]["proxy"], PROXY)


class AcceleratorParamsTest(DownloadHarness):
    def test_accelerator_true_sets_external_downloader(self):
        with mock.patch("uni_dl._aria2c_path", return_value=ARIA2):
            result = self.run_download(lambda index, params: params["post_hooks"][0]("out.mp4"))
        params = self.attempts[0][1]
        self.assertEqual(result, [os.path.abspath("out.mp4")])
        self.assertEqual(params["external_downloader"], {"http": ARIA2})
        self.assertEqual(params["external_downloader_args"], {"aria2c": ARIA2_ARGS})

    def test_builtin_fallback_params_kept_with_accelerator(self):
        with mock.patch("uni_dl._aria2c_path", return_value=ARIA2):
            self.run_download(lambda index, params: params["post_hooks"][0]("out.mp4"))
        params = self.attempts[0][1]
        self.assertEqual(params["http_chunk_size"], 10 * 1024 * 1024)
        self.assertEqual(params["retries"], 10)
        self.assertTrue(params["continuedl"])
        self.assertEqual(params["socket_timeout"], 30)

    def test_accelerator_false_keeps_builtin_downloader(self):
        self.run_download(lambda index, params: params["post_hooks"][0]("out.mp4"),
                          accelerator=False)
        params = self.attempts[0][1]
        self.assertNotIn("external_downloader", params)
        self.assertNotIn("external_downloader_args", params)
        self.assertEqual(params["http_chunk_size"], 10 * 1024 * 1024)

    def test_accelerator_true_without_binary_keeps_builtin(self):
        with mock.patch("uni_dl._aria2c_path", return_value=None):
            self.run_download(lambda index, params: params["post_hooks"][0]("out.mp4"))
        self.assertNotIn("external_downloader", self.attempts[0][1])


class RetryTest(DownloadHarness):
    def test_first_failure_retries_with_builtin_downloader(self):
        def behavior(index, params):
            if index == 0:
                params["logger"].error("ERROR: IncompleteRead(137182884 bytes read)")
                return
            params["post_hooks"][0]("out.mp4")

        with mock.patch("uni_dl._aria2c_path", return_value=ARIA2):
            result = self.run_download(behavior)
        self.assertEqual(len(self.attempts), 2)
        self.assertIn("external_downloader", self.attempts[0][1])
        self.assertNotIn("external_downloader", self.attempts[1][1])
        self.assertEqual(result, [os.path.abspath("out.mp4")])

    def test_410_reparses_page_then_third_attempt_succeeds(self):
        def behavior(index, params):
            if index < 2:
                params["logger"].error("ERROR: HTTP Error 410: Gone")
                return
            params["post_hooks"][0]("out.mp4")

        with mock.patch("uni_dl._aria2c_path", return_value=ARIA2), \
                mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = _page_html()
            result = self.run_download(
                behavior,
                meta=make_meta(url="https://cdn.old/expired.m3u8", webpage_url=PAGE),
            )
        self.assertEqual(len(self.attempts), 3)
        self.assertEqual(self.attempts[0][0], "https://cdn.old/expired.m3u8")
        self.assertEqual(self.attempts[1][0], "https://cdn.old/expired.m3u8")
        self.assertEqual(self.attempts[2][0], MEDIA)
        self.assertNotIn("external_downloader", self.attempts[1][1])
        self.assertNotIn("external_downloader", self.attempts[2][1])
        self.assertEqual(result, [os.path.abspath("out.mp4")])
        get.assert_called_once()

    def test_403_reparse_uses_resolved_url(self):
        def behavior(index, params):
            if index < 2:
                params["logger"].error("ERROR: HTTP Error 403: Forbidden")
                return
            params["post_hooks"][0]("out.mp4")

        resolved = {"media_url": "https://cdn.new/fresh.m3u8", "title": "t", "extractor": "yhdmtv"}
        with mock.patch("uni_dl._resolve_site_media", return_value=resolved) as resolver:
            result = self.run_download(behavior, meta=make_meta(webpage_url=PAGE))
        resolver.assert_called_once_with(PAGE, proxy=None)
        self.assertEqual(self.attempts[2][0], "https://cdn.new/fresh.m3u8")
        self.assertEqual(result, [os.path.abspath("out.mp4")])

    def test_unknown_site_stops_after_two_attempts(self):
        def behavior(index, params):
            params["logger"].error("ERROR: HTTP Error 403: Forbidden")

        with self.assertRaises(UniDownloadError) as ctx:
            self.run_download(behavior, meta=make_meta(url="https://example.com/v/1",
                                                       webpage_url="https://example.com/v/1"))
        self.assertEqual(len(self.attempts), 2)
        self.assertIn("站点拒绝访问", str(ctx.exception))

    def test_final_failure_mentions_reparse(self):
        def behavior(index, params):
            params["logger"].error("ERROR: HTTP Error 410: Gone")

        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = _page_html()
            with self.assertRaises(UniDownloadError) as ctx:
                self.run_download(behavior, meta=make_meta(
                    url="https://cdn.old/expired.m3u8", webpage_url=PAGE))
        message = str(ctx.exception)
        self.assertIn("已尝试重新解析", message)
        self.assertIn("令牌", message)
        self.assertEqual(len(self.attempts), 3)

    def test_cancel_is_checked_before_retry(self):
        flags = {"cancelled": False}

        def behavior(index, params):
            if index == 0:
                flags["cancelled"] = True
                params["logger"].error("ERROR: IncompleteRead(1 bytes read)")
                return
            params["post_hooks"][0]("out.mp4")

        with self.assertRaises(UniCancelledError):
            self.run_download(behavior, cancel=lambda: flags["cancelled"])
        self.assertEqual(len(self.attempts), 1)

    def test_done_progress_reported_once_and_paths_deduped(self):
        stages = []

        def behavior(index, params):
            if index == 0:
                params["logger"].error("ERROR: IncompleteRead(1 bytes read)")
                return
            params["post_hooks"][0]("out.mp4")
            params["post_hooks"][0]("out.mp4")

        result = self.run_download(
            behavior, progress=lambda stage, done, total: stages.append(stage))
        self.assertEqual(stages.count("done"), 1)
        self.assertEqual(result, [os.path.abspath("out.mp4")])


if __name__ == "__main__":
    unittest.main()
