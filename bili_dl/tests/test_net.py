import http.server
import json
import threading
import unittest
from unittest import mock

from bili_dl import ApiError
from bili_dl.net import http_get_json


class CounterHandler(http.server.BaseHTTPRequestHandler):
    calls = 0
    fail_times = 0
    payload = {"code": 0, "message": "0", "data": {}}

    def do_GET(self):
        type(self).calls += 1
        if type(self).fail_times > 0:
            type(self).fail_times -= 1
            self.send_response(500)
            self.end_headers()
            return
        body = json.dumps(type(self).payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class NetRetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CounterHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        CounterHandler.calls = 0
        CounterHandler.fail_times = 0

    def test_retries_twice_then_succeeds(self):
        CounterHandler.fail_times = 2
        with mock.patch("bili_dl.net.time.sleep"):
            result = http_get_json(self.base + "/x")
        self.assertEqual(result["code"], 0)
        self.assertEqual(CounterHandler.calls, 3)

    def test_http_412_raises_risk_control(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(412)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(ApiError) as ctx:
                http_get_json(f"http://127.0.0.1:{server.server_address[1]}/x")
            self.assertIn("风控", str(ctx.exception))
        finally:
            server.shutdown()
            server.server_close()

    def test_all_attempts_fail_raises_chinese_api_error(self):
        CounterHandler.fail_times = 99
        with mock.patch("bili_dl.net.time.sleep"):
            with self.assertRaises(ApiError) as ctx:
                http_get_json(self.base + "/x")
        self.assertIn("网络异常", str(ctx.exception))
        self.assertEqual(CounterHandler.calls, 3)
