"""Bounded local Responses emulator with safe diagnostics and no outbound requests."""

import argparse
import copy
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jobintel.openai_transport import EMULATOR_MODEL, EMULATOR_TOKEN
from jobintel.provider_config import PROMPT, strict_schema
from jobintel.schemas import Extraction
from jobintel.snapshots import content_hash

SCENARIOS = {
    "success",
    "refusal",
    "malformed_json",
    "invalid_schema",
    "invalid_evidence",
    "rate_limit",
    "quota",
    "server_error",
    "delay",
    "connection_close",
    "malformed_http",
    "truncated",
    "malformed_then_success",
}


class State:
    def __init__(self, root):
        self.responses = json.loads((root / "provider_responses.json").read_text())
        self.lock = threading.Lock()
        self.scenario = "success"
        self.requests = []
        self.history = []

    def select(self, scenario):
        with self.lock:
            self.scenario = scenario
            self.requests = []

    def record(self, payload, authenticated):
        inputs = payload.get("input")
        valid_input = (
            isinstance(inputs, list)
            and len(inputs) == 2
            and inputs[0] == {"role": "system", "content": PROMPT}
            and isinstance(inputs[1], dict)
            and inputs[1].get("role") == "user"
            and isinstance(inputs[1].get("content"), str)
        )
        text = inputs[1]["content"] if valid_input else ""
        checks = {
            "auth_valid": authenticated,
            "model_valid": payload.get("model") == EMULATOR_MODEL,
            "schema_valid": payload.get("text")
            == {
                "format": {
                    "type": "json_schema",
                    "name": "job_extraction_v2",
                    "strict": True,
                    "schema": strict_schema(),
                }
            },
            "parameters_valid": payload.get("store") is False
            and payload.get("max_output_tokens") == 8192,
            "input_valid": valid_input,
        }
        with self.lock:
            self.requests.append({"scenario": self.scenario, **checks})
            self.history.append({"scenario": self.scenario, **checks})
            return text, self.scenario, len(self.requests), all(checks.values())

    def diagnostics(self):
        with self.lock:
            return {
                "mode": "emulator",
                "model": EMULATOR_MODEL,
                "scenario": self.scenario,
                "request_count": len(self.requests),
                "requests": copy.deepcopy(self.requests),
                "history": copy.deepcopy(self.history),
            }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, body, *, raw=False, request_id=None):
        data = body if raw else json.dumps(body).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if request_id:
                self.send_header("x-request-id", request_id)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"mode": "emulator", "inference": False})
        elif self.path == "/diagnostics":
            self.respond(200, self.server.state.diagnostics())
        else:
            self.respond(404, {"error": {"code": "unknown_route"}})

    def read_payload(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2_000_000:
                return None
            payload = json.loads(self.rfile.read(size))
            return payload if isinstance(payload, dict) else None
        except (ValueError, TimeoutError):
            return None

    def do_POST(self):
        self.connection.settimeout(5)
        payload = self.read_payload()
        if payload is None:
            self.respond(400, {"error": {"code": "invalid_request"}})
            return
        authenticated = self.headers.get("Authorization") == f"Bearer {EMULATOR_TOKEN}"
        if self.path == "/control" and authenticated:
            scenario = payload.get("scenario")
            if isinstance(scenario, str) and scenario in SCENARIOS:
                self.server.state.select(scenario)
                self.respond(200, self.server.state.diagnostics())
                return
        if self.path != "/v1/responses":
            self.respond(404, {"error": {"code": "unknown_route"}})
            return
        text, scenario, count, valid = self.server.state.record(payload, authenticated)
        if not valid:
            self.respond(400 if authenticated else 401, {"error": {"code": "contract_violation"}})
            return
        self.complete(text, scenario, count)

    def complete(self, text, scenario, count):
        if scenario == "connection_close":
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if scenario == "delay":
            time.sleep(2)
        if scenario in {"quota", "rate_limit", "server_error"}:
            self.respond(
                500 if scenario == "server_error" else 429,
                {"error": {"code": "insufficient_quota" if scenario == "quota" else scenario}},
            )
            return
        if scenario == "malformed_http":
            self.respond(200, b"{", raw=True)
            return
        response = authored_response(self.server.state, text, scenario, count)
        if response is None:
            self.respond(400, {"error": {"code": "unsupported_authored_hash"}})
            return
        self.respond(200, response, request_id=f"emulator-request-{count}")


def authored_response(state, text, scenario, count):
    fixture = state.responses.get(content_hash(text))
    if fixture is None:
        return None
    extraction = Extraction.model_validate(fixture).model_dump(mode="json")
    if scenario == "invalid_evidence":
        extraction["requirements"][0]["evidence"]["quote"] = "Authored invalid evidence"
    if scenario == "invalid_schema":
        extraction["schema_version"] = 1
    output = json.dumps(extraction)
    if scenario == "malformed_json" or (scenario == "malformed_then_success" and count == 1):
        output = "{"
    content = {"type": "output_text", "text": output}
    if scenario == "refusal":
        content = {"type": "refusal", "refusal": "Authored contract refusal"}
    return {
        "id": f"emulator-response-{count}",
        "model": EMULATOR_MODEL,
        "usage": None,
        "status": "incomplete" if scenario == "truncated" else "completed",
        "output": [{"type": "message", "content": [content]}],
    }


def serve(host, port, root):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.state = State(root)
    print(json.dumps({"port": server.server_port, "mode": "emulator"}), flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8033)
    parser.add_argument("--root", type=Path, default=Path("data"))
    args = parser.parse_args()
    serve(args.host, args.port, args.root)


if __name__ == "__main__":
    main()
