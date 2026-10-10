"""Manage an isolated authored origin/proxy Compose stack with scoped TLS trust."""

import argparse
import json
import os
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from scripts.acquisition_fixtures.certificates import certificates

ROOT = Path(__file__).resolve().parents[1]


def compose(project, trust, *arguments, capture=False):
    command = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        "docker-compose.acquisition.yml",
        *arguments,
    ]
    return subprocess.run(
        command,
        env={**os.environ, "JOBINTEL_ACQUISITION_TRUST_DIR": str(trust)},
        check=True,
        text=True,
        capture_output=capture,
    )


def start(project, trust):
    certificates(trust)
    compose(project, trust, "up", "-d", "--build", "--wait", "--wait-timeout", "120")
    port = compose(project, trust, "port", "proxy", "8088", capture=True).stdout.strip()
    return {"proxy": f"http://{port}", "ca": trust / "ca.pem"}


def diagnostics(project, trust):
    result = {}
    for service, port in [("origin", 8080), ("proxy", 8088)]:
        code = (
            "import http.client; "
            f"c=http.client.HTTPConnection('127.0.0.1',{port},timeout=3); "
            "c.request('GET','/diagnostics'); print(c.getresponse().read().decode())"
        )
        output = compose(project, trust, "exec", "-T", service, "python", "-c", code, capture=True)
        result[service] = json.loads(output.stdout)
    return result


@contextmanager
def fixture_environment(directory):
    project = "jobintel-acquisition-" + uuid4().hex[:12]
    trust = Path(directory).resolve() / "trust"
    try:
        fixtures = start(project, trust)
        fixtures["project"] = project
        fixtures["diagnostics"] = lambda: diagnostics(project, trust)
        yield fixtures
    finally:
        compose(project, trust, "down", "--volumes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "status", "stop", "reset", "diagnostics"])
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    if Path.cwd() != ROOT or not re.fullmatch(
        r"jobintel-acquisition-[a-z0-9-]{1,40}", args.project
    ):
        parser.error("Run from repository root with --project jobintel-acquisition-<name>")
    trust = ROOT / "work/acquisition" / args.project / "trust"
    if args.action == "up":
        fixtures = start(args.project, trust)
        print(f"Proxy: {fixtures['proxy']}\nScoped CA: {fixtures['ca']}")
    elif args.action == "diagnostics":
        print(json.dumps(diagnostics(args.project, trust), indent=2))
    else:
        commands = {"status": ["ps", "--all"], "stop": ["down"], "reset": ["down", "--volumes"]}
        compose(args.project, trust, *commands[args.action])


if __name__ == "__main__":
    main()
