"""page_dl.download 离线单测：mock requests，全部在临时目录内完成，不联网。"""

import os
import tempfile
import unittest
import zipfile
from unittest import mock

import requests

import page_dl
from page_dl import (
    MediaItem,
    PageBundle,
    PageCancelledError,
    PageDLError,
    PageDownloadError,
    PageInputError,
    download_page,
)
from page_dl import download as download_mod
from page_dl.tests.fakes import FakeResponse

PAGE_URL = "https://example.com/page/index.html"


def make_bundle(items=None, url=PAGE_URL, title="测试页面"):
    return PageBundle(
        url=url,
        title=title,
        items=list(items or []),
        image_count=0,
        video_count=0,
        audio_count=0,
        other_count=0,
        skipped=0,
    )


class DownloadBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.save_dir = self._tmp.name

    def mock_media(self, data_by_url=None, default=b"DATA", fail=()):
        calls = []
        failures = set(fail)

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            if url in failures:
                raise requests.ConnectionError("连接失败")
            return FakeResponse((data_by_url or {}).get(url, default))

        patcher = mock.patch.object(download_mod.requests, "get", side_effect=fake_get)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def leftover_tmp(self):
        return [name for name in os.listdir(self.save_dir) if name.startswith(".pack_tmp_")]

    def zips(self):
        return [name for name in os.listdir(self.save_dir) if name.endswith(".zip")]


class ZipPackTest(DownloadBase):
    def items(self):
        return [
            MediaItem("https://example.com/img/a.jpg", "image", "a.jpg"),
            MediaItem("https://example.com/v/b.mp4", "video", "b.mp4"),
            MediaItem("https://example.com/au/c.mp3", "audio", "c.mp3"),
            MediaItem("https://example.com/f/d.bin", "other", "d.bin"),
        ]

    def test_zip_structure_manifest_and_progress(self):
        self.mock_media()
        events = []
        path = download_page(
            make_bundle(self.items()), save_dir=self.save_dir, progress=lambda *args: events.append(args)
        )

        self.assertTrue(os.path.isabs(path))
        self.assertEqual(os.path.basename(path), "测试页面 [example.com].zip")
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            manifest = archive.read("清单.txt").decode("utf-8").strip().splitlines()

        for expected in ("图片/a.jpg", "视频/b.mp4", "音频/c.mp3", "其他/d.bin", "清单.txt"):
            self.assertIn(expected, names)
        for name in names:
            self.assertNotIn(chr(92), name)

        self.assertEqual(len(manifest), 4)
        self.assertEqual(manifest[0], "图片\t成功\thttps://example.com/img/a.jpg\ta.jpg")
        self.assertEqual(manifest[2], "音频\t成功\thttps://example.com/au/c.mp3\tc.mp3")

        stages = [event[0] for event in events]
        self.assertTrue(set(stages) <= {"download", "packing", "done"})
        self.assertEqual(stages[-2:], ["packing", "done"])
        packing = [event for event in events if event[0] == "packing"][0]
        self.assertEqual(packing[1:], (0, 0))
        last = events[-1]
        self.assertEqual(last[1], last[2])
        self.assertEqual(last[1], os.path.getsize(path))
        self.assertEqual(self.leftover_tmp(), [])

    def test_duplicate_names_get_index_suffix(self):
        items = [
            MediaItem("https://example.com/1/a.jpg", "image", "a.jpg"),
            MediaItem("https://example.com/2/a.jpg", "image", "a.jpg"),
            MediaItem("https://example.com/3/a.jpg", "image", "a.jpg"),
        ]
        self.mock_media()
        path = download_page(make_bundle(items), save_dir=self.save_dir)
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name != "清单.txt"]
        self.assertEqual(names, ["图片/a.jpg", "图片/a (1).jpg", "图片/a (2).jpg"])

    def test_zip_name_conflict_gets_suffix(self):
        self.mock_media()
        items = [MediaItem("https://example.com/img/a.jpg", "image", "a.jpg")]
        first = download_page(make_bundle(items), save_dir=self.save_dir)
        second = download_page(make_bundle(items), save_dir=self.save_dir)
        self.assertEqual(os.path.basename(first), "测试页面 [example.com].zip")
        self.assertEqual(os.path.basename(second), "测试页面 [example.com] (1).zip")
        self.assertEqual(len(self.zips()), 2)

    def test_partial_failure_keeps_successes(self):
        good = "https://example.com/img/a.jpg"
        bad = "https://example.com/img/b.jpg"
        self.mock_media(fail=[bad])
        path = download_page(
            make_bundle(
                [
                    MediaItem(good, "image", "a.jpg"),
                    MediaItem(bad, "image", "b.jpg"),
                ]
            ),
            save_dir=self.save_dir,
        )
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            manifest = archive.read("清单.txt").decode("utf-8")
        self.assertIn("图片/a.jpg", names)
        self.assertNotIn("图片/b.jpg", names)
        self.assertIn("失败", manifest)
        self.assertIn(bad, manifest)
        self.assertEqual(self.leftover_tmp(), [])

    def test_sanitizes_and_truncates_filename(self):
        long_name = "长" * 200 + ".jpg"
        self.mock_media()
        path = download_page(
            make_bundle(
                [
                    MediaItem("https://example.com/1.jpg", "image", 'a<b>c:d"e.jpg'),
                    MediaItem("https://example.com/2.jpg", "image", long_name),
                    MediaItem("https://example.com/i/none", "image", ""),
                ]
            ),
            save_dir=self.save_dir,
        )
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name != "清单.txt"]
        self.assertEqual(names[0], "图片/a_b_c_d_e.jpg")
        stem = names[1].split("/", 1)[1]
        self.assertLessEqual(len(stem), 120)
        self.assertTrue(stem.endswith(".jpg"))
        self.assertEqual(names[2], "图片/3")

    def test_referer_header_defaults_to_page_url(self):
        calls = self.mock_media()
        download_page(
            make_bundle(
                [
                    MediaItem("https://example.com/a.jpg", "image", "a.jpg"),
                    MediaItem("https://example.com/b.jpg", "image", "b.jpg", referer="https://example.com/other"),
                ]
            ),
            save_dir=self.save_dir,
        )
        headers_by_url = {url: kwargs["headers"] for url, kwargs in calls}
        self.assertEqual(headers_by_url["https://example.com/a.jpg"]["Referer"], PAGE_URL)
        self.assertEqual(headers_by_url["https://example.com/b.jpg"]["Referer"], "https://example.com/other")
        self.assertTrue(all("stream" in kwargs for _url, kwargs in calls))

    def test_proxy_passthrough(self):
        proxy = "http://127.0.0.1:7890"
        calls = self.mock_media()
        download_page(
            make_bundle([MediaItem("https://example.com/a.jpg", "image", "a.jpg")]),
            save_dir=self.save_dir,
            proxy=proxy,
        )
        self.assertEqual(calls[0][1]["proxies"], {"http": proxy, "https": proxy})


