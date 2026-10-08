"""V02-V11: offline destination rejection, bounded retry/redirect/content recovery."""

import gzip
import socket
import zlib
from datetime import UTC, datetime

import pytest

from jobintel.acquisition import retry_after
from jobintel.fetch_destinations import DNSResolver, public_address
from jobintel.fetch_types import FetchError, FetchPolicy
from tests.acquisition_fakes import PUBLIC, URL, Resolver, Response, acquirer

BLOCKED = [
    "127.0.0.1",
    "0.0.0.0",
    "10.1.2.3",
    "172.16.1.2",
    "192.168.1.1",
    "169.254.169.254",
    "169.254.1.2",
    "100.64.0.1",
    "192.0.2.1",
    "198.51.100.2",
    "203.0.113.2",
    "224.0.0.1",
    "240.1.2.3",
    "255.255.255.255",
    "::",
    "::1",
    "fc00::1",
    "fe80::1",
    "ff02::1",
    "2001:db8::1",
    "::ffff:127.0.0.1",
    "::ffff:93.184.216.34",
    "64:ff9b::7f00:1",
    "2002:7f00:1::",
    "fec0::1",
]


@pytest.mark.parametrize("address", BLOCKED)
def test_v02_v03_rejected_literals_and_mixed_dns_make_no_http_request(address):
    literal = f"[{address}]" if ":" in address else address
    fetcher, transport, _ = acquirer()
    result = fetcher.fetch(f"https://{literal}/authored")
    assert result.error.code == "blocked_destination" and transport.calls == []
    mixed = Resolver([[PUBLIC, address]])
    fetcher, transport, _ = acquirer(resolver=mixed)
    assert fetcher.fetch(URL).error.code == "blocked_destination"
    assert transport.calls == [] and len(mixed.calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "file:///authored",
        "ftp://example.com/authored",
        "https://user:secret@example.com/",
        "https://example.com:444/",
        "https://localhost/",
        "https://localhost./",
        "https://a.localhost/",
        "https://example.com/\r\nInjected",
        "https://example.com\\evil/",
    ],
)
def test_v02_invalid_credential_and_localhost_urls_never_reach_transport(url):
    fetcher, transport, _ = acquirer()
    result = fetcher.fetch(url)
    assert result.error.code in {"invalid_url", "blocked_destination"} and transport.calls == []


def test_v03_dns_rebinding_on_retry_is_rejected_before_second_request():
    resolver = Resolver([[PUBLIC], ["127.0.0.1"]])
    fetcher, transport, clock = acquirer(Response(503), resolver=resolver)
    result = fetcher.fetch(URL)
    assert result.error.code == "blocked_destination"
    assert len(transport.calls) == 1 and len(resolver.calls) == 2
    assert transport.calls[0][0].address == PUBLIC and clock.waits == [0.5]


def test_v03_resolver_timeout_and_dns_errors_are_bounded(monkeypatch):
    monkeypatch.setattr(
        "jobintel.fetch_destinations.socket.getaddrinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            socket.gaierror("authored private DNS text")
        ),
    )
    with pytest.raises(FetchError, match="could not be resolved"):
        DNSResolver().resolve("example.com", 443, 0.1)
    monkeypatch.setattr(
        "jobintel.fetch_destinations.queue.Queue.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(__import__("queue").Empty()),
    )
    with pytest.raises(FetchError) as error:
        DNSResolver().resolve("example.com", 443, 0.01)
    assert error.value.code == "dns_timeout"


def test_v04_three_redirects_succeed_and_fourth_or_loop_never_requested():
    redirects = [Response(302, headers={"location": f"/hop-{index}"}) for index in range(3)]
    fetcher, transport, _ = acquirer(*redirects, Response())
    result = fetcher.fetch(URL)
    assert result.error is None and len(transport.calls) == 4
    assert result.final_url == "https://example.com/hop-2"
    fetcher, transport, _ = acquirer(
        *[Response(302, headers={"location": f"/hop-{index}"}) for index in range(4)]
    )
    result = fetcher.fetch(URL)
    assert result.error.code == "redirect_limit" and len(transport.calls) == 4
    fetcher, transport, _ = acquirer(Response(302, headers={"location": URL}))
    assert fetcher.fetch(URL).error.code == "redirect_loop" and len(transport.calls) == 1


