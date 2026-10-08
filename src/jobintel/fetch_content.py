"""Bound wire/decompressed bytes, decode declared text, and refuse access gates."""

import email.message
import zlib
from hashlib import sha256

from bs4 import BeautifulSoup

from jobintel.fetch_types import FetchError
from jobintel.snapshots import clean_text

TEXT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
CHARSETS = {"utf-8", "utf-8-sig", "us-ascii", "ascii", "iso-8859-1", "latin-1", "windows-1252"}


def response_type(headers):
    header = email.message.Message()
    header["content-type"] = headers.get("content-type", "")
    content_type = header.get_content_type()
    if not headers.get("content-type") or content_type not in TEXT_TYPES:
        raise FetchError("unsupported_type", 415)
    charset = (header.get_content_charset() or "utf-8").lower()
    if charset not in CHARSETS:
        raise FetchError("invalid_text", 422)
    return content_type, charset


def decoder(headers):
    encoding = headers.get("content-encoding", "identity").strip().lower()
    if encoding == "identity":
        return None
    if encoding not in {"gzip", "deflate"}:
        raise FetchError("unsupported_encoding", 415)
    return zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)


def remaining_budget(deadline, clock):
    remaining = deadline - clock()
    if remaining <= 0:
        raise FetchError("deadline", 504, True)
    return remaining


def read_bytes(response, policy, deadline, clock):
    try:
        length = int(response.headers.get("content-length", "0"))
    except ValueError:
        raise FetchError("invalid_text", 422) from None
    if length < 0 or length > policy.max_bytes:
        raise FetchError("body_too_large", 413)
    inflate = decoder(response.headers)
    data, wire_size = bytearray(), 0
    try:
        while True:
            timeout = min(policy.read_timeout, remaining_budget(deadline, clock))
            chunk = response.read(min(8192, policy.max_bytes + 1), timeout)
            remaining_budget(deadline, clock)
            if not chunk:
                break
            wire_size += len(chunk)
            if wire_size > policy.max_bytes:
                raise FetchError("body_too_large", 413)
            data.extend(
                inflate.decompress(chunk, policy.max_bytes - len(data) + 1) if inflate else chunk
            )
            if len(data) > policy.max_bytes:
                raise FetchError("body_too_large", 413)
        validate_stream(inflate, response, wire_size, length)
    except zlib.error:
        raise FetchError("unsupported_encoding", 415) from None
    return bytes(data)


def validate_stream(inflate, response, wire_size, length):
    if "content-length" in response.headers and wire_size != length:
        raise FetchError("network_failure", 502, True)
    if inflate and (not inflate.eof or inflate.unused_data or inflate.unconsumed_tail):
        raise FetchError("unsupported_encoding", 415)


def usable_text(text, is_html):
    cleaned = clean_text(text, is_html)
    if is_html:
        soup = BeautifulSoup(text, "html.parser")
        title = soup.title.get_text().casefold() if soup.title else ""
        visible = cleaned.casefold()
        if (
            any(marker in title for marker in ["captcha", "access denied", "checking your browser"])
            or "verify you are human" in visible
        ):
            raise FetchError("captcha", 403)
        if soup.find("script") and visible in {
            "",
            "loading",
            "loading...",
            "loading…",
            "please wait",
        }:
            raise FetchError("js_only", 422)
        if (
            soup.find("noscript")
            and "enable javascript" in soup.get_text().casefold()
            and not soup.select_one("main, article")
        ):
            raise FetchError("js_only", 422)
    if not cleaned:
        raise FetchError("empty_source", 422)
    return cleaned


def read_posting(response, policy, deadline, clock):
    content_type, charset = response_type(response.headers)
    body = read_bytes(response, policy, deadline, clock)
    try:
        text = body.decode("utf-8" if charset == "utf-8-sig" else charset)
    except UnicodeError:
        raise FetchError("invalid_text", 422) from None
    if "\x00" in text:
        raise FetchError("invalid_text", 422)
    is_html = content_type != "text/plain"
    usable_text(text, is_html)
    return (
        text,
        is_html,
        {
            "content_type": content_type,
            "charset": charset,
            "decompressed_bytes": len(body),
            "body_sha256": sha256(body).hexdigest(),
        },
    )
