"""Provision loopback-only disposable runs or explicitly persistent developer sessions."""

import argparse
import json
import os
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from scripts import runtime
from scripts.environment_lifecycle import (
    ROOT,
    Lease,
    bounded_command,
    interruption_guard,
    observed,
    read_record,
    stop,
)

MODES = {"fixture": "dev", "emulator": "contract-test", "local": "local-inference"}


class Environment:
    def __init__(
        self,
        mode="fixture",
        *,
        acquisition=False,
        fixtures=None,
        project=None,
        persistent=False,
        lifetime=3600,
        ca_bundle=None,
        offline=False,
        resume=False,
    ):
        self.mode, self.acquisition, self.fixtures = mode, acquisition, fixtures
        self.project = project or f"jobintel-run-{mode}-{uuid4().hex[:12]}"
        self.options = {"persistent": persistent, "lifetime": lifetime, "resume": resume}
        self.ca_bundle = ca_bundle or (
            "/etc/ssl/certs/ca-certificates.crt" if os.getenv("HTTPS_PROXY") else None
        )
        self.offline = offline
        self.stack = ExitStack()

    def provision(self):
        self.options["expires_at"] = time.time() + self.options["lifetime"]
        if self.acquisition:
            from scripts.acquisition_environment import managed_fixtures

            self.fixtures = self.stack.enter_context(
                managed_fixtures(
                    self.project + "-acq",
                    persistent=self.options["persistent"],
                    lifetime=self.options["lifetime"],
                    resume=self.options["resume"],
                    expires_at=self.options["expires_at"],
                )
            )
        self.lease = self.stack.enter_context(Lease(self.project, **self.options))
        args = SimpleNamespace(
            project=self.project,
            mode=MODES[self.mode],
            port=0,
            offline=self.offline,
            ca_bundle=self.ca_bundle,
        )
        overrides = {
            "JOBINTEL_POSTGRES_PASSWORD": "environment-only",
            "JOBINTEL_COMPOSE_DATABASE_URL": "postgresql+psycopg://jobintel:environment-only@db/jobintel",
            "JOBINTEL_CONFIGURATION": {
                "fixture": "fixture_normalized",
                "emulator": "openai_normalized_v1",
                "local": "local_normalized_v1",
            }[self.mode],
            "JOBINTEL_PROVIDER": "fixture",
            "JOBINTEL_OPENAI_TIMEOUT": "1",
            "JOBINTEL_LOCAL_TIMEOUT": "120",
            "JOBINTEL_RESPONSES_PORT": "0",
        }
        environment = runtime.compose_environment(args, overrides=overrides)
        prefix = runtime.compose_command(args, configured=True)
        if self.fixtures:
            prefix += ["-f", "docker-compose.browser.yml"]
            environment.update(
                JOBINTEL_BROWSER_TRUST_DIR=str(self.fixtures["ca"].parent),
                JOBINTEL_BROWSER_FIXTURE_NETWORK=self.fixtures["project"] + "_control",
            )
        self.lease.record["configuration"] = {
            "mode": self.mode,
            "acquisition": self.acquisition,
            "ca_bundle": self.ca_bundle,
            "offline": self.offline,
        }
        self.lease.configure(prefix, environment)
        self.start()
        self.info = {
            "base": self.service_url("api", 8000),
            "project": self.project,
            "mode": self.mode,
            "database": "postgresql",
            "demo": False,
            "inference": self.mode == "local",
            "lease": str(self.lease.path),
            "expires_at": self.lease.record["expires_at"],
        }
        if self.mode == "emulator":
            from scripts.responses_environment import request

            self.info["control_base"] = self.service_url("responses-emulator", 8033)
            self.lease.collectors["responses"] = lambda: request(
                self.info["control_base"], "/diagnostics"
            )
        if self.fixtures:
            self.lease.collectors["acquisition"] = self.fixtures["diagnostics"]
        self.lease.ready(self.info)
        return self

    def start(self, *, no_build=False):
        if self.mode == "local":
            preparation = [
                sys.executable,
                "-m",
                "scripts.local_model",
                "--cache",
                self.lease.environment["JOBINTEL_LOCAL_MODEL_CACHE"],
            ]
            if self.offline:
                preparation.append("--offline")
            bounded_command(
                preparation, environment=self.lease.environment, timeout=self.lease.remaining()
            )
        self.command(
            "up", "-d", "--no-build" if no_build else "--build", "--wait", "--wait-timeout", "180"
        )

        if hasattr(self, "info"):
            self.info["base"] = self.service_url("api", 8000)
            if self.mode == "emulator":
                self.info["control_base"] = self.service_url("responses-emulator", 8033)
            self.lease.ready(self.info)

    def command(self, *arguments, **options):
        return self.lease.command(*arguments, **options)

    def service_url(self, service, port):
        address = self.command("port", service, str(port), capture=True).stdout.strip()
        if not address.startswith("127.0.0.1:"):
            raise ValueError("Environment endpoint must use loopback")
        return "http://" + address

    def suspend(self):
        self.command("down")

    def __enter__(self):
        self.stack.enter_context(interruption_guard())
        try:
            return self.provision()
        except BaseException:
            self.stack.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *exception):
        return self.stack.__exit__(*exception)


