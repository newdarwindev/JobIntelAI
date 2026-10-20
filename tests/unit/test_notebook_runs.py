"""EXEC-01 through EXEC-05: notebook integrity and no-fallback boundaries."""

import copy
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from jobintel import notebook_runs
from jobintel.experiment_corpus import digest, read_json, write_json
from jobintel.experiments import ExperimentSpec
from jobintel.local_model import MODEL
from jobintel.notebook_artifacts import seal_manifest, verify_manifest
from jobintel.notebook_cli import main
from jobintel.notebook_contracts import NotebookRejected, NotebookRequest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def request(tmp_path, **changes):
    return NotebookRequest(output=tmp_path / "run", **changes)


def test_exec01_fixture_run_is_database_and_secret_independent(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBINTEL_DATABASE_URL", "postgresql://must-not-connect/private")
    monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "private-sentinel-never-read")
    monkeypatch.setenv("JOBINTEL_FIXTURE_ROOT", str(tmp_path / "private-inputs"))
    value = request(tmp_path)
    planned = notebook_runs.plan_notebook(value, data_root=DATA)
    assert planned.status == "planned" and not value.output.exists()
    manifest = notebook_runs.run_notebook(value, data_root=DATA)
    assert manifest.status == "succeeded"
    assert manifest.mode == "fixture" and manifest.evidence_mode == "fake"
    assert manifest.parameters_sha256 == planned.parameters_sha256
    report = read_json(value.output / "report.json")
    assert [(r["summary"]["succeeded"], r["summary"]["failed"]) for r in report["results"]] == [
        (20, 0),
        (20, 0),
        (20, 0),
    ]
    assert all(r["summary"]["tokens"] is None for r in report["results"])
    assert "private-sentinel" not in manifest.model_dump_json()
    assert verify_manifest(value.output / "manifest.json") == manifest


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "training", "split": "train", "max_steps": 1},
        {"spec": ExperimentSpec(max_calls=1)},
        {"spec": ExperimentSpec(max_input_tokens=1)},
        {"spec": ExperimentSpec(model="unknown-model")},
        {"corpus_sha256": "0" * 64},
        {"model_weights_sha256": "0" * 64},
        {"split": "test"},
        {"cases": ["unknown"]},
        {"mode": "local-inference", "endpoint": "https://api.openai.com/v1/chat/completions"},
    ],
)
def test_exec02_rejections_precede_provider_and_outputs(tmp_path, monkeypatch, change):
    def forbidden(*args, **kwargs):
        raise AssertionError("provider allocated before preflight")

    monkeypatch.setattr(notebook_runs, "FakeExperimentProvider", forbidden)
    monkeypatch.setattr(notebook_runs, "HttpLocalTransport", forbidden)
    value = request(tmp_path, **change)
    with pytest.raises(ValueError):
        notebook_runs.run_notebook(value, data_root=DATA)
    assert not value.output.exists()


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "local"},
        {"mode": "saved-report"},
        {"report": Path("unexpected.json")},
        {"endpoint": "http://127.0.0.1:1/v1/chat/completions"},
        {"format_version": 2},
        {"max_steps": 1},
        {"unknown": "private-sentinel"},
    ],
)
def test_exec02_typed_mode_contract(tmp_path, change):
    with pytest.raises(ValidationError):
        request(tmp_path, **change)


@pytest.mark.parametrize(
    "path,dataset,split",
    [
        ("results/experiments/fake/report.json", "fixture", "regression"),
        ("results/experiments/reviewed-fake/report.json", "reviewed", "development"),
        ("results/network-experiments/local/report.json", "reviewed", "development"),
    ],
)
def test_exec03_saved_legacy_reports_without_provider(tmp_path, monkeypatch, path, dataset, split):
    def forbidden(*args, **kwargs):
        raise AssertionError("saved rescoring invoked a provider")

    monkeypatch.setattr(notebook_runs, "FakeExperimentProvider", forbidden)
    monkeypatch.setattr(notebook_runs, "HttpLocalTransport", forbidden)
    source = ROOT / path
    original = source.read_bytes()
    value = request(tmp_path, mode="saved-report", report=source, dataset=dataset, split=split)
    result = notebook_runs.run_notebook(value, data_root=DATA)
    expected = read_json(source.with_name("scores.json"))
    assert read_json(value.output / "scores.json") == expected
    assert source.read_bytes() == original
    assert result.mode == "saved-report"
    assert result.evidence_mode == read_json(source)["mode"]
    assert not (value.output / "report.json").exists()
    comparison = (value.output / "comparison.md").read_text()
    assert result.input_sha256 in comparison
    assert str(source) not in comparison
    for target in re.findall(r"\]\(([^)]+)\)", comparison):
        assert (value.output / target).is_file(), target
    assert verify_manifest(value.output / "manifest.json") == result


