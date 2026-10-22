"""真实网络集成测试：真实 BV 解析、真实画质列表、真实下载与取消。"""
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe

from bili_dl import ApiError, CancelledError, download_video, list_qualities, parse_input

FFMPEG = get_ffmpeg_exe()
BV = "BV1GJ411x7h7"  # 公开视频：Rick Astley - Never Gonna Give You Up


class LiveParseTest(unittest.TestCase):
    def test_parse_real_video(self):
        meta = parse_input(BV)
        self.assertEqual(meta.bvid, BV)
        self.assertGreater(meta.aid, 0)
        self.assertGreater(meta.cid, 0)
        self.assertTrue(meta.title)
        self.assertTrue(meta.owner_name)
        self.assertGreater(meta.duration, 0)
        print(
            f"[live-parse] bvid={meta.bvid} aid={meta.aid} cid={meta.cid} "
            f"title={meta.title!r} owner={meta.owner_name!r} duration={meta.duration}s"
        )


class LiveQualityTest(unittest.TestCase):
    def test_list_qualities_real(self):
        meta = parse_input(BV)
        qualities = list_qualities(meta)
        self.assertTrue(qualities)
        qns = [q.qn for q in qualities]
        self.assertEqual(qns, sorted(qns, reverse=True))
        print(f"[live-quality] 免登录可用画质: {[(q.qn, q.desc) for q in qualities]}")
        print(f"[live-quality] 免登录最高档: qn={qualities[0].qn} desc={qualities[0].desc}")


class LiveDownloadTest(unittest.TestCase):
    def test_full_download_no_login(self):
        meta = parse_input(BV)
        save_dir = Path(tempfile.mkdtemp(prefix="bili_dl_live_"))
        stages = []

        def progress(stage, downloaded, total):
            stages.append((stage, downloaded, total))

        try:
            started = time.time()
            out = download_video(meta, save_dir=str(save_dir), quality="max", progress=progress)
            elapsed = time.time() - started
            size = out.stat().st_size
            self.assertTrue(out.is_file())
            self.assertGreater(size, 0)
            self.assertEqual(out.parent.resolve(), save_dir.resolve())
            order, seen = [], set()
            for stage, _, _ in stages:
                if stage not in seen:
                    seen.add(stage)
                    order.append(stage)
            self.assertEqual(order, ["fetching", "video", "audio", "merging", "done"])
            self.assertEqual(stages[-1][1:], (size, size))
            leftovers = [p.name for p in save_dir.iterdir() if p != out]
            self.assertEqual(leftovers, [])
            err = subprocess.run(
                [FFMPEG, "-hide_banner", "-i", str(out)], capture_output=True
            ).stderr.decode("utf-8", errors="replace")
            self.assertIn("Input #0, mov,mp4", err)
            self.assertIn("Stream #0:0", err)
            self.assertIn("Stream #0:1", err)
            match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
            self.assertIsNotNone(match, err)
            seconds = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
            self.assertGreater(seconds, 0)
            print(f"[live-download] BV={BV} 耗时={elapsed:.1f}s 大小={size} bytes ({size / 1048576:.2f} MB) 文件={out}")
            print("[live-download] progress 样例:")
            for line in stages[:6] + stages[-4:]:
                print(f"    {line}")
            print("[live-download] ffmpeg -i 关键行:")
            for line in err.splitlines():
                stripped = line.strip()
                if (
                    line.startswith("Input #")
                    or "Duration:" in line
                    or stripped.startswith("Stream #")
                    or (stripped.startswith("Video:") or stripped.startswith("Audio:"))
                ):
                    print(f"    {line}")
        finally:
            shutil.rmtree(save_dir, ignore_errors=True)

    def test_cancel_mid_download_no_login(self):
        meta = parse_input(BV)
        save_dir = Path(tempfile.mkdtemp(prefix="bili_dl_live_cancel_"))
        state = {"video_bytes": 0}

        def progress(stage, downloaded, total):
            if stage == "video":
                state["video_bytes"] = downloaded

        def cancel():
            return state["video_bytes"] > 200_000

        try:
            with self.assertRaises(CancelledError):
                download_video(meta, save_dir=str(save_dir), quality="max", progress=progress, cancel=cancel)
            self.assertEqual(list(save_dir.iterdir()), [])
            print("[live-cancel] 取消路径验证通过：CancelledError 已抛出且保存目录无临时残留")
        finally:
            shutil.rmtree(save_dir, ignore_errors=True)

    def test_bad_cookie_no_crash(self):
        meta = parse_input(BV)
        with self.assertRaises(ApiError) as ctx:
            list_qualities(meta, cookie="SESSDATA=bad")
        print(f"[live-badcookie] list_qualities 抛出 ApiError: {ctx.exception}")
        with self.assertRaises(ApiError) as ctx2:
            download_video(meta, cookie="SESSDATA=bad", save_dir=".")
        print(f"[live-badcookie] download_video 抛出 ApiError: {ctx2.exception}")
