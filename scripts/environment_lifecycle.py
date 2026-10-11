"""Owned Compose leases, bounded commands and cleanup independent of provider configuration."""

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "work/environments"
LABEL = "io.jobintel.environment"
PROJECT = "com.docker.compose.project"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def record_path(project):
    if not re.fullmatch(r"jobintel-[a-z0-9][a-z0-9-]{0,64}", project):
        raise ValueError("Use a scoped jobintel- project name")
    return RECORDS / project / "lease.json"


def read_record(project):
    path = record_path(project)
    return json.loads(path.read_text()) if path.is_file() else None


def docker(*arguments):
    return subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, check=True, timeout=60
    ).stdout.strip()


def resources(project, owner=None):
    filters = ["--filter", f"label={PROJECT}={project}"]
    if owner:
        filters += ["--filter", f"label={LABEL}={owner}"]
    return {
        "containers": docker("ps", "-aq", *filters).split(),
        "volumes": docker("volume", "ls", "-q", *filters).split(),
        "networks": docker("network", "ls", "-q", *filters).split(),
    }


def observed(record):
    owned = resources(record["project"], record["owner"])
    containers = []
    for identifier in owned["containers"]:
        item = json.loads(docker("inspect", "--format", "{{json .State}}", identifier))
        containers.append(
            {
                "service": docker(
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "com.docker.compose.service"}}',
                    identifier,
                ),
                "id": identifier,
                "status": item["Status"],
                "exit_code": item["ExitCode"],
                "health": item.get("Health", {}).get("Status"),
            }
        )
    return {"resources": owned, "containers": containers}


def stop(project, *, reset=False):
    path = record_path(project)
    if not path.is_file():
        return {"project": project, "status": "not_managed"}
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return stop_locked(project, reset=reset)


def stop_locked(project, *, reset=False):
    record = read_record(project)
    if record is None:
        return {"project": project, "status": "not_managed"}
    owned = resources(project, record["owner"])
    if "diagnostics" not in record:
        record["diagnostics"] = collect_diagnostics({"compose": lambda: observed(record)})
        record.setdefault("outcome", "external_stop")
    if owned["containers"]:
        docker("rm", "--force", *owned["containers"])
    if owned["networks"]:
        docker("network", "rm", *owned["networks"])
    if (reset or not record["persistent"]) and owned["volumes"]:
        docker("volume", "rm", *owned["volumes"])
    record.update(status="stopped", cleanup=resources(project, record["owner"]))
    write_json(record_path(project), record)
    directory = ROOT / "local_data/environments" / project
    marker = directory / "owner"
    if (
        (reset or not record["persistent"])
        and marker.is_file()
        and marker.read_text() == record["owner"]
    ):
        shutil.rmtree(directory)
    return record


@contextmanager
def interruption_guard():
    previous = signal.getsignal(signal.SIGTERM)

    def interrupt(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def terminate_group(process):
    for kind in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, kind)
        except ProcessLookupError:
            pass
        if kind == signal.SIGTERM:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    process.wait(timeout=5)


