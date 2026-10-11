"""Lease boundary regressions: ownership, secret isolation, interruption and expiration."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import environment_lifecycle as lifecycle


@pytest.fixture
def registry(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle, "RECORDS", tmp_path)
    return tmp_path


def record(project="jobintel-test", *, persistent=False):
    return {
        "project": project,
        "owner": "authored-owner",
        "persistent": persistent,
        "expires_at": 1,
        "status": "ready",
    }


@pytest.mark.parametrize("kind", ["containers", "volumes", "networks"])
def test_preexisting_resources_cannot_be_claimed_or_removed(monkeypatch, registry, kind):
    existing = {"containers": [], "volumes": [], "networks": [], kind: ["preexisting"]}
    monkeypatch.setattr(lifecycle, "resources", lambda *_args: existing)
    with pytest.raises(ValueError, match="already exists"):
        lifecycle.Lease("jobintel-test")
    assert not lifecycle.record_path("jobintel-test").exists()


def test_stop_without_ownership_record_never_contacts_docker(monkeypatch, registry):
    def unexpected(*_args):
        pytest.fail("unmanaged resources must not be touched")

    monkeypatch.setattr(lifecycle, "docker", unexpected)
    assert lifecycle.stop("jobintel-test")["status"] == "not_managed"


@pytest.mark.parametrize("persistent", [True, False])
def test_stop_only_removes_labelled_resources_and_preserves_persistent_volumes(
    monkeypatch, registry, persistent
):
    lease = record(persistent=persistent)
    lifecycle.write_json(lifecycle.record_path(lease["project"]), lease)
    owned = {
        "containers": ["owned-container"],
        "networks": ["owned-network"],
        "volumes": ["owned-volume"],
    }

    def resources(project, owner):
        assert project == lease["project"] and owner == lease["owner"]
        return {k: v.copy() for k, v in owned.items()}

    monkeypatch.setattr(lifecycle, "resources", resources)
    removed = []

    def docker(kind, _command, *identifiers):
        removed.extend(identifiers)
        owned[{"rm": "containers", "network": "networks", "volume": "volumes"}[kind]] = []

    monkeypatch.setattr(lifecycle, "docker", docker)
    lifecycle.stop(lease["project"])
    assert "owned-container" in removed and "owned-network" in removed
    assert ("owned-volume" in removed) is not persistent
    before = removed.copy()
    lifecycle.stop(lease["project"])
    assert removed == before


def test_resume_refuses_foreign_resources_with_the_same_project(monkeypatch, registry):
    lease = record(persistent=True)
    lifecycle.write_json(lifecycle.record_path(lease["project"]), lease)

    def resources(_project, owner=None):
        return {
            "containers": [],
            "networks": [],
            "volumes": ["own"] if owner else ["own", "foreign"],
        }

    monkeypatch.setattr(lifecycle, "resources", resources)
    with pytest.raises(ValueError, match="outside this lease"):
        lifecycle.Lease(lease["project"], persistent=True, resume=True)


def test_config_diagnostics_never_serialize_inherited_secrets(monkeypatch, registry):
    monkeypatch.setattr(
        lifecycle, "resources", lambda *_args: {"containers": [], "volumes": [], "networks": []}
    )
    lease = lifecycle.Lease("jobintel-test", persistent=True)
    config = {
        "services": {"api": {"environment": {"secret": "private-value"}}},
        "networks": {"default": {}, "borrowed": {"external": True}},
        "volumes": {"pgdata": {}},
    }
    monkeypatch.setattr(
        lifecycle,
        "bounded_command",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps(config)),
    )
    lease.configure(["docker", "compose", "-f", "docker-compose.yml"], {"secret": "private-value"})
    assert "private-value" not in lease.path.read_text() + lease.overlay.read_text()
    overlay = json.loads(lease.overlay.read_text())
    assert "borrowed" not in overlay["networks"]
    assert overlay["services"]["api"]["labels"][lifecycle.LABEL] == lease.record["owner"]
    assert len(lease.record["compose_config_sha256"]) == 64


def test_expired_commands_never_start(monkeypatch, registry):
    lease = lifecycle.Lease.__new__(lifecycle.Lease)
    lease.record = record()
    with pytest.raises(TimeoutError, match="expired"):
        lease.remaining()


def test_expiry_watchdog_collects_and_removes_owned_resources(monkeypatch, registry):
    lease = record()
    lifecycle.write_json(lifecycle.record_path(lease["project"]), lease)
    stopped = []
    monkeypatch.setattr(lifecycle, "observed", lambda _record: {"containers": []})
    monkeypatch.setattr(lifecycle, "stop", lambda project: stopped.append(project))
    lifecycle.watch(lease["project"])
    assert stopped == [lease["project"]]
    assert lifecycle.read_record(lease["project"])["outcome"] == "expired"


def test_sigterm_raises_through_finally_and_restores_handler():
    previous = signal.getsignal(signal.SIGTERM)
    with pytest.raises(KeyboardInterrupt), lifecycle.interruption_guard():
        os.kill(os.getpid(), signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == previous


def assert_stopped(pid):
    path = Path(f"/proc/{pid}/stat")
    deadline = time.monotonic() + 3
    while path.exists() and path.read_text().split()[2] != "Z":
        assert time.monotonic() < deadline, "command descendant is still running"
        time.sleep(0.01)


def test_timeout_terminates_the_command_process_group(tmp_path):
    child = tmp_path / "child.pid"
    code = (
        "import subprocess,time; from pathlib import Path; p=subprocess.Popen(['sleep','60']); Path("
        + repr(str(child))
        + ").write_text(str(p.pid)); time.sleep(60)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        lifecycle.bounded_command(
            [sys.executable, "-c", code], environment=os.environ, timeout=1, capture=True
        )
    pid = int(child.read_text())
    assert_stopped(pid)


def test_failed_diagnostic_collector_does_not_prevent_other_diagnostics():
    def failed():
        raise ValueError("private-value-must-not-be-published")

    result = lifecycle.collect_diagnostics({"failed": failed, "healthy": lambda: {"count": 3}})
    assert result == {
        "failed": {"unavailable": True, "failure_kind": "ValueError"},
        "healthy": {"count": 3},
    }


def test_command_timeout_kills_descendant_even_after_leader_exits(tmp_path):
    child = tmp_path / "child.pid"
    child_code = (
        "import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path("
        + repr(str(child))
        + ").write_text(str(os.getpid())); time.sleep(60)"
    )
    code = (
        "import subprocess,time; subprocess.Popen(["
        + repr(sys.executable)
        + ",'-c',"
        + repr(child_code)
        + "]); time.sleep(60)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        lifecycle.bounded_command(
            [sys.executable, "-c", code], environment=os.environ, timeout=1, capture=True
        )
    pid = int(child.read_text())
    assert_stopped(pid)


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_network_measurement_retains_partial_checkpoint_and_actual_attempts(monkeypatch, error):
    from scripts import network_experiments

    def failed_transport(_payload):
        raise error("authored failure")

    provider = SimpleNamespace(
        mode="emulator", transport=SimpleNamespace(complete=failed_transport)
    )
    monkeypatch.setattr(
        network_experiments, "selected_experiment_provider", lambda *_args: provider
    )

    def run(provider, _corpus, _spec, *, checkpoint):
        checkpoint({"records": [{"status": "active", "prediction": None, "usage": None}]})
        provider.transport.complete({"model": "authored", "input": "public fixture"})

    monkeypatch.setattr(network_experiments, "run_experiment", run)
    observed = {}
    with pytest.raises(error):
        network_experiments.measure("emulator", on_update=observed.update)
    assert observed["status"] == "failed" and observed["failure_kind"] == error.__name__
    assert observed["observed_http_attempts"] == 1 and len(observed["request_sha256"]) == 1
    assert observed["report"]["records"] == [
        {"status": "active", "prediction": None, "usage": None}
    ]
    assert observed["scores"] is observed["rescore_without_requests"] is None