def stop_session(project, *, reset=False):
    record = read_record(project)
    result = stop(project, reset=reset)
    if record and record.get("configuration", {}).get("acquisition"):
        stop(project + "-acq", reset=reset)
    return result


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "up", "start", "status", "stop", "reset"])
    parser.add_argument("--mode", choices=MODES, default="emulator")
    parser.add_argument("--acquisition", action="store_true")
    parser.add_argument("--project")
    parser.add_argument("--persistent", action="store_true")
    parser.add_argument("--lifetime", type=int, default=3600)
    parser.add_argument("--ca-bundle")
    parser.add_argument("--offline", action="store_true")
    supplied = sys.argv[1:]
    separator = supplied.index("--") if "--" in supplied else len(supplied)
    args = parser.parse_args(supplied[:separator])
    args.command = supplied[separator + 1 :]
    if Path.cwd() != ROOT:
        parser.error("Run from the repository root")
    if args.action == "up" and not args.persistent:
        parser.error(
            "Background up requires --persistent; use run for a bounded disposable session"
        )
    if args.action == "run" and (args.persistent or not args.command):
        parser.error("Use run [options] -- command for a disposable session")
    if args.action in {"start", "status", "stop", "reset"} and not args.project:
        parser.error("This action requires --project")
    return args


def main():
    args = arguments()
    if args.action in {"status", "stop", "reset"}:
        record = read_record(args.project)
        if args.action == "status":
            result = (
                {"lease": record, "observed": observed(record)}
                if record
                else {"status": "not_managed"}
            )
        else:
            result = stop_session(args.project, reset=args.action == "reset")
        print(json.dumps(result, indent=2))
        return
    if args.action == "start":
        record = read_record(args.project)
        if not record or not record["persistent"]:
            raise SystemExit("Only a recorded persistent session can be started")
        options = record["configuration"]
        environment = Environment(project=args.project, persistent=True, resume=True, **options)
    else:
        environment = Environment(
            args.mode,
            project=args.project,
            acquisition=args.acquisition,
            persistent=args.persistent,
            lifetime=args.lifetime,
            ca_bundle=args.ca_bundle,
            offline=args.offline,
        )
    with interruption_guard(), environment as session:
        print(json.dumps(session.info), flush=True)
        if args.action in {"up", "start"}:
            session.lease.detached = True
            if session.acquisition:
                session.fixtures["_lease"].detached = True
            return
        command = args.command[1:] if args.command[0] == "--" else args.command
        result = bounded_command(
            command,
            timeout=session.lease.remaining(),
            check=False,
            environment={**os.environ, "JOBINTEL_ENVIRONMENT": json.dumps(session.info)},
        )
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
