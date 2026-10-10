"""V02-V06: verified IP selection happens before any HTTP bytes are sent."""

import io
import socket
import ssl
from dataclasses import replace

import pytest

from jobintel.fetch_destinations import Destination
from jobintel.fetch_transport import HttpTransport, PinnedConnection, configured_proxy
from jobintel.fetch_types import FetchError, FetchPolicy
from tests.acquisition_fakes import PUBLIC, URL, Resolver

PACKET = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 6\r\n\r\nPython"


class WireSocket:
    def __init__(self, *packets, peer=PUBLIC, handshake_error=None):
        self.packets = list(packets or [PACKET])
        self.peer, self.handshake_error = peer, handshake_error
        self.sent, self.timeouts, self.closed, self.shutdowns = [], [], False, []

    def getpeername(self):
        return self.peer, 443

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def makefile(self, *_):
        return io.BytesIO(self.packets.pop(0))

    def close(self):
        self.closed = True

    def shutdown(self, how):
        self.shutdowns.append(how)

    def do_handshake(self):
        if self.handshake_error:
            raise self.handshake_error


class VerifiedContext:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED

    def __init__(self):
        self.hostnames = []

    def wrap_socket(self, sock, *, server_hostname, do_handshake_on_connect):
        self.hostnames.append(server_hostname)
        assert do_handshake_on_connect is False
        return sock


def destination(scheme="https"):
    return Destination(
        URL.replace("https:", scheme + ":"),
        "example.com",
        443 if scheme == "https" else 80,
        PUBLIC,
        scheme,
    )


def install_socket(monkeypatch, sock):
    calls = []

    def connect(address, timeout):
        calls.append((address, timeout))
        return sock

    monkeypatch.setattr("jobintel.fetch_transport.socket.create_connection", connect)
    monkeypatch.setattr("jobintel.fetch_transport.DNSResolver.resolve", lambda *_: ["10.0.0.2"])
    return calls


def test_v03_direct_connection_pins_numeric_ip_and_preserves_tls_hostname(monkeypatch):
    sock, context = WireSocket(), VerifiedContext()
    calls = install_socket(monkeypatch, sock)
    transport = HttpTransport(proxies={}, context=context)
    with transport.get(destination(), FetchPolicy(), 10) as response:
        assert response.read(100, 5) == b"Python"
        assert response.status == 200
    assert calls == [((PUBLIC, 443), 3)]
    assert context.hostnames == ["example.com"] and sock.closed
    sent = b"".join(sock.sent)
    assert b"Host: example.com" in sent and b"GET /authored " in sent
    assert b"Authorization:" not in sent and b"Cookie:" not in sent and b"Referer:" not in sent


def test_v03_rebound_or_unexpected_peer_receives_no_http_bytes(monkeypatch):
    sock = WireSocket(peer="127.0.0.1")
    calls = install_socket(monkeypatch, sock)
    with pytest.raises(FetchError) as error:
        HttpTransport(proxies={}, context=VerifiedContext()).get(destination(), FetchPolicy(), 10)
    assert error.value.code == "blocked_destination"
    assert calls == [((PUBLIC, 443), 3)] and sock.sent == [] and sock.closed


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_v03_supported_http_proxy_preserves_destination_pin_and_never_falls_back(
    monkeypatch, scheme
):
    packets = (
        [b"HTTP/1.0 200 Connection established\r\n\r\n", PACKET] if scheme == "https" else [PACKET]
    )
    sock, context = WireSocket(*packets, peer="10.0.0.2"), VerifiedContext()
    calls = install_socket(monkeypatch, sock)
    with HttpTransport(proxies={scheme: "http://proxy.internal:8080"}, context=context).get(
        destination(scheme), FetchPolicy(), 10
    ) as response:
        assert response.read(100, 5) == b"Python"
    assert calls == [(("10.0.0.2", 8080), 3)]
    sent = b"".join(sock.sent)
    expected = (
        f"CONNECT {PUBLIC}:443".encode()
        if scheme == "https"
        else f"GET http://{PUBLIC}:80/authored".encode()
    )
    assert expected in sent and b"Host: example.com" in sent
    assert b"Authorization:" not in sent and b"Cookie:" not in sent


def test_v03_proxy_denial_does_not_attempt_direct_connection(monkeypatch):
    sock = WireSocket(b"HTTP/1.0 403 Denied\r\n\r\n", peer="10.0.0.2")
    calls = install_socket(monkeypatch, sock)
    with pytest.raises(FetchError) as error:
        HttpTransport(
            proxies={"https": "http://proxy.internal:8080"}, context=VerifiedContext()
        ).get(destination(), FetchPolicy(), 10)
    assert error.value.code == "proxy_denied" and len(calls) == 1 and sock.closed


def test_v05_proxy_resolution_timeout_receives_no_request_or_direct_fallback(monkeypatch):
    calls = install_socket(monkeypatch, WireSocket())
    resolver = Resolver([FetchError("dns_timeout", 504, True)])
    with pytest.raises(FetchError) as error:
        HttpTransport(
            proxies={"https": "http://proxy.internal:8080"},
            context=VerifiedContext(),
            proxy_resolver=resolver,
        ).get(destination(), FetchPolicy(), 10)
    assert error.value.code == "dns_timeout" and calls == []
    assert resolver.calls == [("proxy.internal", 8080, 3)]


