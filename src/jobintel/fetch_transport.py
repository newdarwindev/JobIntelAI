"""Pinned HTTP connections; proxy refusals never cause a direct fallback."""

import http.client
import ipaddress
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit, urlunsplit
from urllib.request import getproxies, proxy_bypass_environment

from jobintel.fetch_destinations import DNSResolver
from jobintel.fetch_types import FetchError


def configured_proxy(destination, proxies):
    if proxy_bypass_environment(destination.host, proxies):
        return None
    value = proxies.get(destination.scheme) or proxies.get("all")
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port or 80
    except ValueError:
        raise FetchError("proxy_unsupported") from None
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise FetchError("proxy_unsupported")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise FetchError("proxy_unsupported")
    return parsed.hostname, port


class PinnedConnection(http.client.HTTPConnection):
    def __init__(self, destination, policy, remaining, proxy, context, proxy_resolver=None):
        super().__init__(
            destination.host, destination.port, timeout=min(policy.connect_timeout, remaining)
        )
        self.destination, self.proxy, self.context = destination, proxy, context
        self.proxy_resolver = proxy_resolver or DNSResolver()
        self.remaining, self.guard = remaining, None

    def expire(self):
        try:
            if self.sock:
                self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def connect(self):
        started = time.monotonic()
        target = self.connection_target()
        budget = self.remaining - (time.monotonic() - started)
        if budget <= 0:
            raise FetchError("deadline", 504, True)
        self.sock = socket.create_connection(target, min(self.timeout, budget))
        if not self.proxy and ipaddress.ip_address(
            self.sock.getpeername()[0]
        ) != ipaddress.ip_address(self.destination.address):
            self.close()
            raise FetchError("blocked_destination", 422)
        self.guard = threading.Timer(
            max(0, self.remaining - (time.monotonic() - started)), self.expire
        )
        self.guard.daemon = True
        self.guard.start()
        if self.proxy and self.destination.scheme == "https":
            try:
                self.tunnel()
            except TimeoutError:
                raise
            except OSError:
                raise FetchError("proxy_denied") from None
        if self.destination.scheme == "https":
            self.sock = self.context.wrap_socket(
                self.sock, server_hostname=self.destination.host, do_handshake_on_connect=False
            )
            self.sock.do_handshake()

    def connection_target(self):
        if not self.proxy:
            return self.destination.address, self.destination.port
        addresses = self.proxy_resolver.resolve(*self.proxy, self.timeout)
        return str(ipaddress.ip_address(addresses[0])), self.proxy[1]

    def tunnel(self):
        authority = self.destination.pinned_authority
        self.sock.sendall(
            f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode("ascii")
        )
        response = http.client.HTTPResponse(self.sock, method="CONNECT")
        try:
            response.begin()
            if response.status != 200:
                raise FetchError("proxy_denied")
        finally:
            response.close()

    def close(self):
        if self.guard:
            self.guard.cancel()
        super().close()


class TransportResponse:
    def __init__(self, connection, response, sock, remaining):
        self.connection, self.response, self.sock = connection, response, sock
        self.status = response.status
        self.headers = {key.lower(): value for key, value in response.getheaders()}
        self.guard = threading.Timer(max(0, remaining), self.expire)
        self.guard.daemon = True
        self.guard.start()

    def expire(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def read(self, size, timeout):
        if self.response.isclosed():
            return b""
        try:
            self.sock.settimeout(timeout)
            return self.response.read1(size)
        except TimeoutError:
            raise FetchError("read_timeout", 504, True) from None
        except ssl.SSLError:
            raise FetchError("tls_error") from None
        except (OSError, http.client.HTTPException):
            raise FetchError("network_failure", 502, True) from None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.guard.cancel()
        self.response.close()
        self.connection.close()


class HttpTransport:
    def __init__(self, *, proxies=None, context=None, proxy_resolver=None):
        self.proxies = proxies
        self.proxy_resolver = proxy_resolver
        self.context = context or ssl.create_default_context()
        if not self.context.check_hostname or self.context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("acquisition requires verified TLS")

    def get(self, destination, policy, remaining):
        started = time.monotonic()
        proxies = getproxies() if self.proxies is None else self.proxies
        proxy = configured_proxy(destination, proxies)
        connection = PinnedConnection(
            destination, policy, remaining, proxy, self.context, self.proxy_resolver
        )
        try:
            self.connect(connection)
            sock = connection.sock
            sock.settimeout(min(policy.read_timeout, remaining))
            parsed = urlsplit(destination.url)
            target = urlunsplit(("", "", parsed.path, parsed.query, ""))
            if proxy and destination.scheme == "http":
                target = urlunsplit(
                    ("http", destination.pinned_authority, parsed.path, parsed.query, "")
                )
            connection.request(
                "GET",
                target,
                headers={
                    "Host": destination.authority,
                    "User-Agent": "JobIntelAI/0.1",
                    "Accept": "text/html, text/plain, application/xhtml+xml",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            return TransportResponse(
                connection, response, sock, remaining - (time.monotonic() - started)
            )
        except FetchError:
            connection.close()
            raise
        except TimeoutError:
            connection.close()
            raise FetchError("read_timeout", 504, True) from None
        except ssl.SSLError:
            connection.close()
            raise FetchError("tls_error") from None
        except (OSError, http.client.HTTPException):
            connection.close()
            raise FetchError("network_failure", 502, True) from None

    @staticmethod
    def connect(connection):
        try:
            connection.connect()
        except TimeoutError:
            raise FetchError("connect_timeout", 504, True) from None
        except ssl.SSLError:
            raise FetchError("tls_error") from None
