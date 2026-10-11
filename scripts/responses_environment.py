"""Own a scoped development emulator container, including browser cleanup."""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from jobintel.openai_transport import EMULATOR_TOKEN
from scripts.environment_lifecycle import Lease, bounded_command, read_record, record_path


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
    if read_record(project):
        command += ["-f", str(record_path(project).parent / "ownership.json")]
    return bounded_command(
        [*command, *arguments], environment=environment, timeout=180, capture=capture
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


def runtime_control(project, action, ca_bundle, api_port):
    command = [sys.executable, "scripts/runtime.py", action, "--project", project]
    if action == "up":
        command += ["--mode", "contract-test", "--port", str(api_port)]
        if ca_bundle:
            command += ["--ca-bundle", str(ca_bundle)]
    subprocess.run(command, env={**os.environ, "JOBINTEL_OPENAI_TIMEOUT": "1"}, check=True)


@contextmanager
def emulator_environment(*, api=False, project=None, ca_bundle=None, api_port=0):
    project = project or "jobintel-responses-" + uuid4().hex[:12]
    if api:
        from scripts.environment import Environment

        with Environment("emulator", project=project, ca_bundle=ca_bundle) as session:
            fixtures = {
                "base": session.info["control_base"],
                "project": project,
                "api_base": session.info["base"],
            }
            fixtures["diagnostics"] = lambda: request(fixtures["base"], "/diagnostics")
            yield fixtures
        return
    with Lease(project) as lease:
        prefix = [
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
        environment = {**os.environ, "JOBINTEL_API_PORT": "0", "JOBINTEL_RESPONSES_PORT": "0"}
        if ca_bundle:
            prefix += ["-f", "docker-compose.proxy.yml", "-f", "docker-compose.responses-proxy.yml"]
            environment["JOBINTEL_CA_BUNDLE"] = str(ca_bundle)
        lease.configure(prefix, environment)
        lease.command(
            "up", "-d", "--build", "--wait", "--wait-timeout", "120", "responses-emulator"
        )
        fixtures = {"base": base_url(project, ca_bundle), "project": project}
        fixtures["diagnostics"] = lambda: request(fixtures["base"], "/diagnostics")
        lease.collectors["responses"] = fixtures["diagnostics"]
        lease.ready({"responses": fixtures["base"]})
        yield fixtures


def write_evidence(path, evidence):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n")