@pytest.mark.parametrize(
    "location,code",
    [
        ("http://example.com/down", "invalid_redirect"),
        ("https://127.0.0.1/private", "blocked_destination"),
        ("https://user:secret@example.com/", "invalid_url"),
        ("", "invalid_redirect"),
    ],
)
def test_v04_each_redirect_is_validated_without_forwarding_credentials(location, code):
    response = Response(302, headers={"location": location})
    fetcher, transport, _ = acquirer(response)
    assert fetcher.fetch(URL).error.code == code
    assert len(transport.calls) == 1 and response.closed


@pytest.mark.parametrize(
    "code", ["connect_timeout", "read_timeout", "dns_timeout", "network_failure"]
)
def test_v05_transient_errors_have_bounded_attempts_and_backoff(code):
    fetcher, transport, clock = acquirer(*[FetchError(code, 504, True) for _ in range(3)])
    result = fetcher.fetch(URL)
    assert result.error.code == code and len(transport.calls) == 3
    assert clock.waits == [0.5, 1] and len(result.events) == 3
    assert result.error.detail()["manual_fallback"] is True


@pytest.mark.parametrize(
    "status,code", [(429, "rate_limit"), (500, "server_error"), (503, "server_error")]
)
def test_v05_exhausted_http_retries_cap_retry_after(status, code):
    responses = [Response(status, headers={"retry-after": "999999"}) for _ in range(3)]
    fetcher, transport, clock = acquirer(*responses)
    result = fetcher.fetch(URL)
    assert result.error.code == code and result.error.retryable
    assert len(transport.calls) == 3 and clock.waits == [2, 2]
    assert all(response.closed for response in responses)


def test_v05_retry_recovery_and_global_deadline_preserve_diagnostics():
    fetcher, _, clock = acquirer(Response(429), Response())
    assert fetcher.fetch(URL).text == "Python is required." and clock.waits == [0.5]
    fetcher, transport, clock = acquirer(
        Response(429, headers={"retry-after": "999"}), policy=FetchPolicy(total_timeout=1)
    )
    result = fetcher.fetch(URL)
    assert result.error.code == "deadline" and len(transport.calls) == 1 and clock.waits == []
    fetcher, transport, clock = acquirer(Response())
    original_read = transport.responses[0].read

    def delayed_read(*args):
        clock.value += 21
        return original_read(*args)

    transport.responses[0].read = delayed_read
    assert fetcher.fetch(URL).error.code == "deadline"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("100000", 2),
        ("-1", 0),
        ("invalid", None),
        ("Thu, 08 Oct 2026 00:00:10 GMT", 2),
        ("Wed, 07 Oct 2026 00:00:00 GMT", 0),
    ],
)
def test_v05_retry_after_seconds_and_dates_are_capped(value, expected):
    assert retry_after(value, datetime(2026, 10, 8, tzinfo=UTC), 2) == expected


@pytest.mark.parametrize("compression", ["gzip", "deflate"])
def test_v06_bounded_decompressed_body_and_truncated_compression(compression):
    encode = gzip.compress if compression == "gzip" else zlib.compress
    response = Response(
        body=encode(b"x" * 10000),
        headers={"content-type": "text/plain", "content-encoding": compression},
    )
    fetcher, _, _ = acquirer(response, policy=FetchPolicy(max_bytes=100))
    assert fetcher.fetch(URL).error.code == "body_too_large" and response.closed
    body = encode("café Python is required.".encode())
    fetcher, _, _ = acquirer(
        Response(body=body, headers={"content-type": "text/plain", "content-encoding": compression})
    )
    assert fetcher.fetch(URL).text == "café Python is required."
    fetcher, _, _ = acquirer(
        Response(
            body=body[:-2], headers={"content-type": "text/plain", "content-encoding": compression}
        )
    )
    assert fetcher.fetch(URL).error.code == "unsupported_encoding"


