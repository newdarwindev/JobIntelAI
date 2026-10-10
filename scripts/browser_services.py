"""Scoped normal PostgreSQL APIs for fixture, HTTP contract and actual CPU browser journeys."""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from jobintel.experiments import code_provenance
from scripts import runtime
from scripts.responses_environment import write_evidence
from scripts.runtime_smoke import require_fresh_projects

MODES = {"fixture": "dev", "emulator": "contract-test", "local": "local-inference"}


def command(args, *arguments, capture=False):
    return subprocess.run(
        [
            *runtime.compose_command(args, configured=True),
            "-f",
            "docker-compose.browser.yml",
            *arguments,
        ],
        env=args.environment,
        check=True,
        text=True,
        capture_output=capture,
    )


def service_url(args, service, port):
    address = command(args, "port", service, str(port), capture=True).stdout.strip()
    return "http://" + address


@contextmanager
def normal_api(mode, fixtures):
    project = "jobintel-browser-" + mode + "-" + uuid4().hex[:12]
    require_fresh_projects(project)
    args = SimpleNamespace(
        project=project,
        mode=MODES[mode],
        port=0,
        offline=False,
        ca_bundle="/etc/ssl/certs/ca-certificates.crt" if os.getenv("HTTPS_PROXY") else None,
    )
    overrides = {
        "JOBINTEL_POSTGRES_PASSWORD": "browser-only",
        "JOBINTEL_COMPOSE_DATABASE_URL": "postgresql+psycopg://jobintel:browser-only@db/jobintel",
        "JOBINTEL_OPENAI_TIMEOUT": "1",
        "JOBINTEL_LOCAL_TIMEOUT": "120",
    }
    if mode == "fixture":
        overrides.update(JOBINTEL_PROVIDER="fixture", JOBINTEL_CONFIGURATION="fixture_normalized")
    args.environment = {
        **runtime.compose_environment(args, overrides=overrides),
        "JOBINTEL_BROWSER_TRUST_DIR": str(fixtures["ca"].parent),
        "JOBINTEL_BROWSER_FIXTURE_NETWORK": fixtures["project"] + "_control",
    }
    if mode == "local":
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.local_model",
                "--cache",
                args.environment["JOBINTEL_LOCAL_MODEL_CACHE"],
            ],
            env=args.environment,
            check=True,
        )
    try:
        command(args, "up", "-d", "--build", "--wait", "--wait-timeout", "180")
        info = {
            "base": service_url(args, "api", 8000),
            "project": project,
            "mode": mode,
            "database": "postgresql",
            "demo": False,
            "inference": mode == "local",
        }
        if mode == "emulator":
            info["control_base"] = service_url(args, "responses-emulator", 8033)
        if mode == "local":
            evaluated = command(
                args, "exec", "-T", "api", "python", "-m", "scripts.local_evaluation", capture=True
            )
            report = json.loads(evaluated.stdout)
            report["code_provenance"] = code_provenance()
            write_evidence("work/persistent-browser-local-evaluation.json", report)
            info["evaluation_run_id"] = report["evaluation_run_id"]
        yield info
    finally:
        command(args, "down", "--volumes")
