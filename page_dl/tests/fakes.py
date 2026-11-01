"""page_dl 单测用的假响应对象（不联网）。"""

import requests


class FakeResponse:
    """最小可用的 requests.Response 替身：content/text/headers/iter_content。"""

    def __init__(self, content=b"", status_code=200, headers=None, encoding="utf-8"):
        self.content = content.encode(encoding) if isinstance(content, str) else bytes(content)
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.headers.setdefault("Content-Length", str(len(self.content)))
        self.encoding = encoding
        self.apparent_encoding = encoding

    @property
    def text(self):
        return self.content.decode(self.encoding, errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("HTTP " + str(self.status_code))

    def iter_content(self, chunk_size=1024):
        step = max(int(chunk_size or 1024), 1)
        for start in range(0, len(self.content), step):
            yield self.content[start:start + step]

    def close(self):
        pass
