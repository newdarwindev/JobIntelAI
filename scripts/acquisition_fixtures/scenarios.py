"""Only authored paths can select a scenario. No user-controlled destinations."""

import gzip
import zlib
from dataclasses import dataclass, field


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    headers: dict = field(default_factory=lambda: {"Content-Type": "text/html; charset=utf-8"})
    chunked: bool = False
    pause: float = 0


def redirect(path):
    fixed = {
        "/authored-job": "/authored-final",
        "/loop": "/loop",
        "/private-redirect": "http://127.0.0.1/private",
        "/rebind": "/authored-final",
        "/downgrade": "http://example.com/authored-final",
    }
    if path in fixed:
        return fixed[path]
    if path.startswith("/redirect/"):
        suffix = path.removeprefix("/redirect/")
        if suffix.isdigit() and 0 <= int(suffix) <= 4:
            return f"/redirect/{int(suffix) - 1}" if int(suffix) else "/authored-final"
    return None


def content_reply(path, source):
    html = (
        f"<nav>Authored navigation</nav><main>{source}</main><script>window.__fetched=true</script>"
    ).encode()
    variants = {
        "/authored-final": Reply(body=html),
        "/mutable": Reply(body=html),
        "/changed": Reply(body=b"<!-- Authored raw change -->" + html),
        "/text": Reply(body=source.encode(), headers={"Content-Type": "text/plain; charset=utf-8"}),
        "/gzip": Reply(
            body=gzip.compress(html),
            headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
        ),
        "/deflate": Reply(
            body=zlib.compress(html),
            headers={"Content-Type": "text/html", "Content-Encoding": "deflate"},
        ),
        "/chunked": Reply(body=html, chunked=True),
        "/slow": Reply(body=html, chunked=True, pause=0.2),
        "/oversized": Reply(body=b"x" * 200_001),
        "/oversized-chunked": Reply(body=b"x" * 200_001, chunked=True),
        "/gzip-bomb": Reply(
            body=gzip.compress(b"x" * 200_001),
            headers={"Content-Type": "text/plain", "Content-Encoding": "gzip"},
        ),
        "/captcha": Reply(body=b"<main>Verify you are human</main>"),
        "/authored-js": Reply(body=b'<div id="root"></div><script>renderPosting()</script>'),
        "/unsupported": Reply(
            body=b"Authored binary", headers={"Content-Type": "application/octet-stream"}
        ),
    }
    return variants.get(path)


def reply(path, count, source):
    target = redirect(path)
    if target is not None:
        return Reply(302, headers={"Location": target})
    content = content_reply(path, source)
    if content:
        if path == "/mutable" and count % 3 == 0:
            return content_reply("/changed", source)
        return content
    if path in {"/rate-limit", "/retry-success"}:
        if path == "/retry-success" and count % 3 == 0:
            return content_reply("/text", source)
        return Reply(429, headers={"Retry-After": "999"})
    if path in {"/server-error", "/server-success"}:
        if path == "/server-success" and count % 3 == 0:
            return content_reply("/text", source)
        return Reply(503)
    return Reply(403)
