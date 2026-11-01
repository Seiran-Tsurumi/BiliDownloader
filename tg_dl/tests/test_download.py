"""download_channel_media 的离线测试：保存路径、重名、文件名清理、进度、跳过、取消、限流。"""

import os
import threading

import tg_dl
from tg_dl import TgAuthError, TgCancelledError, TgDownloadError, TgInputError
from tg_dl.tests.fakes import FakeClient, FakeEntity, FakeMessage, TgClientTestCase, fake_clock


class DownloadPathTest(TgClientTestCase):
    def test_files_land_in_kind_folders(self):
        root = self.temp_dir()
        FakeClient.messages = [
            FakeMessage(1, "photo", ext="jpg"),
            FakeMessage(2, "video", name="clip.mp4"),
            FakeMessage(3, "audio", name="song.mp3"),
            FakeMessage(4, "document", name="doc.pdf"),
            FakeMessage(5, "other"),
        ]
        saved = tg_dl.download_channel_media(self.session_config(), "@test_channel", root)

        channel = os.path.join(root, "测试频道")
        self.assertEqual(
            saved,
            [
                os.path.join(channel, "图片", "1.jpg"),
                os.path.join(channel, "视频", "clip.mp4"),
                os.path.join(channel, "音频", "song.mp3"),
                os.path.join(channel, "文件", "doc.pdf"),
            ],
        )
        for path in saved:
            self.assertTrue(os.path.isfile(path))
        self.assertEqual(len(self.client.downloads), 4)
        self.assertTrue(self.client.disconnected)

    def test_download_media_receives_path_and_callback(self):
        FakeClient.messages = [FakeMessage(1, "photo", name="a.jpg")]
        saved = tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        message_id, target = self.client.downloads[0]
        self.assertEqual(message_id, 1)
        self.assertEqual(target, saved[0])
        self.assertIsInstance(target, str)

    def test_duplicate_names_get_sequence_numbers(self):
        FakeClient.messages = [FakeMessage(index, "photo", name="same.jpg") for index in (1, 2, 3)]
        saved = tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        self.assertEqual([os.path.basename(path) for path in saved], ["same.jpg", "same_1.jpg", "same_2.jpg"])

    def test_illegal_characters_are_cleaned(self):
        FakeClient.messages = [FakeMessage(1, "document", name="a<b>:c?d*.zip")]
        saved = tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        self.assertEqual(os.path.basename(saved[0]), "a_b__c_d_.zip")

    def test_long_name_is_truncated_keeping_extension(self):
        FakeClient.messages = [FakeMessage(1, "video", name="长" * 200 + ".mp4")]
        saved = tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        name = os.path.basename(saved[0])
        self.assertEqual(len(name), 120)
        self.assertTrue(name.endswith(".mp4"))

    def test_blank_filename_falls_back_to_media(self):
        FakeClient.messages = [FakeMessage(1, "document", name="   ")]
        saved = tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        self.assertEqual(os.path.basename(saved[0]), "media")

    def test_nested_save_dir_is_created(self):
        root = os.path.join(self.temp_dir(), "a", "b", "c")
        FakeClient.messages = [FakeMessage(1, "photo", ext="jpg")]
        saved = tg_dl.download_channel_media(self.session_config(), "chan", root)
        self.assertTrue(os.path.isfile(saved[0]))

    def test_channel_title_is_sanitized_for_folder(self):
        FakeClient.entity = FakeEntity(title="a/b:c*?", username="u")
        FakeClient.messages = [FakeMessage(1, "photo", name="x.jpg")]
        root = self.temp_dir()
        saved = tg_dl.download_channel_media(self.session_config(), "chan", root)
        self.assertEqual(os.path.dirname(os.path.dirname(saved[0])), os.path.join(root, "a_b_c__"))

    def test_missing_title_falls_back(self):
        FakeClient.entity = FakeEntity(title="", username="")
        FakeClient.messages = [FakeMessage(1, "photo", name="x.jpg")]
        root = self.temp_dir()
        saved = tg_dl.download_channel_media(self.session_config(), "chan", root)
        self.assertEqual(os.path.dirname(os.path.dirname(saved[0])), os.path.join(root, "chan"))

    def test_returns_raw_result_when_file_not_written(self):
        FakeClient.write_files = False
        FakeClient.messages = [FakeMessage(1, "photo", name="a.jpg")]
        saved = tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0].endswith("a.jpg"))