@pytest.mark.parametrize(
    "body,headers,code",
    [
        (b"x" * 101, {"content-type": "text/plain"}, "body_too_large"),
        (b"x", {"content-type": "text/plain", "content-length": "1000000"}, "body_too_large"),
        (b"binary", {"content-type": "application/pdf"}, "unsupported_type"),
        (b"binary", {"content-type": "application/octet-stream"}, "unsupported_type"),
        (b"text", {}, "unsupported_type"),
        (b"text", {"content-type": "text/plain", "content-encoding": "br"}, "unsupported_encoding"),
        (b"\xff", {"content-type": "text/plain"}, "invalid_text"),
        (b"text", {"content-type": "text/plain; charset=unknown"}, "invalid_text"),
        (b"\0text", {"content-type": "text/plain"}, "invalid_text"),
        (b"  \n", {"content-type": "text/plain"}, "empty_source"),
        (
            b"<title>CAPTCHA</title><main>Verify you are human</main>",
            {"content-type": "text/html"},
            "captcha",
        ),
        (
            b"<div id='app'></div><script>render()</script>",
            {"content-type": "text/html"},
            "js_only",
        ),
        (
            b"<title>Job</title><div id='app'>Loading...</div><script>render()</script>",
            {"content-type": "text/html"},
            "js_only",
        ),
        (
            b"<noscript>Enable JavaScript</noscript><script>render()</script>",
            {"content-type": "text/html"},
            "js_only",
        ),
    ],
)
def test_v06_v07_v09_unsupported_content_and_access_gates_require_manual_entry(body, headers, code):
    response = Response(body=body, headers=headers)
    fetcher, transport, _ = acquirer(response, policy=FetchPolicy(max_bytes=100))
    result = fetcher.fetch(URL)
    assert result.error.code == code and result.text is None
    assert (
        result.error.detail()["manual_fallback"] and response.closed and len(transport.calls) == 1
    )


@pytest.mark.parametrize(
    "error", [FetchError("tls_error"), FetchError("proxy_denied"), FetchError("access_denied", 403)]
)
def test_v07_nonretryable_tls_proxy_and_access_failures_do_not_retry(error):
    fetcher, transport, clock = acquirer(error)
    assert fetcher.fetch(URL).error.code == error.code
    assert len(transport.calls) == 1 and clock.waits == []


@pytest.mark.parametrize(
    "options",
    [
        {"redirects": 4},
        {"attempts": 4},
        {"max_bytes": 200001},
        {"read_timeout": 0},
        {"total_timeout": 61},
        {"attempts": 1.5},
    ],
)
def test_v05_configuration_cannot_remove_acquisition_bounds(options):
    with pytest.raises(ValueError):
        FetchPolicy(**options)


def test_v02_public_ipv4_and_ipv6_are_supported():
    assert public_address(PUBLIC) and public_address("2606:4700:4700::1111")
    response = Response(body=b"Authored public IPv6 posting.")
    fetcher, transport, _ = acquirer(response)
    assert fetcher.fetch("https://[2606:4700:4700::1111]/").error is None
    assert transport.calls[0][0].address == "2606:4700:4700::1111"


@pytest.mark.parametrize("url", ["https://@example.com/", "https://:@example.com/"])
def test_v02_empty_userinfo_is_rejected_before_transport(url):
    fetcher, transport, _ = acquirer()
    assert fetcher.fetch(url).error.code == "invalid_url" and transport.calls == []


def test_v03_resolved_ipv6_addresses_are_canonicalized_before_pinning():
    fetcher, transport, _ = acquirer(
        Response(), resolver=Resolver([["2606:4700:4700:0000:0000:0000:0000:1111"]])
    )
    assert fetcher.fetch(URL).error is None
    assert transport.calls[0][0].address == "2606:4700:4700::1111"
