"""V02-V07: libcurl pins, route isolation, verified trust and bounded transfers."""

import ssl
import time
from dataclasses import replace

import pycurl
import pytest

from jobintel.fetch_destinations import Destination
from jobintel.fetch_transport import CurlResponse, HttpTransport, configured_proxy, curl_failure
from jobintel.fetch_types import FetchError, FetchPolicy
from scripts.acquisition_fixtures.local import local_acquirer, local_fixtures
from tests.acquisition_fakes import PUBLIC, URL, Resolver


class Options:
    def __init__(self, connect_status=0):
        self.values, self.connect_status = {}, connect_status

    def setopt(self, key, value):
        self.values[key] = value

    def getinfo(self, key):
        assert key == pycurl.HTTP_CONNECTCODE
        return self.connect_status


def destination(scheme="https", address=PUBLIC):
    return Destination(
        URL.replace("https:", scheme + ":"),
        "example.com",
        443 if scheme == "https" else 80,
        address,
        scheme,
    )


def options(target, *, proxy=None):
    curl = Options()
    transport = HttpTransport(proxies={})
    response = CurlResponse(FetchPolicy(), "127.0.0.1" if proxy else target.address)
    transport.options(curl, target, FetchPolicy(), time.monotonic() + 10, proxy, response)
    return curl.values, response


@pytest.mark.parametrize("address", [PUBLIC, "2606:4700:4700::1111"])
def test_v03_direct_pin_and_numeric_peer_comparison_precede_http(address):
    settings, response = options(destination(address=address))
    pin = f"[{address}]" if ":" in address else address
    assert settings[pycurl.RESOLVE] == [f"example.com:443:{pin}"]
    assert settings[pycurl.URL] == URL
    assert settings[pycurl.PROXY] == "" and settings[pycurl.NOPROXY] == ""
    peer = "2606:4700:4700:0000:0000:0000:0000:1111" if ":" in address else address
    assert response.prerequest(peer) == pycurl.PREREQFUNC_OK
    assert response.prerequest("127.0.0.1") == pycurl.PREREQFUNC_ABORT
    assert response.error.code == "blocked_destination" and response.tell() == 0


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("address", [PUBLIC, "2606:4700:4700::1111"])
def test_v03_numeric_proxy_preserves_pin_original_host_and_tls_identity(scheme, address):
    target = destination(scheme, address)
    settings, _ = options(target, proxy=("proxy.internal", 8080))
    assert settings[pycurl.PROXY] == "http://127.0.0.1:8080"
    assert settings[pycurl.NOPROXY] == ""
    if scheme == "https":
        assert settings[pycurl.CONNECT_TO] == [f"example.com:443:{target.pinned_authority}"]
        assert settings[pycurl.URL] == target.url
    else:
        assert settings[pycurl.REQUEST_TARGET] == f"http://{target.pinned_authority}/authored"
    assert settings[pycurl.HTTPHEADER] == [
        "Host: example.com",
        "User-Agent: JobIntelAI/0.1",
        "Accept: text/html, text/plain, application/xhtml+xml",
        "Accept-Encoding: gzip, deflate",
        "Connection: close",
    ]
    assert settings[pycurl.SSL_VERIFYPEER] == 1 and settings[pycurl.SSL_VERIFYHOST] == 2
    assert settings[pycurl.FOLLOWLOCATION] == settings[pycurl.HTTP_CONTENT_DECODING] == 0


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_policy_control_header_is_scoped_to_gateway_not_tls_origin(scheme):
    target = replace(destination(scheme), route="a" * 64, proxy=("proxy.internal", 8080))
    settings, _ = options(target, proxy=target.proxy)
    route = "JobIntel-Route: " + "a" * 64
    if scheme == "https":
        assert settings[pycurl.PROXYHEADER] == [route]
        assert route not in settings[pycurl.HTTPHEADER]
    else:
        assert route in settings[pycurl.HTTPHEADER]
    assert pycurl.CONNECT_TO not in settings and settings[pycurl.URL] == target.url


def test_v03_policy_mode_refuses_missing_or_foreign_lease_before_connection():
    transport = HttpTransport(mode="policy-proxy", proxies={"https": "http://proxy.internal:8080"})
    for target in [destination(), replace(destination(), route="a" * 64, proxy=("foreign", 8080))]:
        with pytest.raises(FetchError, match="gateway capability"):
            transport.get(target, FetchPolicy(), 10)


