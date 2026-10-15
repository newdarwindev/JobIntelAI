"""Полные Python-проверки в собственной временной PostgreSQL либо TEST_DATABASE_URL."""

import argparse
import json
import os
import sys
from contextlib import contextmanager
from uuid import uuid4

from scripts.environment_lifecycle import Lease, bounded_command, interruption_guard


@contextmanager
def database(*, project=None, lifetime=1800):
    project = project or "jobintel-check-" + uuid4().hex[:12]
    with interruption_guard(), Lease(project, lifetime=lifetime) as lease:
        document = {
            "services": {
                "db": {
                    "image": "postgres:16-alpine",
                    "environment": {
                        "POSTGRES_USER": "jobintel",
                        "POSTGRES_PASSWORD": "ci-only",
                        "POSTGRES_DB": "jobintel_test",
                    },
                    "ports": ["127.0.0.1::5432"],
                    "volumes": ["database:/var/lib/postgresql/data"],
                    "healthcheck": {
                        "test": ["CMD", "pg_isready", "-U", "jobintel", "-d", "jobintel_test"],
                        "interval": "1s",
                        "timeout": "2s",
                        "retries": 60,
                    },
                }
            },
            "volumes": {"database": {}},
        }
        compose = lease.path.parent / "postgres.yml"
        compose.write_text(json.dumps(document))
        lease.configure(["docker", "compose", "-p", project, "-f", str(compose)], dict(os.environ))
        lease.command("up", "-d", "--wait", "--wait-timeout", "90")
        address = lease.command("port", "db", "5432", capture=True).stdout.strip()
        if not address.startswith("127.0.0.1:") or not address[10:].isdigit():
            raise ValueError("PostgreSQL должен иметь обнаруженный loopback-порт")
        url = f"postgresql+psycopg://jobintel:ci-only@{address}/jobintel_test"
        lease.ready({"database": "postgresql", "address": address})
        yield lease, url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project", help="Новый jobintel- проект; существующий использовать нельзя"
    )
    parser.add_argument("--lifetime", type=int, default=1800)
    parser.add_argument("--junitxml", default="work/ci/junit.xml")
    parser.add_argument("--evidence-dir", default="work/ci")
    args = parser.parse_args()
    command = [
        sys.executable,
        "scripts/check.py",
        "--require-postgres",
        "--junitxml",
        args.junitxml,
        "--evidence-dir",
        args.evidence_dir,
    ]
    if os.getenv("TEST_DATABASE_URL"):
        result = bounded_command(
            command, environment=dict(os.environ), timeout=args.lifetime, check=False
        )
    else:
        with database(project=args.project, lifetime=args.lifetime) as (lease, url):
            result = bounded_command(
                command,
                environment={**os.environ, "TEST_DATABASE_URL": url},
                timeout=lease.remaining(),
                check=False,
            )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