def bounded_command(command, *, environment, timeout, capture=False, check=True):
    process = subprocess.Popen(
        command,
        env=environment,
        text=True,
        start_new_session=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    try:
        output, errors = process.communicate(timeout=timeout)
    except BaseException:
        terminate_group(process)
        raise
    result = subprocess.CompletedProcess(command, process.returncode, output, errors)
    if check:
        result.check_returncode()
    return result


def collect_diagnostics(collectors):
    result = {}
    for name, collector in collectors.items():
        try:
            result[name] = collector()
        except Exception as error:
            result[name] = {"unavailable": True, "failure_kind": type(error).__name__}
    return result


class Lease:
    """Only fresh or explicitly resumed, labelled projects belong to this lease."""

    def __init__(self, project, *, persistent=False, lifetime=3600, resume=False, expires_at=None):
        if not 30 <= lifetime <= 7200:
            raise ValueError("Lifetime must be 30..7200 seconds")
        self.path = record_path(project)
        self.overlay = self.path.parent / "ownership.json"
        self.collectors = {}
        self.detached = False
        existing = read_record(project)
        if resume:
            if not existing or not existing["persistent"]:
                raise ValueError("Only a recorded persistent session can be resumed")
            self.record = existing
            self.assert_owned()
        else:
            if existing or any(resources(project).values()):
                raise ValueError("Project already exists; choose a fresh name")
            self.path.parent.mkdir(parents=True, exist_ok=False)
            from jobintel.experiments import code_provenance

            self.record = {
                "version": 1,
                "project": project,
                "owner": uuid4().hex,
                "persistent": persistent,
                "expires_at": None if persistent else (expires_at or time.time() + lifetime),
                "code_provenance": code_provenance(),
                "status": "starting",
                "endpoints": {},
            }
        self.save()
        self.watchdog = None
        if not persistent and not resume:
            self.watchdog = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "scripts.environment_lifecycle",
                    "watch",
                    "--project",
                    project,
                ],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

    def save(self):
        write_json(self.path, self.record)

    def assert_owned(self):
        all_resources = resources(self.record["project"])
        owned = resources(self.record["project"], self.record["owner"])
        if all_resources != owned:
            raise ValueError("Project contains resources outside this lease")

    def configure(self, prefix, environment):
        self.prefix, self.environment = prefix, environment
        config = bounded_command(
            [*prefix, "config", "--format", "json"],
            environment=environment,
            timeout=self.remaining(),
            capture=True,
        )
        document = json.loads(config.stdout)
        self.record["compose_config_sha256"] = sha256(config.stdout.encode()).hexdigest()
        self.record["compose_files"] = [str(item) for item in prefix if str(item).endswith(".yml")]
        self.save()
        label = {LABEL: self.record["owner"]}
        overlay = {
            kind: {
                name: {"labels": label}
                for name, value in document.get(kind, {}).items()
                if not value.get("external")
            }
            for kind in ("services", "volumes", "networks")
        }
        write_json(self.overlay, overlay)

    def remaining(self):
        expiry = self.record["expires_at"]
        remaining = expiry - time.time() if expiry else 7200
        if remaining <= 0:
            raise TimeoutError("Environment lease expired")
        return remaining

    def command(self, *arguments, capture=False, check=True):
        return bounded_command(
            [*self.prefix, "-f", str(self.overlay), *arguments],
            environment=self.environment,
            timeout=self.remaining(),
            capture=capture,
            check=check,
        )

    def ready(self, endpoints):
        self.record.update(status="ready", endpoints=endpoints)
        self.save()

    def diagnostics(self):
        return collect_diagnostics({"compose": lambda: observed(self.record), **self.collectors})

    def close(self, error=None):
        if self.detached:
            return None
        self.record.update(
            outcome="completed" if error is None else type(error).__name__,
            diagnostics=self.diagnostics(),
        )
        self.save()
        result = stop(self.record["project"])
        if self.watchdog:
            self.watchdog.terminate()
            self.watchdog.wait(timeout=5)
        return result

    def __enter__(self):
        return self

    def __exit__(self, _kind, error, _traceback):
        self.close(error)


def watch(project):
    while (record := read_record(project)) and record["status"] != "stopped":
        if time.time() >= record["expires_at"]:
            record.update(
                outcome="expired",
                diagnostics=collect_diagnostics({"compose": lambda: observed(record)}),
            )
            write_json(record_path(project), record)
            try:
                stop(project)
                return
            except (OSError, subprocess.SubprocessError):
                # An owned network can still have a dependent API awaiting its own expiry.
                time.sleep(5)
                continue
        time.sleep(min(5, max(0.1, record["expires_at"] - time.time())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["watch", "reap"])
    parser.add_argument("--project")
    parser.add_argument("--all-disposable", action="store_true")
    args = parser.parse_args()
    if args.action == "watch":
        watch(args.project)
    else:
        records = [json.loads(path.read_text()) for path in RECORDS.glob("*/lease.json")]
        records.sort(key=lambda record: bool(record.get("configuration")), reverse=True)
        failures = 0
        for record in records:
            if not record["persistent"] and (
                args.all_disposable or time.time() >= record["expires_at"]
            ):
                try:
                    stop(record["project"])
                except (OSError, subprocess.SubprocessError):
                    failures += 1
        if failures:
            raise SystemExit(f"Could not clean {failures} recorded disposable leases")


if __name__ == "__main__":
    main()
