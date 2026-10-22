import functools
import http.server
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from imageio_ffmpeg import get_ffmpeg_exe

import bili_dl.download as download_mod
from bili_dl import ApiError, CancelledError, DownloadError, InputError, VideoMeta

FFMPEG = get_ffmpeg_exe()
META = VideoMeta(
    bvid="BV1GJ411x7h7", aid=170001, cid=1,
    title='测:试*标?题"<>|', owner_name="示例UP主", duration=2,
)


def make_fixtures(directory):
    video = directory / "v.m4s"
    audio = directory / "a.m4s"
    flv = directory / "v.flv"
    bad = directory / "bad.m4s"
    big = directory / "big.bin"
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=128x96:rate=10",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", "-f", "mp4", str(video)],
        check=True, capture_output=True,
    )
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:a", "aac", "-b:a", "64k", "-vn", "-f", "mp4", str(audio)],
        check=True, capture_output=True,
    )
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=128x96:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
         "-f", "flv", str(flv)],
        check=True, capture_output=True,
    )
    bad.write_bytes(b"this is not a video file at all" * 64)
    big.write_bytes(os.urandom(2 * 1024 * 1024))
    return video, audio, flv, bad, big


class _QuietServer(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass


def start_server(directory):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = _QuietServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def dash_payload(base, video_ids, audio_id=30280):
    return {
        "quality": 0,
        "accept_quality": [127, 120, 116, 112, 80, 74, 64, 32, 16],
        "accept_description": [],
        "dash": {
            "video": [
                {"id": q, "baseUrl": f"{base}/v.m4s", "codecid": 7, "codecs": "avc1.64001f"}
                for q in video_ids
            ],
            "audio": [{"id": audio_id, "baseUrl": f"{base}/a.m4s", "codecs": "mp4a.40.2"}],
        },
        "durl": None,
    }


class DownloadLocalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = Path(tempfile.mkdtemp(prefix="bili_dl_fix_"))
        cls.video_file, cls.audio_file, cls.flv_file, cls.bad_file, cls.big_file = make_fixtures(cls.fixture_dir)
        cls.server = start_server(cls.fixture_dir)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.fixture_dir, ignore_errors=True)

    def setUp(self):
        self.save_dir = Path(tempfile.mkdtemp(prefix="bili_dl_out_"))
        self.addCleanup(shutil.rmtree, self.save_dir, True)

    def collect(self):
        stages = []

        def progress(stage, downloaded, total):
            stages.append((stage, downloaded, total))

        return stages, progress

    def ordered_stages(self, stages):
        order, seen = [], set()
        for stage, _, _ in stages:
            if stage not in seen:
                seen.add(stage)
                order.append(stage)
        return order

    def assert_empty(self):
        self.assertEqual(list(self.save_dir.iterdir()), [])

    def assert_only(self, name):
        self.assertEqual(sorted(p.name for p in self.save_dir.iterdir()), [name])

    def assert_two_streams(self, path):
        proc = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True)
        err = proc.stderr.decode("utf-8", errors="replace")
        self.assertIn("Input #0, mov,mp4", err)
        self.assertIn("Stream #0:0", err)
        self.assertIn("Stream #0:1", err)
        self.assertIn("Video:", err)
        self.assertIn("Audio:", err)
        match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
        self.assertIsNotNone(match, err)
        seconds = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
        self.assertGreater(seconds, 0)

    def test_dash_download_merge_progress_and_naming(self):
        stages, progress = self.collect()
        payload = dash_payload(self.base, video_ids=[80, 64, 32, 16])
        nested = self.save_dir / "x" / "y"
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            out = download_mod.download_video(META, quality=80, save_dir=nested, progress=progress)
        self.assertTrue(out.is_file())
        size = out.stat().st_size
        self.assertGreater(size, 0)
        self.assertEqual(out.parent.resolve(), nested.resolve())
        self.assertEqual(self.ordered_stages(stages), ["fetching", "video", "audio", "merging", "done"])
        self.assertEqual(stages[-1], ("done", size, size))
        expected_stem = f"{download_mod._clean_title(META.title)} {META.bvid}"
        self.assertEqual(out.name, expected_stem + ".mp4")
        self.assertEqual(sorted(p.name for p in nested.iterdir()), [out.name])
        self.assert_two_streams(out)

    def test_max_quality_picks_highest_available_dash(self):
        payload = dash_payload(self.base, video_ids=[80, 64])
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload) as fetch:
            out = download_mod.download_video(META, quality="max", save_dir=self.save_dir)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[1], 127)
        self.assertTrue(out.is_file())
        self.assert_only(out.name)

    def test_unavailable_qn_raises_chinese_api_error(self):
        payload = dash_payload(self.base, video_ids=[64, 32])
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            with self.assertRaises(ApiError) as ctx:
                download_mod.download_video(META, quality=80, save_dir=self.save_dir)
            self.assertIn("画质不可用", str(ctx.exception))
        self.assert_empty()

    def test_invalid_quality_arg(self):
        with mock.patch("bili_dl.download.fetch_playurl") as fetch:
            for bad in ("abc", "", 0, -1, 1.5, True):
                with self.subTest(bad=bad):
                    with self.assertRaises(InputError):
                        download_mod.download_video(META, quality=bad, save_dir=self.save_dir)
        fetch.assert_not_called()

    def test_durl_fallback_when_no_dash(self):
        payload = {
            "quality": 64,
            "accept_quality": [64, 32, 16],
            "accept_description": [],
            "dash": None,
            "durl": [{"url": f"{self.base}/v.flv", "size": self.flv_file.stat().st_size}],
        }
        stages, progress = self.collect()
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            out = download_mod.download_video(META, quality=64, save_dir=self.save_dir, progress=progress)
        self.assertEqual(self.ordered_stages(stages), ["fetching", "video", "audio", "merging", "done"])
        self.assertEqual(stages[-1], ("done", out.stat().st_size, out.stat().st_size))
        self.assert_two_streams(out)
        self.assert_only(out.name)

    def test_durl_probe_when_advertised_quality_higher_than_dash(self):
        first = dash_payload(self.base, video_ids=[32])
        first["quality"] = 64
        second = {
            "quality": 64,
            "dash": None,
            "durl": [{"url": f"{self.base}/v.flv", "size": self.flv_file.stat().st_size}],
        }

        def fake_fetch(meta, qn, cookie=None, fnval="4048"):
            return first if fnval == "4048" else second

        stages, progress = self.collect()
        with mock.patch("bili_dl.download.fetch_playurl", side_effect=fake_fetch) as fetch:
            out = download_mod.download_video(META, quality="max", save_dir=self.save_dir, progress=progress)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(self.ordered_stages(stages), ["fetching", "video", "audio", "merging", "done"])
        self.assertEqual(stages[-1], ("done", out.stat().st_size, out.stat().st_size))
        self.assert_two_streams(out)
        self.assert_only(out.name)

    def test_durl_preferred_when_higher_than_dash_without_cookie(self):
        payload = dash_payload(self.base, video_ids=[32])
        payload["quality"] = 64
        payload["durl"] = [{"url": f"{self.base}/v.flv", "size": self.flv_file.stat().st_size}]
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            out = download_mod.download_video(META, quality="max", save_dir=self.save_dir)
        self.assert_two_streams(out)
        self.assert_only(out.name)

    def test_dash_preferred_over_durl_with_cookie(self):
        payload = dash_payload(self.base, video_ids=[32])
        payload["quality"] = 64
        payload["durl"] = [{"url": f"{self.base}/v.flv", "size": self.flv_file.stat().st_size}]
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            out = download_mod.download_video(
                META, quality="max", cookie="SESSDATA=" + "a" * 40, save_dir=self.save_dir
            )
        self.assert_two_streams(out)
        self.assert_only(out.name)

    def test_duplicate_name_gets_numbered(self):
        payload = dash_payload(self.base, video_ids=[80])
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            first = download_mod.download_video(META, quality=80, save_dir=self.save_dir)
            second = download_mod.download_video(META, quality=80, save_dir=self.save_dir)
        stem = f"{download_mod._clean_title(META.title)} {META.bvid}"
        self.assertEqual(first.name, stem + ".mp4")
        self.assertEqual(second.name, stem + " (1).mp4")
        self.assertEqual(len(list(self.save_dir.iterdir())), 2)

    def test_bad_cookie_raises_before_any_request(self):
        with mock.patch("bili_dl.download.fetch_playurl") as fetch:
            with self.assertRaises(ApiError) as ctx:
                download_mod.download_video(META, cookie="SESSDATA=bad", save_dir=self.save_dir)
            self.assertIn("Cookie 无效", str(ctx.exception))
        fetch.assert_not_called()
        self.assert_empty()

    def test_merge_failure_raises_download_error_and_cleans(self):
        payload = {
            "quality": 0,
            "accept_quality": [80],
            "accept_description": [],
            "dash": {
                "video": [{"id": 80, "baseUrl": f"{self.base}/bad.m4s", "codecid": 7}],
                "audio": [{"id": 30280, "baseUrl": f"{self.base}/a.m4s", "codecs": "mp4a.40.2"}],
            },
            "durl": None,
        }
        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            with self.assertRaises(DownloadError) as ctx:
                download_mod.download_video(META, quality=80, save_dir=self.save_dir)
            self.assertIn("合并失败", str(ctx.exception))
        self.assert_empty()

    def test_cancel_mid_download_cleans_up(self):
        payload = dash_payload(self.base, video_ids=[80])
        payload["dash"]["video"][0]["baseUrl"] = f"{self.base}/big.bin"
        state = {"video_bytes": 0}

        def progress(stage, downloaded, total):
            if stage == "video":
                state["video_bytes"] = downloaded

        def cancel():
            return state["video_bytes"] > 200_000

        with mock.patch("bili_dl.download.fetch_playurl", return_value=payload):
            with self.assertRaises(CancelledError):
                download_mod.download_video(META, quality=80, save_dir=self.save_dir, progress=progress, cancel=cancel)
        self.assert_empty()
