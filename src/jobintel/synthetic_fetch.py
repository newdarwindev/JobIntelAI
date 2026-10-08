"""Explicit demo-only HTTP fixtures; this transport never opens a network socket."""

import io

from jobintel.acquisition import HttpAcquirer


class SyntheticResolver:
    def resolve(self, *_):
        return ["93.184.216.34"]


class SyntheticResponse:
    def __init__(self, status, body=b"", headers=None):
        self.status = status
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.body = io.BytesIO(body)

    def read(self, size, timeout):
        return self.body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.body.close()


class SyntheticTransport:
    def __init__(self, root):
        self.source = (root / "sample_jobs/SYN-01.txt").read_text()

    def get(self, destination, *_):
        if destination.url == "https://example.com/authored-job":
            return SyntheticResponse(302, headers={"location": "/authored-final"})
        if destination.url == "https://example.com/authored-final":
            html = f"<nav>Authored navigation</nav><main>{self.source}</main><script>window.__fetched=true</script>"
            return SyntheticResponse(200, html.encode())
        if destination.url == "https://example.com/authored-js":
            return SyntheticResponse(200, b'<div id="root"></div><script>renderPosting()</script>')
        return SyntheticResponse(403)


def synthetic_acquirer(root):
    return HttpAcquirer(transport=SyntheticTransport(root), resolver=SyntheticResolver())
