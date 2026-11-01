"""page_dl 对外 API 契约单测：导出名、异常层级与函数签名。"""

import inspect
import unittest

import page_dl
from page_dl import (
    MediaItem,
    PageBundle,
    PageCancelledError,
    PageDLError,
    PageDownloadError,
    PageInputError,
    download_page,
    parse_page,
)


class ExportTest(unittest.TestCase):
    def test_all_exact(self):
        self.assertEqual(
            page_dl.__all__,
            [
                "parse_page",
                "download_page",
                "PageBundle",
                "MediaItem",
                "PageDLError",
                "PageInputError",
                "PageDownloadError",
                "PageCancelledError",
            ],
        )

    def test_all_names_importable(self):
        for name in page_dl.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(page_dl, name))

    def test_error_hierarchy(self):
        self.assertTrue(issubclass(PageDLError, Exception))
        for error in (PageInputError, PageDownloadError, PageCancelledError):
            self.assertTrue(issubclass(error, PageDLError))

    def test_dataclass_fields(self):
        self.assertEqual(
            [field for field in MediaItem.__dataclass_fields__], ["url", "kind", "filename", "referer"]
        )
        self.assertEqual(
            [field for field in PageBundle.__dataclass_fields__],
            ["url", "title", "items", "image_count", "video_count", "audio_count", "other_count", "skipped"],
        )
        item = MediaItem(url="u", kind="image", filename="f")
        self.assertEqual(item.referer, "")

    def test_signatures(self):
        parse_sig = inspect.signature(parse_page)
        self.assertEqual(list(parse_sig.parameters), ["url", "cookie", "proxy", "max_items"])
        self.assertEqual(parse_sig.parameters["cookie"].default, None)
        self.assertEqual(parse_sig.parameters["proxy"].default, None)
        self.assertEqual(parse_sig.parameters["max_items"].default, 500)

        download_sig = inspect.signature(download_page)
        self.assertEqual(
            list(download_sig.parameters),
            ["bundle", "save_dir", "zip_output", "progress", "cancel", "proxy", "cookie"],
        )
        self.assertEqual(download_sig.parameters["save_dir"].default, ".")
        self.assertEqual(download_sig.parameters["zip_output"].default, True)
        self.assertEqual(download_sig.parameters["progress"].default, None)
        self.assertEqual(download_sig.parameters["cancel"].default, None)
        self.assertEqual(download_sig.parameters["proxy"].default, None)
        self.assertEqual(download_sig.parameters["cookie"].default, None)


if __name__ == "__main__":
    unittest.main()
