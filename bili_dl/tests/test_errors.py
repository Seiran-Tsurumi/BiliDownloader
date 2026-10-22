import unittest

import bili_dl


class ErrorsExportTest(unittest.TestCase):
    def test_errors_exported_and_subclass_exception(self):
        for name in ("InputError", "ApiError", "DownloadError", "CancelledError"):
            cls = getattr(bili_dl, name)
            self.assertTrue(issubclass(cls, Exception), name)
            self.assertTrue(issubclass(cls, bili_dl.BiliDLError), name)

    def test_public_api_names(self):
        for name in ("parse_input", "list_qualities", "download_video", "VideoMeta", "Quality"):
            self.assertTrue(hasattr(bili_dl, name), name)

    def test_chinese_messages(self):
        err = bili_dl.InputError("输入无效")
        self.assertEqual(str(err), "输入无效")
