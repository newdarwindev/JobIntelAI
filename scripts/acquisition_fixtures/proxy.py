"""Test-only proxy: one exact numeric public pin, two ports, no arbitrary forwarding."""

import argparse
import http.client
import json
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from scripts.acquisition_fixtures.origin import Diagnostics

PIN = "93.184.216.34"
HOSTS = {"example.com", "rebind.example.test", "wrong.example.test"}


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def answer(self, status, body=b""):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def allowed(self, address, port, host=None):
        accepted = address == PIN and port in {80, 443} and (host is None or host in HOSTS)
        self.server.diagnostics.record(
            kind="proxy",
            method=self.command,
            pin=PIN if address == PIN else "refused",
            disposition="forwarded" if accepted else "denied",
            port=port if port in {80, 443} else None,
        )
        if not accepted:
            self.answer(403)
        return accepted

    def do_GET(self):
        if self.path in {"/health", "/diagnostics"}:
            body = (
                b"ok"
                if self.path == "/health"
                else json.dumps(self.server.diagnostics.snapshot()).encode()
            )
            return self.answer(200, body)
        try:
            target = urlsplit(self.path)
            port = target.port
        except ValueError:
            return self.answer(403)
        if target.scheme != "http" or target.username is not None or target.password is not None:
            return self.answer(403)
        if not self.allowed(target.hostname, port, self.headers.get("Host")):
            return
        origin = http.client.HTTPConnection(
            self.server.origin_host, self.server.http_port, timeout=3
        )
        try:
            origin.request(
                "GET", target.path, headers={"Host": self.headers["Host"], "Connection": "close"}
            )
            response = origin.getresponse()
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() not in {"server", "date", "connection", "transfer-encoding"}:
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while part := response.read1(4096):
                self.wfile.write(part)
                self.wfile.flush()
        except OSError:
            pass
        finally:
            origin.close()
            self.close_connection = True

    def do_CONNECT(self):
        # Never resolve a CONNECT hostname. Only this exact pin is routable.
        if self.path != f"{PIN}:443":
            self.allowed(None, None)
            return
        if not self.allowed(PIN, 443):
            return
        with socket.create_connection(
            (self.server.origin_host, self.server.https_port), timeout=3
        ) as upstream:
            self.connection.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            deadline = time.monotonic() + 10
            self.connection.settimeout(3)
            while time.monotonic() < deadline:
                ready, _, _ = select.select([self.connection, upstream], [], [], 0.2)
                if any(not self.relay(source, upstream) for source in ready):
                    break
        self.close_connection = True

    def relay(self, source, upstream):
        try:
            part = source.recv(16384)
            if not part:
                return False
            (upstream if source is self.connection else self.connection).sendall(part)
            return True
        except OSError:
            return False


def server(host, port, origin_host, http_port, https_port):
    instance = ThreadingHTTPServer((host, port), ProxyHandler)
    instance.origin_host, instance.http_port, instance.https_port = (
        origin_host,
        http_port,
        https_port,
    )
    instance.diagnostics = Diagnostics()
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    return instance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="origin")
    args = parser.parse_args()
    instance = server("0.0.0.0", 8088, args.origin, 8080, 8443)
    try:
        threading.Event().wait()
    finally:
        instance.shutdown()
        instance.server_close()


if __name__ == "__main__":
    main()
