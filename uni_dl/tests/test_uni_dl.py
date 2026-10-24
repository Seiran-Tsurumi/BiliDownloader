"""uni_dl 离线单元测试：全部用 unittest.mock 打桩 yt_dlp.YoutubeDL，不联网。"""

import os
import unittest
from unittest import mock

import yt_dlp

import uni_dl
from uni_dl import (
    DEFAULT_FORMAT,
    FORMAT_PRESETS,
    UniCancelledError,
    UniDownloadError,
    UniInputError,
    UniversalMeta,
    download_video,
    parse_input,
)


def make_meta(url="https://example.com/video/1", **kwargs):
    data = {"url": url}
    data.update(kwargs)
    return UniversalMeta(**data)


class FormatPresetsTest(unittest.TestCase):
    def test_presets_exact_content(self):
        self.assertEqual(
            FORMAT_PRESETS,
            [
                ("最高可用", "bestvideo*+bestaudio/best"),
                ("最高画质+最佳音质", "bestvideo+bestaudio/best"),
                ("单一文件（免合并）", "best/bestvideo+bestaudio"),
                ("最低画质", "worst"),
            ],
        )
        self.assertEqual(DEFAULT_FORMAT, FORMAT_PRESETS[0][1])

    def test_cancelled_error_is_ytdlp_cancelled(self):
        self.assertTrue(issubclass(UniCancelledError, uni_dl.UniDLError))
        self.assertTrue(issubclass(UniCancelledError, yt_dlp.utils.DownloadCancelled))


class ParseInputValidationTest(unittest.TestCase):
    def test_rejects_non_string(self):
        for bad in (None, 123, 4.5, b"https://example.com", ["https://example.com"]):
            with self.subTest(bad=bad):
                with self.assertRaises(UniInputError):
                    parse_input(bad)

    def test_rejects_empty_or_blank(self):
        for bad in ("", "   ", "\n\t"):
            with self.subTest(bad=bad):
                with self.assertRaises(UniInputError):
                    parse_input(bad)

    def test_rejects_missing_http_scheme(self):
        for bad in ("www.bilibili.com/video/BV1", "ftp://example.com/a", "file:///tmp/a"):
            with self.subTest(bad=bad):
                with self.assertRaises(UniInputError):
                    parse_input(bad)

    def test_invalid_cookie_raises_input_error(self):
        for bad_cookie in ("chrome", {"foo": "bar"}, {"browser": "safari"}, {"cookiefile": ""},
                           {"browser": "chrome", "cookiefile": "c.txt"}):
            with self.subTest(cookie=bad_cookie):
                with self.assertRaises(UniInputError):
                    parse_input("https://example.com/v", cookie=bad_cookie)


class ParseInputMetaTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("uni_dl.yt_dlp.YoutubeDL")
        self.ydl_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.ydl = self.ydl_cls.return_value

    def test_single_video_mapping(self):
        self.ydl.extract_info.return_value = {
            "id": "bv1",
            "title": "示例视频",
            "uploader": "UP主甲",
            "duration": 125,
            "webpage_url": "https://example.com/video/bv1",
            "extractor_key": "Example",
        }
        meta = parse_input("https://example.com/video/bv1")
        self.assertIsInstance(meta, UniversalMeta)
        self.assertEqual(meta.url, "https://example.com/video/bv1")
        self.assertEqual(meta.title, "示例视频")
        self.assertEqual(meta.uploader, "UP主甲")
        self.assertEqual(meta.duration, 125)
        self.assertFalse(meta.is_playlist)
        self.assertEqual(meta.entry_count, 1)
        self.assertEqual(meta.webpage_url, "https://example.com/video/bv1")
        self.assertEqual(meta.extractor, "Example")
        self.ydl.extract_info.assert_called_once_with(
            "https://example.com/video/bv1", download=False, process=True
        )

    def test_playlist_mapping(self):
        self.ydl.extract_info.return_value = {
            "_type": "playlist",
            "id": "pl1",
            "title": "示例合集",
            "channel": "UP主乙",
            "webpage_url": "https://example.com/playlist/pl1",
            "extractor_key": "ExamplePlaylist",
            "entries": [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}],
        }
        meta = parse_input("https://example.com/playlist/pl1")
        self.assertTrue(meta.is_playlist)
        self.assertEqual(meta.entry_count, 3)
        self.assertEqual(meta.title, "示例合集")
        self.assertEqual(meta.uploader, "UP主乙")
        self.assertEqual(meta.webpage_url, "https://example.com/playlist/pl1")
        self.assertEqual(meta.extractor, "ExamplePlaylist")

    def test_single_video_entry_count_is_one_even_with_entries(self):
        self.ydl.extract_info.return_value = {
            "_type": "video",
            "id": "v1",
            "title": "单视频",
            "entries": [{"id": "e1"}],
        }
        meta = parse_input("https://example.com/video/v1")
        self.assertFalse(meta.is_playlist)
        self.assertEqual(meta.entry_count, 1)

    def test_parse_download_error_becomes_chinese_uni_download_error(self):
        self.ydl.extract_info.side_effect = yt_dlp.utils.DownloadError("Unsupported URL")
        with self.assertRaises(UniDownloadError) as ctx:
            parse_input("https://example.com/video/v1")
        self.assertIn("站点暂不支持", str(ctx.exception))


