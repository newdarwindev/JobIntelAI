"""Real HTTP/HTTPS fixture origin with bounded, sanitized diagnostics."""

import argparse
import json
import ssl
import threading
import time
from collections import Counter, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.acquisition_fixtures.scenarios import content_reply, redirect, reply


class Diagnostics:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = deque(maxlen=2048)
        self.counts = Counter()

    def record(self, **event):
        with self.lock:
            self.events.append(event)
            self.counts[event.get("scenario", event.get("kind"))] += 1
            return self.counts[event.get("scenario", event.get("kind"))]

    def snapshot(self):
        with self.lock:
            return {"events": list(self.events), "counts": dict(self.counts)}


class OriginHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/health":
            return self.send_reply(200, b"ok", {})
        if self.path == "/diagnostics":
            body = json.dumps(self.server.diagnostics.snapshot()).encode()
            return self.send_reply(200, body, {"Content-Type": "application/json"})
        known = content_reply(self.path, self.server.source) or redirect(self.path)
        known = known or self.path in {
            "/rate-limit",
            "/retry-success",
            "/server-error",
            "/server-success",
            "/authored-denied",
        }
        scenario = self.path if known else "refused"
        count = self.server.diagnostics.record(
            kind="http",
            scenario=scenario,
            tls=isinstance(self.connection, ssl.SSLSocket),
            authority=self.headers.get("Host")
            if self.headers.get("Host") in {"example.com", "rebind.example.test"}
            else "refused",
        )
        response = reply(self.path, count, self.server.source)
        try:
            self.send_reply(
                response.status, response.body, response.headers, response.chunked, response.pause
            )
        except (OSError, ssl.SSLError):
            # Expected when bounded clients close oversized/slow streams.
            pass

    def send_reply(self, status, body, headers, chunked=False, pause=0):
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header(
            "Transfer-Encoding" if chunked else "Content-Length",
            "chunked" if chunked else str(len(body)),
        )
        self.send_header("Connection", "close")
        self.end_headers()
        if chunked:
            for start in range(0, len(body), 256):
                part = body[start : start + 256]
                self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                self.wfile.flush()
                if pause:
                    time.sleep(pause)
            self.wfile.write(b"0\r\n\r\n")
        else:
            self.wfile.write(body)
        self.close_connection = True


def servers(host, http_port, https_port, trust, source):
    diagnostics = Diagnostics()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(trust / "origin.pem"), str(trust / "origin.key"))

    def sni(_socket, name, _context):
        diagnostics.record(
            kind="tls",
            hostname=name
            if name in {"example.com", "rebind.example.test", "wrong.example.test"}
            else "refused",
        )

    context.set_servername_callback(sni)
    result = []
    for port, tls in [(http_port, False), (https_port, True)]:
        server = ThreadingHTTPServer((host, port), OriginHandler)
        server.source, server.diagnostics = source, diagnostics
        if tls:
            server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        result.append(server)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trust", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path("data/sample_jobs/SYN-01.txt"))
    args = parser.parse_args()
    running = servers("0.0.0.0", 8080, 8443, args.trust, args.source.read_text())
    try:
        threading.Event().wait()
    finally:
        for server in running:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