class DownloadProgressTest(TgClientTestCase):
    def test_stage_sequence(self):
        events = []
        FakeClient.messages = [
            FakeMessage(1, "photo", name="a.jpg"),
            FakeMessage(2, "video", name="b.mp4"),
        ]
        saved = tg_dl.download_channel_media(
            self.session_config(), "chan", self.temp_dir(), progress=lambda *args: events.append(args)
        )
        self.assertEqual(len(saved), 2)
        stages = [event[0] for event in events]
        self.assertEqual(stages[0], "download")
        self.assertEqual(stages[-1], "done")
        self.assertNotIn("skip", stages)
        self.assertEqual(events[-1], ("done", 2, 2))
        self.assertIn(("download", 2, 2), events)
        self.assertTrue(all(event[2] == 2 for event in events))

    def test_progress_is_optional(self):
        FakeClient.messages = [FakeMessage(1, "photo", name="a.jpg")]
        self.assertEqual(
            len(tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())), 1
        )

    def test_skip_stage_on_single_file_failure(self):
        events = []
        FakeClient.fail_message_ids = (2,)
        FakeClient.messages = [
            FakeMessage(1, "photo", name="a.jpg"),
            FakeMessage(2, "photo", name="b.jpg"),
        ]
        saved = tg_dl.download_channel_media(
            self.session_config(), "chan", self.temp_dir(), progress=lambda *args: events.append(args)
        )
        self.assertEqual([os.path.basename(path) for path in saved], ["a.jpg"])
        self.assertIn(("skip", 1, 2), events)
        self.assertEqual(events[-1], ("done", 1, 1))

    def test_all_failures_raise(self):
        FakeClient.fail_message_ids = (1, 2)
        FakeClient.messages = [FakeMessage(1, "photo"), FakeMessage(2, "photo")]
        with self.assertRaises(TgDownloadError) as ctx:
            tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        self.assertEqual(str(ctx.exception), "未下载到任何媒体文件")
        self.assertTrue(self.client.disconnected)

    def test_no_matching_media_raises(self):
        FakeClient.messages = [FakeMessage(1, "other")]
        with self.assertRaises(TgDownloadError) as ctx:
            tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        self.assertEqual(str(ctx.exception), "未下载到任何媒体文件")


class DownloadCancelTest(TgClientTestCase):
    def test_cancel_keeps_finished_files(self):
        event = threading.Event()

        def progress(stage, current, total):
            if stage == "download" and current == 0:
                event.set()

        FakeClient.messages = [
            FakeMessage(1, "photo", name="a.jpg"),
            FakeMessage(2, "photo", name="b.jpg"),
        ]
        root = self.temp_dir()
        with self.assertRaises(TgCancelledError) as ctx:
            tg_dl.download_channel_media(
                self.session_config(), "chan", root, progress=progress, cancel=event
            )
        self.assertIn("取消", str(ctx.exception))
        self.assertTrue(os.path.isfile(os.path.join(root, "测试频道", "图片", "a.jpg")))
        self.assertEqual(len(self.client.downloads), 1)
        self.assertTrue(self.client.disconnected)

    def test_cancel_before_start_does_not_connect(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(TgCancelledError):
            tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir(), cancel=event)
        self.assertEqual(FakeClient.instances, [])


class DownloadFloodTest(TgClientTestCase):
    def test_flood_wait_retries_single_file(self):
        FakeClient.download_flood_seconds = 5
        FakeClient.messages = [FakeMessage(1, "photo", name="a.jpg")]
        with fake_clock():
            saved = tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        self.assertEqual(len(saved), 1)
        self.assertEqual(len(self.client.downloads), 2)

    def test_flood_wait_over_limit_raises_with_seconds(self):
        FakeClient.download_flood_seconds = 120
        FakeClient.messages = [FakeMessage(1, "photo", name="a.jpg")]
        with fake_clock():
            with self.assertRaises(TgDownloadError) as ctx:
                tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir())
        self.assertIn("120", str(ctx.exception))


class DownloadFilterTest(TgClientTestCase):
    def test_media_types_filter(self):
        FakeClient.messages = [
            FakeMessage(1, "photo", name="a.jpg"),
            FakeMessage(2, "video", name="b.mp4"),
        ]
        saved = tg_dl.download_channel_media(
            self.session_config(), "chan", self.temp_dir(), media_types={"video"}
        )
        self.assertEqual([os.path.basename(path) for path in saved], ["b.mp4"])

    def test_limit_restricts_downloads(self):
        FakeClient.messages = [FakeMessage(index, "photo", name=f"{index}.jpg") for index in (1, 2, 3)]
        saved = tg_dl.download_channel_media(self.session_config(), "chan", self.temp_dir(), limit=1)
        self.assertEqual([os.path.basename(path) for path in saved], ["1.jpg"])

    def test_unknown_media_type_rejected(self):
        with self.assertRaises(TgInputError):
            tg_dl.download_channel_media(
                self.session_config(), "chan", self.temp_dir(), media_types={"gif"}
            )

    def test_blank_save_dir_rejected(self):
        for bad in ("", "   ", None):
            with self.subTest(save_dir=bad):
                with self.assertRaises(TgInputError) as ctx:
                    tg_dl.download_channel_media(self.session_config(), "chan", bad)
                self.assertIn("保存目录", str(ctx.exception))


class DownloadAuthTest(TgClientTestCase):
    def test_unauthorized_creates_nothing(self):
        FakeClient.authorized = False
        root = self.temp_dir()
        with self.assertRaises(TgAuthError) as ctx:
            tg_dl.download_channel_media(self.session_config(), "chan", root)
        self.assertEqual(str(ctx.exception), "尚未登录或会话已失效")
        self.assertEqual(os.listdir(root), [])
        self.assertTrue(self.client.disconnected)