def test_v05_proxy_dns_timeout_receives_no_request_or_direct_fallback(monkeypatch):
    resolver = Resolver([FetchError("dns_timeout", 504, True)])

    def unexpected():
        pytest.fail("no curl handle may be created after DNS refusal")

    monkeypatch.setattr("jobintel.fetch_transport.pycurl.Curl", unexpected)
    transport = HttpTransport(
        proxies={"https": "http://proxy.internal:8080"}, proxy_resolver=resolver
    )
    with pytest.raises(FetchError) as error:
        transport.get(destination(), FetchPolicy(), 10)
    assert error.value.code == "dns_timeout"
    assert resolver.calls == [("proxy.internal", 8080, 3)]


@pytest.mark.parametrize(
    "proxy",
    [
        "https://proxy.internal",
        "http://user:secret@proxy.internal",
        "socks5://proxy.internal",
        "http://proxy.internal/path",
        "http://proxy.internal:invalid",
        "http://[invalid",
    ],
)
def test_v03_unsupported_or_credential_proxy_is_explicitly_refused(proxy):
    with pytest.raises(FetchError) as error:
        configured_proxy(destination(), {"https": proxy})
    assert error.value.code == "proxy_unsupported"


def test_v03_auto_honors_no_proxy_but_explicit_proxy_mode_refuses_fallback(monkeypatch):
    monkeypatch.setenv("https_proxy", "http://proxy.internal:8080")
    monkeypatch.setenv("no_proxy", "example.com")
    assert HttpTransport().selected_proxy(destination()) is None
    with pytest.raises(FetchError) as error:
        HttpTransport(mode="pinned-proxy").selected_proxy(destination())
    assert error.value.code == "proxy_capability"


@pytest.mark.parametrize(
    "failure,connect_status,code,retryable",
    [
        (pycurl.E_OPERATION_TIMEDOUT, 0, "connect_timeout", True),
        (pycurl.E_PEER_FAILED_VERIFICATION, 200, "tls_error", False),
        (pycurl.E_SSL_CONNECT_ERROR, 0, "tls_error", False),
        (pycurl.E_RECV_ERROR, 403, "proxy_denied", False),
        (pycurl.E_PARTIAL_FILE, 200, "network_failure", True),
    ],
)
def test_v05_v07_safe_typed_failures(failure, connect_status, code, retryable):
    with pytest.raises(FetchError) as error:
        curl_failure(Options(connect_status), CurlResponse(FetchPolicy(), PUBLIC), failure)
    assert error.value.code == code and error.value.retryable == retryable


def test_v05_v07_verified_context_required_and_buffer_is_bounded():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
    with pytest.raises(ValueError, match="verified TLS"):
        HttpTransport(context=context)
    with CurlResponse(FetchPolicy(max_bytes=6), PUBLIC) as response:
        response.status = 200
        assert response.receive(b"Python") == 6
        assert response.receive(b"!") == 0
        assert response.error.code == "body_too_large" and response.tell() == 6
    assert response.closed


@pytest.fixture(scope="module")
def wire(tmp_path_factory):
    with local_fixtures(tmp_path_factory.mktemp("curl-wire"), "Python is required.") as fixtures:
        yield fixtures


def requests(wire):
    return sum(e.get("kind") == "http" for e in wire["origin"].snapshot()["events"])


def test_v03_real_prerequest_abort_sends_no_origin_http(monkeypatch, wire):
    original = CurlResponse.prerequest
    monkeypatch.setattr(CurlResponse, "prerequest", lambda self, *_: original(self, PUBLIC))
    before = requests(wire)
    result = local_acquirer(wire).fetch("https://example.com/text")
    assert result.error.code == "blocked_destination" and requests(wire) == before


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_v03_real_direct_numeric_connection_and_verified_original_hostname(wire, scheme):
    gateway = wire["gateway"]
    port = gateway.https_port if scheme == "https" else gateway.http_port
    # Only this transport-level fixture supplies a loopback pin, bypassing no URL policy.
    target = Destination(
        f"{scheme}://example.com:{port}/text", "example.com", port, "127.0.0.1", scheme
    )
    context = ssl.create_default_context(cafile=str(wire["ca"]))
    transport = HttpTransport(mode="direct", proxies={}, context=context)
    before = requests(wire)
    with transport.get(target, FetchPolicy(), 2) as response:
        assert response.status == 200 and response.read(100, 1) == b"Python is required."
    assert requests(wire) == before + 1 and response.closed


@pytest.mark.parametrize("seconds", [0.001, 0.04])
def test_v05_real_read_inactivity_at_supported_lower_bounds_closes_transfer(wire, seconds):
    policy = FetchPolicy(read_timeout=seconds, total_timeout=1, attempts=1)
    started = time.monotonic()
    result = local_acquirer(wire, policy=policy).fetch("https://example.com/slow")
    assert result.error.code == "read_timeout" and time.monotonic() - started < 0.5