class CookieConversionTest(unittest.TestCase):
    def assert_params(self, params):
        self.assertIsInstance(params, dict)

    def test_parse_cookiefile_param(self):
        with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls:
            ydl_cls.return_value.extract_info.return_value = {"id": "1"}
            parse_input("https://example.com/v", cookie={"cookiefile": "cookies.txt"})
            params = ydl_cls.call_args.args[0]
            self.assertTrue(params["quiet"])
            self.assertTrue(params["no_warnings"])
            self.assertEqual(params["cookiefile"], "cookies.txt")
            self.assertNotIn("cookiesfrombrowser", params)

    def test_parse_browser_param(self):
        with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls:
            ydl_cls.return_value.extract_info.return_value = {"id": "1"}
            parse_input("https://example.com/v", cookie={"browser": "edge"})
            params = ydl_cls.call_args.args[0]
            self.assertEqual(params["cookiesfrombrowser"], ("edge", None, None, None))
            self.assertNotIn("cookiefile", params)

    def test_download_browser_param(self):
        with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls,              mock.patch("uni_dl.get_ffmpeg_exe", return_value="FF"):
            ydl_cls.return_value.download.side_effect = lambda urls: (
                ydl_cls.call_args.args[0]["post_hooks"][0]("out.mp4")
            )
            download_video(make_meta(), cookie={"browser": "chrome"})
            params = ydl_cls.call_args.args[0]
            self.assertEqual(params["cookiesfrombrowser"], ("chrome", None, None, None))
            self.assertNotIn("cookiefile", params)


class DownloadVideoParamsTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("uni_dl.yt_dlp.YoutubeDL")
        self.ydl_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.ffmpeg_patcher = mock.patch("uni_dl.get_ffmpeg_exe", return_value="FAKE_FFMPEG")
        self.ffmpeg_patcher.start()
        self.addCleanup(self.ffmpeg_patcher.stop)
        self.ydl = self.ydl_cls.return_value

    def _succeed_with_file(self, path="out.mp4"):
        def side_effect(urls):
            self.ydl_cls.call_args.args[0]["post_hooks"][0](path)
            return 0
        self.ydl.download.side_effect = side_effect

    def test_default_params(self):
        self._succeed_with_file()
        result = download_video(make_meta())
        params = self.ydl_cls.call_args.args[0]
        self.assertEqual(result, [os.path.abspath("out.mp4")])
        self.assertEqual(params["format"], DEFAULT_FORMAT)
        self.assertEqual(params["outtmpl"], os.path.join(".", "%(title)s [%(id)s].%(ext)s"))
        self.assertEqual(params["merge_output_format"], "mp4")
        self.assertEqual(params["ffmpeg_location"], "FAKE_FFMPEG")
        self.assertTrue(params["ignoreerrors"])
        self.assertFalse(params["noplaylist"])

    def test_custom_format(self):
        self._succeed_with_file()
        download_video(make_meta(), format_sel="worst")
        self.assertEqual(self.ydl_cls.call_args.args[0]["format"], "worst")

    def test_save_dir_used_in_outtmpl(self):
        self._succeed_with_file()
        download_video(make_meta(), save_dir="下载目录")
        params = self.ydl_cls.call_args.args[0]
        self.assertEqual(params["outtmpl"], os.path.join("下载目录", "%(title)s [%(id)s].%(ext)s"))

    def test_all_failed_uses_logger_summary(self):
        def side_effect(urls):
            self.ydl_cls.call_args.args[0]["logger"].error("ERROR: Video unavailable")
            return 1
        self.ydl.download.side_effect = side_effect
        with self.assertRaises(UniDownloadError) as ctx:
            download_video(make_meta())
        self.assertIn("页面找不到视频", str(ctx.exception))

    def test_ytdlp_download_error_becomes_chinese(self):
        self.ydl.download.side_effect = yt_dlp.utils.DownloadError("ERROR: ffmpeg not installed")
        with self.assertRaises(UniDownloadError) as ctx:
            download_video(make_meta())
        self.assertIn("合并/后处理失败", str(ctx.exception))


class DownloadVideoProgressCancelTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("uni_dl.yt_dlp.YoutubeDL")
        self.ydl_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.ffmpeg_patcher = mock.patch("uni_dl.get_ffmpeg_exe", return_value="FAKE_FFMPEG")
        self.ffmpeg_patcher.start()
        self.addCleanup(self.ffmpeg_patcher.stop)
        self.ydl = self.ydl_cls.return_value

    def test_progress_stages(self):
        calls = []

        def side_effect(urls):
            params = self.ydl_cls.call_args.args[0]
            params["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10})
            params["postprocessor_hooks"][0]({"status": "started", "postprocessor": "Merger"})
            params["post_hooks"][0]("out.mp4")
            return 0
        self.ydl.download.side_effect = side_effect
        result = download_video(make_meta(), progress=lambda stage, a, b: calls.append((stage, a, b)))
        self.assertEqual(result, [os.path.abspath("out.mp4")])
        self.assertEqual(calls, [("video", 5, 10), ("merging", 0, 0), ("done", 0, 0)])

    def test_cancel_propagates_from_progress_hook(self):
        def side_effect(urls):
            params = self.ydl_cls.call_args.args[0]
            params["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 100})
            return 0
        self.ydl.download.side_effect = side_effect
        with self.assertRaises(UniCancelledError):
            download_video(make_meta(), cancel=lambda: True)

    def test_cancel_after_download_raises(self):
        self.ydl.download.side_effect = lambda urls: self.ydl_cls.call_args.args[0]["post_hooks"][0]("out.mp4")
        with self.assertRaises(UniCancelledError):
            download_video(make_meta(), cancel=lambda: True)

    def test_invalid_meta_url_raises_input_error(self):
        for bad_meta in (None, make_meta(url=""), make_meta(url="not-a-url")):
            with self.subTest(meta=bad_meta):
                with self.assertRaises(UniInputError):
                    download_video(bad_meta)


class NetworkResilienceParamsTest(unittest.TestCase):
    def test_retry_and_chunk_params(self):
        with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls, mock.patch("uni_dl.get_ffmpeg_exe", return_value="FF"):
            def side_effect(urls):
                ydl_cls.call_args.args[0]["post_hooks"][0]("out.mp4")
                return 0
            ydl_cls.return_value.download.side_effect = side_effect
            download_video(make_meta())
            params = ydl_cls.call_args.args[0]
        self.assertEqual(params["http_chunk_size"], 10 * 1024 * 1024)
        self.assertEqual(params["retries"], 10)
        self.assertTrue(params["continuedl"])
        self.assertEqual(params["socket_timeout"], 30)


class ErrorMessageMappingTest(unittest.TestCase):
    def _fail_with(self, detail):
        with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls, mock.patch("uni_dl.get_ffmpeg_exe", return_value="FF"):
            def side_effect(urls):
                ydl_cls.call_args.args[0]["logger"].error(detail)
                return 1
            ydl_cls.return_value.download.side_effect = side_effect
            with self.assertRaises(UniDownloadError) as ctx:
                download_video(make_meta())
        return str(ctx.exception)

    def test_http_403_message(self):
        self.assertIn("站点拒绝访问", self._fail_with("ERROR: HTTP Error 403: Forbidden"))

    def test_http_404_message(self):
        self.assertIn("视频不存在", self._fail_with("ERROR: HTTP Error 404: Not Found"))

    def test_incomplete_read_message(self):
        self.assertIn("连接被站点中途断开", self._fail_with("ERROR: IncompleteRead(137182884 bytes read)"))

    def test_unknown_fallback_message(self):
        self.assertIn("未获取到任何文件", self._fail_with("ERROR: something odd happened"))


if __name__ == "__main__":
    unittest.main()