@pytest.mark.parametrize("change", ["source", "config", "prediction", "version", "report_hash"])
def test_exec03_corruption_refused_without_outputs(tmp_path, change):
    report = copy.deepcopy(read_json(ROOT / "results/experiments/fake/report.json"))
    if change == "source":
        report["corpus"]["cases"][0]["text"] += " changed"
    elif change == "config":
        report["spec"]["model"] = "wrong"
    elif change == "prediction":
        report["results"][0]["records"][0]["prediction"]["requirements"] = []
    elif change == "version":
        report["format_version"] = 99
    source = tmp_path / "input.json"
    write_json(source, report)
    value = request(
        tmp_path,
        mode="saved-report",
        report=source,
        report_sha256="0" * 64 if change == "report_hash" else None,
    )
    with pytest.raises(ValueError):
        notebook_runs.run_notebook(value, data_root=DATA)
    assert not value.output.exists()


def test_exec03_artifact_integrity_and_confinement(tmp_path):
    value = request(tmp_path)
    manifest = notebook_runs.run_notebook(value, data_root=DATA)
    score_path = value.output / "scores.json"
    original = score_path.read_bytes()
    score_path.write_bytes(original + b" ")
    with pytest.raises(NotebookRejected, match="artifact_checksum"):
        verify_manifest(value.output / "manifest.json")
    score_path.write_bytes(original)
    envelope = manifest.model_dump(mode="json", exclude={"manifest_sha256"})
    envelope["artifacts"][0]["path"] = "../outside.json"
    forged = seal_manifest(envelope)
    (value.output / "manifest.json").write_text(forged.model_dump_json())
    with pytest.raises(NotebookRejected, match="artifact_path"):
        verify_manifest(value.output / "manifest.json")


def test_exec04_output_collision_and_cli_equivalence(tmp_path, capsys):
    value = request(tmp_path)
    result = notebook_runs.run_notebook(value, data_root=DATA)
    original = (value.output / "manifest.json").read_bytes()
    with pytest.raises(NotebookRejected, match="output_exists"):
        notebook_runs.run_notebook(value, data_root=DATA)
    assert (value.output / "manifest.json").read_bytes() == original
    config = tmp_path / "config.json"
    write_json(config, value.model_dump(mode="json"))
    assert (
        main(
            [
                "run",
                "--config",
                str(config),
                "--output",
                str(tmp_path / "cli"),
                "--data-root",
                str(DATA),
            ]
        )
        == 0
    )
    cli = json.loads(capsys.readouterr().out)
    assert cli["parameters"] == result.parameters
    assert cli["parameters_sha256"] == result.parameters_sha256


def test_exec05_safe_cli_preflight_error(tmp_path, capsys):
    config = tmp_path / "config.json"
    write_json(config, {"output": str(tmp_path / "run"), "provider": "private-sentinel"})
    with pytest.raises(SystemExit) as error:
        main(["run", "--config", str(config)])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "invalid_input" in captured.err
    assert "private-sentinel" not in captured.err + captured.out
    assert not (tmp_path / "run").exists()


def local_request(tmp_path):
    return request(
        tmp_path,
        mode="local-inference",
        dataset="reviewed",
        split="development",
        cases=["REV-01", "REV-23", "REV-25"],
        endpoint="http://127.0.0.1:9999/v1/chat/completions",
        spec=ExperimentSpec(
            configurations=["B", "C"],
            model=MODEL,
            max_calls=6,
            max_input_tokens=6144,
            max_output_tokens=2048,
        ),
    )


def test_exec05_actual_mode_failure_never_substitutes_fixture(tmp_path, monkeypatch):
    class FailingTransport:
        calls = 0

        def complete(self, payload):
            self.calls += 1
            raise RuntimeError("private-sentinel-response")

    def forbidden(*args, **kwargs):
        raise AssertionError("fixture fallback")

    monkeypatch.setattr(notebook_runs, "FakeExperimentProvider", forbidden)
    transport = FailingTransport()
    value = local_request(tmp_path)
    result = notebook_runs.run_notebook(value, data_root=DATA, transport=transport)
    assert result.status == "completed_with_failures"
    assert result.evidence_mode == "local-inference"
    assert transport.calls == 1
    report = read_json(value.output / "report.json")
    statuses = [record["status"] for r in report["results"] for record in r["records"]]
    assert statuses == ["failed", *(["not_attempted"] * 5)]
    assert "private-sentinel" not in json.dumps(report)


def test_exec05_interruption_keeps_checkpoint_and_manifest(tmp_path):
    class InterruptedTransport:
        def complete(self, payload):
            raise KeyboardInterrupt

    value = local_request(tmp_path)
    result = notebook_runs.run_notebook(value, data_root=DATA, transport=InterruptedTransport())
    assert result.status == "interrupted"
    assert result.error_code == "interrupted"
    report = read_json(value.output / "report.json")
    assert report["complete"] is False
    assert report["active_case"] == {"configuration": "B", "case_id": "REV-01"}
    assert verify_manifest(value.output / "manifest.json") == result


def test_exec03_manifest_corrupt_parameters(tmp_path):
    planned = notebook_runs.plan_notebook(request(tmp_path), data_root=DATA)
    value = planned.model_dump(mode="json")
    value["parameters"]["seed"] = 123
    value["manifest_sha256"] = digest({k: v for k, v in value.items() if k != "manifest_sha256"})
    with pytest.raises(ValidationError, match="parameters checksum"):
        seal_manifest(value)