class FailureTest(DownloadBase):
    def test_all_failed_raises_chinese_error(self):
        self.mock_media(fail=["https://example.com/a.jpg", "https://example.com/b.jpg"])
        with self.assertRaises(PageDownloadError) as ctx:
            download_page(
                make_bundle(
                    [
                        MediaItem("https://example.com/a.jpg", "image", "a.jpg"),
                        MediaItem("https://example.com/b.jpg", "image", "b.jpg"),
                    ]
                ),
                save_dir=self.save_dir,
            )
        self.assertEqual(str(ctx.exception), "未下载到任何媒体文件")
        self.assertEqual(self.zips(), [])
        self.assertEqual(self.leftover_tmp(), [])

    def test_empty_bundle_raises(self):
        with self.assertRaises(PageDownloadError) as ctx:
            download_page(make_bundle([]), save_dir=self.save_dir)
        self.assertEqual(str(ctx.exception), "未下载到任何媒体文件")
        self.assertEqual(self.leftover_tmp(), [])

    def test_invalid_bundle(self):
        with self.assertRaises(PageInputError):
            download_page("not-a-bundle", save_dir=self.save_dir)
        with self.assertRaises(PageInputError):
            download_page(make_bundle([]), save_dir=self.save_dir, proxy=123)

    def test_cancel_cleans_tmp_and_partial_zip(self):
        items = [MediaItem("https://example.com/{0}.jpg".format(i), "image", "{0}.jpg".format(i)) for i in range(6)]
        self.mock_media()
        state = {"calls": 0}

        def cancel():
            state["calls"] += 1
            return state["calls"] > 1

        with self.assertRaises(PageCancelledError):
            download_page(make_bundle(items), save_dir=self.save_dir, cancel=cancel)
        self.assertEqual(self.leftover_tmp(), [])
        self.assertEqual(self.zips(), [])
        self.assertTrue(issubclass(PageCancelledError, PageDLError))

    def test_cancel_before_start(self):
        self.mock_media()
        with self.assertRaises(PageCancelledError):
            download_page(
                make_bundle([MediaItem("https://example.com/a.jpg", "image", "a.jpg")]),
                save_dir=self.save_dir,
                cancel=lambda: True,
            )
        self.assertEqual(os.listdir(self.save_dir), [])


class DirOutputTest(DownloadBase):
    def test_directory_output(self):
        self.mock_media()
        events = []
        target = download_page(
            make_bundle(
                [
                    MediaItem("https://example.com/img/a.jpg", "image", "a.jpg"),
                    MediaItem("https://example.com/v/b.mp4", "video", "b.mp4"),
                ]
            ),
            save_dir=self.save_dir,
            zip_output=False,
            progress=lambda *args: events.append(args),
        )
        self.assertTrue(os.path.isdir(target))
        self.assertTrue(os.path.isfile(os.path.join(target, "图片", "a.jpg")))
        self.assertTrue(os.path.isfile(os.path.join(target, "视频", "b.mp4")))
        self.assertTrue(os.path.isfile(os.path.join(target, "清单.txt")))
        self.assertEqual(os.path.dirname(target), os.path.abspath(self.save_dir))
        self.assertEqual(self.leftover_tmp(), [])
        self.assertEqual(self.zips(), [])
        self.assertEqual(events[-1][0], "done")


if __name__ == "__main__":
    unittest.main()
