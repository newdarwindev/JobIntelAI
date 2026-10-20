"""Границы новых команд: ошибки, повторное выполнение, ownership и сохранённые измерения."""

import json
import subprocess
from contextlib import contextmanager

import pytest

from scripts import task_emulator, task_experiment, tasks


def test_replay_preserves_failures_and_rescores_without_paid_calls(tmp_path):
    output = tmp_path / "replay"
    assert task_experiment.replay(output, "reviewed") == 1
    report = json.loads((output / "run/report.json").read_text())
    assert [r["summary"]["failed"] for r in report["results"]] == [5, 5, 5]
    assert json.loads((output / "reproduced.json").read_text()) == json.loads(
        (output / "run/scores.json").read_text()
    )
    original = (output / "run/report.json").read_bytes()
    with pytest.raises(FileExistsError):
        task_experiment.replay(output, "reviewed")
    assert (output / "run/report.json").read_bytes() == original


def test_replay_preflight_failure_does_not_claim_rescoring(tmp_path, monkeypatch):
    monkeypatch.setattr(task_experiment, "run", lambda *args: None)
    monkeypatch.setattr(
        task_experiment.subprocess, "run", lambda *args, **kw: subprocess.CompletedProcess([], 2)
    )
    assert task_experiment.replay(tmp_path / "rejected", "reviewed") == 2
    assert not (tmp_path / "rejected/reproduced.json").exists()


@pytest.mark.parametrize("endpoint", ["https://example.com", "http://127.0.0.1:9/secret"])
def test_emulator_control_rejects_nonlocal_or_extended_endpoints(monkeypatch, endpoint):
    record = {
        "status": "ready",
        "owner": "test",
        "configuration": {"mode": "emulator"},
        "endpoints": {"control_base": endpoint},
    }
    monkeypatch.setattr(task_emulator, "read_record", lambda project: record)
    monkeypatch.setattr(task_emulator, "resources", lambda *args: {"containers": ["owned"]})
    with pytest.raises(ValueError, match="endpoint"):
        task_emulator.control_base("jobintel-control")


def test_emulator_control_refuses_foreign_resources(monkeypatch):
    record = {"status": "ready", "owner": "test", "configuration": {"mode": "emulator"}}
    monkeypatch.setattr(task_emulator, "read_record", lambda project: record)
    monkeypatch.setattr(
        task_emulator,
        "resources",
        lambda project, *owner: {"containers": ["owned"] if owner else ["foreign"]},
    )
    with pytest.raises(ValueError, match="чужие"):
        task_emulator.control_base("jobintel-control")


def test_ui_gate_stops_before_publication_on_failed_suite(monkeypatch):
    commands = []

    def run(*command, **options):
        commands.append(command[-1])
        if command[-1] == "test:ui":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(tasks, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        tasks.ui_check()
    assert commands == [
        "test:recordings",
        "test:drafts",
        "test:mutations",
        "test:batches",
        "test:ui",
    ]


def test_offline_preparation_refuses_wrong_target(monkeypatch):
    monkeypatch.setattr(tasks.platform, "machine", lambda: "aarch64")
    with pytest.raises(ValueError, match="x86_64"):
        tasks.prepare_offline()


@pytest.mark.parametrize("fail", [False, True])
def test_catalogue_measurement_cleans_owned_database_after_command_outcome(monkeypatch, fail):
    from scripts import task_postgres

    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    states = []
    url = "postgresql+psycopg://jobintel:ci-only@127.0.0.1:5432/disposable"

    @contextmanager
    def database():
        states.append("started")
        try:
            yield None, url
        finally:
            states.append("cleaned")

    def run(*command, environment):
        assert command[-1] == "scripts.catalogue_benchmark"
        assert environment["TEST_DATABASE_URL"] == url
        assert environment["JOBINTEL_PROVIDER"] == "fixture"
        assert environment["JOBINTEL_CONFIGURATION"] == "fixture_normalized"
        if fail:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(task_postgres, "database", database)
    monkeypatch.setattr(tasks, "run", run)
    if fail:
        with pytest.raises(subprocess.CalledProcessError):
            tasks.catalogue_check()
    else:
        tasks.catalogue_check()
    assert states == ["started", "cleaned"]


def test_catalogue_measurement_preserves_explicit_database_ownership(monkeypatch):
    from scripts import task_postgres

    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://localhost/disposable")
    monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
    monkeypatch.setenv("JOBINTEL_CONFIGURATION", "openai_normalized_v1")
    calls = []

    def forbidden_database():
        raise AssertionError("must not claim configured database resources")

    monkeypatch.setattr(task_postgres, "database", forbidden_database)

    def run(*command, environment):
        calls.append(command)
        assert environment["TEST_DATABASE_URL"] == "postgresql+psycopg://localhost/disposable"
        assert environment["JOBINTEL_PROVIDER"] == "fixture"
        assert environment["JOBINTEL_CONFIGURATION"] == "fixture_normalized"

    monkeypatch.setattr(tasks, "run", run)
    tasks.catalogue_check()
    assert len(calls) == 1 and calls[0][-1] == "scripts.catalogue_benchmark"


def test_catalogue_measurement_uses_fixture_despite_hosted_environment(monkeypatch):
    from scripts.catalogue_benchmark import benchmark

    monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
    monkeypatch.setenv("JOBINTEL_CONFIGURATION", "openai_normalized_v1")
    rows = benchmark("sqlite", [1])
    assert len(rows) == 1
    assert rows[0]["legacy"]["returned_jobs"] == 1
    assert rows[0]["bounded"]["returned_jobs"] == 1
    assert rows[0]["bounded"]["select_statements"] == 2
    assert not rows[0]["bounded"]["selected_source_body_columns"]
