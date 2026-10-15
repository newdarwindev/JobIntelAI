"""Границы новых команд: ошибки, повторное выполнение, ownership и сохранённые измерения."""

import json
import subprocess

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
