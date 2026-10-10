"""Trusted loopback/private-network gateway; never run outside authorized egress."""

import argparse
import http.client
import ipaddress
import json
import select
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit
from urllib.request import getproxies

from jobintel.egress_policy import (
    CAPABILITIES,
    CAPABILITY_PATH,
    RESOLVE_PATH,
    ROUTE_HEADER,
    EgressPolicy,
)
from jobintel.fetch_destinations import canonical_destination
from jobintel.fetch_types import FetchError


class EgressHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass

    def answer(self, status, payload, error=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        if error:
            self.send_header("JobIntel-Egress-Error", error)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def refuse(self, error):
        self.answer(error.status, {"code": error.code}, error.code)

    def do_POST(self):
        try:
            if self.path != RESOLVE_PATH or self.headers.get("Transfer-Encoding"):
                raise FetchError("proxy_capability", 503)
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 1024:
                raise FetchError("proxy_capability", 503)
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict) or set(payload) != {"host", "scheme"}:
                raise FetchError("proxy_capability", 503)
            self.answer(200, self.server.policy.issue(payload["host"], payload["scheme"]))
        except FetchError as error:
            self.refuse(error)
        except (ValueError, TypeError):
            self.refuse(FetchError("proxy_capability", 503))

    def do_GET(self):
        if self.path == CAPABILITY_PATH:
            return self.answer(200, CAPABILITIES)
        upstream = None
        try:
            parsed = urlsplit(canonical_destination(self.path))
            if parsed.scheme != "http" or parsed.port is not None:
                raise FetchError("proxy_denied")
            destination = self.server.policy.consume(
                self.headers.get(ROUTE_HEADER), parsed.hostname, "http"
            )
            upstream = self.open_upstream(destination)
            try:
                self.forward_http(upstream, destination, parsed)
            except (OSError, http.client.HTTPException):
                pass
        except FetchError as error:
            self.refuse(error)
        except OSError:
            self.refuse(FetchError("network_failure"))
        finally:
            if upstream:
                upstream.close()
            self.close_connection = True

    def open_upstream(self, destination):
        upstream = socket.create_connection((destination.address, destination.port), timeout=3)
        if ipaddress.ip_address(upstream.getpeername()[0]) != ipaddress.ip_address(
            destination.address
        ):
            upstream.close()
            raise FetchError("blocked_destination", 422)
        return upstream

    def forward_http(self, upstream, destination, parsed):
        connection = http.client.HTTPConnection(destination.host, 80, timeout=5)
        connection.sock = upstream
        try:
            connection.request(
                "GET",
                urlunsplit(("", "", parsed.path, parsed.query, "")),
                headers={
                    "Host": destination.authority,
                    "User-Agent": "JobIntelAI/0.1",
                    "Accept": "text/html, text/plain, application/xhtml+xml",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() not in {
                    "connection",
                    "transfer-encoding",
                    "server",
                    "date",
                    "jobintel-egress-error",
                }:
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            deadline, size = time.monotonic() + 20, 0
            while time.monotonic() < deadline and size <= 200_000:
                part = response.read1(min(4096, 200_001 - size))
                if not part:
                    break
                self.wfile.write(part)
                self.wfile.flush()
                size += len(part)
        finally:
            connection.close()

    def do_CONNECT(self):
        try:
            parsed = urlsplit(f"https://{self.path}")
            if (
                parsed.port != 443
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise FetchError("proxy_denied")
            destination = self.server.policy.consume(
                self.headers.get(ROUTE_HEADER), parsed.hostname, "https"
            )
            with self.open_upstream(destination) as upstream:
                self.connection.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                self.tunnel(upstream)
        except FetchError as error:
            self.refuse(error)
        except (OSError, ValueError):
            self.close_connection = True
        finally:
            self.close_connection = True

    def tunnel(self, upstream):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.connection, upstream], [], [], 0.1)
            for source in ready:
                part = source.recv(16384)
                if not part:
                    return
                (upstream if source is self.connection else self.connection).sendall(part)


def gateway(host, port, allowed_hosts, *, resolver=None, handler=EgressHandler):
    instance = ThreadingHTTPServer((host, port), handler)
    instance.daemon_threads = True
    instance.policy = EgressPolicy(allowed_hosts, resolver=resolver)
    return instance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--allow-host", action="append", required=True)
    args = parser.parse_args()
    # This reference gateway requires an administrator-authorized direct egress host.
    # Chaining a domain proxy without its validation contract would lose the pin.
    if any(key in getproxies() for key in ("http", "https", "all")):
        parser.error(
            "gateway requires authorized direct egress; inherited proxies cannot be bypassed"
        )
    instance = gateway(args.bind, args.port, args.allow_host)
    try:
        instance.serve_forever()
    finally:
        instance.server_close()


if __name__ == "__main__":
    main()
