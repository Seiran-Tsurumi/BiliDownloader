"""yhdmtv.cc 站点预解析离线测试。"""

import base64
import unittest
from unittest import mock
from urllib.parse import quote

import requests

import uni_dl
from uni_dl import UniDownloadError, _decode_yhdmtv_file, _extract_yhdmtv_media, _resolve_yhdmtv

_ORIGINAL_CURL_CFFI = uni_dl._curl_cffi_requests


def setUpModule():
    uni_dl._curl_cffi_requests = None


def tearDownModule():
    uni_dl._curl_cffi_requests = _ORIGINAL_CURL_CFFI


MEDIA = "https://v.lzcdn31.com/20260911/11224_7b7af541/index.m3u8"
PREFIX = "Etf"


def _file_field(media):
    payload = base64.b64encode(quote(media, safe="").encode("utf-8")).decode("ascii")
    return PREFIX + payload


def _page_html(include_entry=True, include_iframe=True, episode_name="第01集", drama="狐妖小红娘黄风岭篇"):
    parts = ["<html><head><title>正在播放《" + drama + "》-高清" + episode_name + "在线观看</title></head><body>"]
    parts.append("<script>var curPlaylineId = \"22254091\";</script>")
    if include_entry:
        parts.append("<script>var eps = [{\"currency\":0,\"file\":\"" + _file_field(MEDIA) + "\",\"id\":22254091,\"name\":\"" + episode_name + "\",\"sort\":0}];</script>")
    if include_iframe:
        parts.append("<div><iframe height=100% src='https://dxfbk.com/?url=" + MEDIA + "'></iframe></div>")
    if not include_entry:
        parts.append("<script>var Iyplayer = {id:22254091, name:'" + episode_name + "', file:''};</script>")
    parts.append("</body></html>")
    return "".join(parts)


class YhdmtvResolveTest(unittest.TestCase):
    def test_resolve_media_and_title(self):
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = _page_html()
            result = _resolve_yhdmtv("https://www.yhdmtv.cc/p/1033515/1/22254091")
        self.assertEqual(result["media_url"], MEDIA)
        self.assertEqual(result["title"], "狐妖小红娘黄风岭篇 第01集")
        self.assertEqual(result["extractor"], "yhdmtv")

    def test_picks_current_episode_not_first(self):
        second = "https://v.lzcdn31.com/20260911/11223_f788152f/index.m3u8"
        html = _page_html()
        html = html.replace("<script>var eps = [", "<script>var eps = [{\"currency\":0,\"file\":\"" + _file_field(second) + "\",\"id\":22254087,\"name\":\"第02集\"},")
        media, episode = _extract_yhdmtv_media(html)
        self.assertEqual(media, MEDIA)
        self.assertEqual(episode, "第01集")

    def test_fallback_to_iframe_when_no_id_entry(self):
        media, episode = _extract_yhdmtv_media(_page_html(include_entry=False))
        self.assertEqual(media, MEDIA)
        self.assertEqual(episode, "第01集")

    def test_decode_file(self):
        self.assertEqual(_decode_yhdmtv_file(_file_field(MEDIA)), MEDIA)

    def test_request_error_becomes_chinese(self):
        with mock.patch("uni_dl.requests.get", side_effect=requests.RequestException("boom")):
            with self.assertRaises(UniDownloadError) as ctx:
                _resolve_yhdmtv("https://www.yhdmtv.cc/p/1/1/1")
        self.assertIn("无法访问站点页面", str(ctx.exception))

    def test_http_error_becomes_chinese(self):
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 404
            get.return_value.text = ""
            with self.assertRaises(UniDownloadError) as ctx:
                _resolve_yhdmtv("https://www.yhdmtv.cc/p/1/1/1")
        self.assertIn("站点页面请求失败", str(ctx.exception))

    def test_no_media_raises(self):
        with mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = "<html><body>no player</body></html>"
            with self.assertRaises(UniDownloadError) as ctx:
                _resolve_yhdmtv("https://www.yhdmtv.cc/p/1/1/1")
        self.assertIn("未在该页面找到视频源", str(ctx.exception))


class ParseInputResolverTest(unittest.TestCase):
    def test_parse_uses_resolved_media_url(self):
        with mock.patch("uni_dl.yt_dlp.YoutubeDL") as ydl_cls, mock.patch("uni_dl.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.text = _page_html()
            ydl_cls.return_value.extract_info.return_value = {"id": "x", "title": "index", "duration": 60, "extractor_key": "generic"}
            meta = uni_dl.parse_input("https://www.yhdmtv.cc/p/1033515/1/22254091")
        self.assertEqual(meta.url, MEDIA)
        self.assertEqual(meta.title, "狐妖小红娘黄风岭篇 第01集")
        self.assertEqual(meta.webpage_url, "https://www.yhdmtv.cc/p/1033515/1/22254091")
        self.assertEqual(meta.extractor, "yhdmtv")
        ydl_cls.return_value.extract_info.assert_called_once_with(MEDIA, download=False, process=True)


if __name__ == "__main__":
    unittest.main()