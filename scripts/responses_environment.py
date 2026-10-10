"""Own a scoped development emulator container, including browser cleanup."""

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from jobintel.openai_transport import EMULATOR_TOKEN


def compose(project, *arguments, capture=False, ca_bundle=None, api_port=18083):
    command = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.responses.yml",
        "--profile",
        "contract-test",
    ]
    if ca_bundle:
        command += ["-f", "docker-compose.proxy.yml", "-f", "docker-compose.responses-proxy.yml"]
    environment = {**os.environ, "JOBINTEL_API_PORT": str(api_port), "JOBINTEL_OPENAI_TIMEOUT": "1"}
    if ca_bundle:
        environment["JOBINTEL_CA_BUNDLE"] = str(ca_bundle)
    return subprocess.run(
        [*command, *arguments], env=environment, check=True, capture_output=capture, text=True
    )


def request(base, path, payload=None):
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.request(
            "GET" if payload is None else "POST",
            base + path,
            json=payload,
            headers={"Authorization": f"Bearer {EMULATOR_TOKEN}"},
        )
    response.raise_for_status()
    return response.json()


def base_url(project, ca_bundle=None):
    port = compose(
        project, "port", "responses-emulator", "8033", capture=True, ca_bundle=ca_bundle
    ).stdout.strip()
    return f"http://{port}"


@contextmanager
def emulator_environment(*, api=False, project=None, ca_bundle=None, api_port=18083):
    project = project or "jobintel-responses-" + uuid4().hex[:12]
    options = {"ca_bundle": ca_bundle, "api_port": api_port}
    try:
        services = [] if api else ["responses-emulator"]
        compose(
            project, "up", "-d", "--build", "--wait", "--wait-timeout", "120", *services, **options
        )
        base = base_url(project, ca_bundle)
        yield {
            "base": base,
            "project": project,
            "diagnostics": lambda: request(base, "/diagnostics"),
        }
    finally:
        compose(project, "down", "--volumes", **options)


def write_evidence(path, evidence):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n")