def test_v03_public_ipv6_proxy_connect_uses_bracketed_pinned_authority(monkeypatch):
    address = "2606:4700:4700::1111"
    target = Destination(URL, "example.com", 443, address, "https")
    sock = WireSocket(b"HTTP/1.1 200 Connection established\r\n\r\n", PACKET, peer="10.0.0.2")
    calls = install_socket(monkeypatch, sock)
    context = VerifiedContext()
    with HttpTransport(proxies={"https": "http://proxy.internal:8080"}, context=context).get(
        target, FetchPolicy(), 10
    ) as response:
        assert response.read(100, 5) == b"Python"
    assert calls == [(("10.0.0.2", 8080), 3)]
    assert f"CONNECT [{address}]:443 HTTP/1.1".encode() in b"".join(sock.sent)
    assert context.hostnames == ["example.com"]


def test_v03_public_ipv6_peer_comparison_is_numeric(monkeypatch):
    address = "2606:4700:4700::1111"
    sock = WireSocket(peer="2606:4700:4700:0000:0000:0000:0000:1111")
    install_socket(monkeypatch, sock)
    with HttpTransport(proxies={}, context=VerifiedContext()).get(
        Destination(URL, "example.com", 443, address, "https"), FetchPolicy(), 10
    ) as response:
        assert response.read(100, 5) == b"Python"


@pytest.mark.parametrize(
    "failure,code,retryable",
    [
        (TimeoutError("private diagnostic"), "read_timeout", True),
        (ssl.SSLError("private diagnostic"), "tls_error", False),
    ],
)
def test_v05_v07_stream_errors_remain_safe_typed_failures(monkeypatch, failure, code, retryable):
    sock = WireSocket()
    install_socket(monkeypatch, sock)
    with HttpTransport(proxies={}, context=VerifiedContext()).get(
        destination(), FetchPolicy(), 10
    ) as response:

        def fail_read(_):
            raise failure

        monkeypatch.setattr(response.response, "read1", fail_read)
        with pytest.raises(FetchError) as error:
            response.read(100, 5)
        assert error.value.code == code and error.value.retryable == retryable
        assert "private diagnostic" not in str(error.value)
    assert sock.closed


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


def test_v03_proxy_environment_and_no_proxy_are_respected(monkeypatch):
    monkeypatch.setenv("https_proxy", "http://proxy.internal:8080")
    monkeypatch.setenv("no_proxy", "example.com")
    sock = WireSocket()
    calls = install_socket(monkeypatch, sock)
    with HttpTransport(context=VerifiedContext()).get(destination(), FetchPolicy(), 10) as response:
        assert response.read(100, 5) == b"Python"
    assert calls == [((PUBLIC, 443), 3)]


def test_v05_v07_connect_timeout_and_tls_verification_are_typed(monkeypatch):
    def timeout(*_):
        raise TimeoutError("authored private diagnostic")

    monkeypatch.setattr("jobintel.fetch_transport.socket.create_connection", timeout)
    with pytest.raises(FetchError) as error:
        HttpTransport(proxies={}, context=VerifiedContext()).get(destination(), FetchPolicy(), 10)
    assert error.value.code == "connect_timeout" and error.value.retryable
    sock = WireSocket(handshake_error=ssl.SSLCertVerificationError("authored certificate failure"))
    install_socket(monkeypatch, sock)
    with pytest.raises(FetchError) as error:
        HttpTransport(proxies={}, context=VerifiedContext()).get(destination(), FetchPolicy(), 10)
    assert error.value.code == "tls_error" and not error.value.retryable and sock.sent == []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with pytest.raises(ValueError, match="verified TLS"):
        HttpTransport(context=context)


def test_v05_deadline_guard_closes_socket_and_response_guards_cancel(monkeypatch):
    sock = WireSocket()
    install_socket(monkeypatch, sock)
    connection = PinnedConnection(destination("http"), FetchPolicy(), 0.5, None, VerifiedContext())
    connection.connect()
    connection.expire()
    assert sock.shutdowns == [socket.SHUT_RDWR]
    connection.close()
    assert connection.guard.finished.is_set()
    sock = WireSocket()
    install_socket(monkeypatch, sock)
    with HttpTransport(proxies={}, context=VerifiedContext()).get(
        destination(), FetchPolicy(), 10
    ) as response:
        response.expire()
    assert response.guard.finished.is_set() and sock.shutdowns == [socket.SHUT_RDWR]


def test_policy_proxy_requires_lease_and_keeps_control_header_outside_tls(monkeypatch):
    proxy = ("proxy.internal", 8080)
    transport = HttpTransport(
        mode="policy-proxy",
        proxies={"https": "http://proxy.internal:8080"},
        context=VerifiedContext(),
    )
    with pytest.raises(FetchError) as error:
        transport.get(destination(), FetchPolicy(), 10)
    assert error.value.code == "proxy_capability"
    packet = PACKET.replace(
        b"Content-Type:", b"JobIntel-Egress-Error: blocked_destination\r\nContent-Type:"
    )
    sock = WireSocket(b"HTTP/1.1 200 Connection established\r\n\r\n", packet)
    calls = install_socket(monkeypatch, sock)
    leased = replace(destination(), route="a" * 64, proxy=proxy)
    with transport.get(leased, FetchPolicy(), 10) as response:
        assert response.read(100, 5) == b"Python"
    assert len(calls) == 1 and b"CONNECT example.com:443" in sock.sent[0]
    assert b"JobIntel-Route:" in sock.sent[0]
    assert b"JobIntel-Route:" not in b"".join(sock.sent[1:])
