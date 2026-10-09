"""V38: offline experiment acceptance; these tests never establish a live run."""

import copy
import json
from pathlib import Path

import pytest

from jobintel.experiment_cli import main
from jobintel.experiment_corpus import FrozenCorpus, Review, digest, freeze_bundled, write_json
from jobintel.experiments import (
    CONFIGURATIONS,
    ExperimentSpec,
    FakeExperimentProvider,
    Prediction,
    Pricing,
    Usage,
    plan,
    rescore,
    run_experiment,
)
from jobintel.schemas import Extraction

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture
def corpus():
    return freeze_bundled(DATA)


class RecordingProvider(FakeExperimentProvider):
    def __init__(self):
        super().__init__(DATA)
        self.requests = []

    def predict(self, text, configuration, spec):
        self.requests.append((text, copy.deepcopy(configuration)))
        return super().predict(text, configuration, spec)


def test_v38_frozen_inputs_and_config_separation(corpus):
    provider = RecordingProvider()
    report = run_experiment(provider, corpus, ExperimentSpec())
    texts = [case.text for case in corpus.cases]
    assert [text for text, _ in provider.requests] == texts * 3
    assert [config for _, config in provider.requests] == [
        config for config in CONFIGURATIONS.values() for _ in texts
    ]
    assert len({result["config_sha256"] for result in report["results"]}) == 3
    assert report["mode"] == "fake"
    for result in report["results"]:
        assert result["summary"]["succeeded"] == 20
        assert result["summary"]["failed"] == 0
        assert result["summary"]["tokens"] is None
        assert result["summary"]["cost_usd"] is None
        assert result["summary"]["metrics"]["semantic_hallucination_rate"] is None
    assert [r["summary"]["metrics"]["true_positives"] for r in report["results"]] == [18, 18, 22]
    assert all(
        r["records"][0]["raw_prediction"] == report["results"][0]["records"][0]["raw_prediction"]
        for r in report["results"]
    )


def test_v38_saved_predictions_rescore_without_requests(corpus, monkeypatch):
    report = run_experiment(RecordingProvider(), corpus, ExperimentSpec())

    def forbid_request(*args):
        raise AssertionError("rescore attempted a provider call")

    monkeypatch.setattr(FakeExperimentProvider, "predict", forbid_request)
    saved = json.loads(json.dumps(report))
    reproduced = rescore(saved)
    assert [r["summary"] for r in reproduced["results"]] == [
        r["summary"] for r in report["results"]
    ]


@pytest.mark.parametrize(
    "change", ["text", "gold", "config", "prediction", "missing_case", "status"]
)
def test_v38_reject_corrupt_saved_report(corpus, change):
    report = run_experiment(RecordingProvider(), corpus, ExperimentSpec())
    if change == "text":
        report["corpus"]["cases"][0]["text"] += "changed"
    elif change == "gold":
        report["corpus"]["cases"][0]["gold"]["requirements"] = []
    elif change == "config":
        report["results"][0]["config"]["prompt"] = "changed"
    elif change == "prediction":
        report["results"][0]["records"][0]["prediction"]["requirements"] = []
    elif change == "missing_case":
        report["results"][0]["records"].pop()
    else:
        record = report["results"][0]["records"][0]
        record["status"] = "failed"
        report["results"][0]["records_sha256"] = digest(report["results"][0]["records"])
    with pytest.raises(ValueError):
        rescore(report)


@pytest.mark.parametrize(
    "settings",
    [
        {"max_calls": 59},
        {"max_input_tokens": 1},
        {
            "budget_usd": 0,
            "pricing": {
                "model": "fake-fixture",
                "source": "simulation only",
                "date": "2026-10-08",
                "input_usd_per_million": 1,
                "output_usd_per_million": 2,
            },
        },
    ],
)
def test_v38_budget_rejects_before_provider_requests(corpus, settings):
    provider = RecordingProvider()
    with pytest.raises(ValueError):
        run_experiment(provider, corpus, ExperimentSpec(**settings))
    assert provider.requests == []


@pytest.mark.parametrize("configurations", [["A"], ["A", "A"], ["A", "D"], []])
def test_v38_requires_two_distinct_known_configurations(configurations):
    with pytest.raises(ValueError):
        ExperimentSpec(configurations=configurations)


def test_v38_failure_preservation_and_checkpoint_redaction(corpus):
    class Failing(RecordingProvider):
        def predict(self, text, configuration, spec):
            if text == corpus.cases[0].text:
                raise RuntimeError("secret-key and full private posting must not be logged")
            return super().predict(text, configuration, spec)

    checkpoints = []
    report = run_experiment(
        Failing(),
        corpus,
        ExperimentSpec(),
        checkpoint=lambda r: checkpoints.append(copy.deepcopy(r)),
    )
    assert checkpoints[0]["complete"] is False
    assert checkpoints[0]["results"] == []
    assert any(
        c["active_case"] == {"configuration": "A", "case_id": corpus.cases[0].case_id}
        for c in checkpoints
    )
    for result in report["results"]:
        failed = result["records"][0]
        assert failed["status"] == "failed" and failed["prediction"] is None
        assert failed["error_code"] == "provider_failure"
        assert result["summary"]["succeeded"] == 19
        assert result["summary"]["failed"] == 1
        assert result["summary"]["metrics"]["expected"] == 20
    assert "secret-key" not in json.dumps(report)
    assert rescore(report)["results"][0]["summary"]["failed"] == 1


def test_v38_audits_a_invalid_evidence_and_rejects_b(corpus):
    class Ungrounded(RecordingProvider):
        def predict(self, text, configuration, spec):
            result = super().predict(text, configuration, spec)
            if result.extraction.requirements:
                result.extraction.requirements[0].evidence.quote = "unfounded"
            return result

    report = run_experiment(Ungrounded(), corpus, ExperimentSpec(configurations=["A", "B"]))
    a, b = report["results"]
    assert a["records"][0]["status"] == "succeeded"
    assert a["summary"]["metrics"]["unsupported_span_rate"] > 0
    assert b["records"][0]["status"] == "failed"
    assert b["records"][0]["raw_prediction"] is not None
    assert b["records"][0]["error_code"] == "invalid_evidence"


def test_v38_all_failures_have_null_metrics(corpus):
    class Timeout(RecordingProvider):
        def predict(self, text, configuration, spec):
            raise TimeoutError("private response")

    report = run_experiment(Timeout(), corpus, ExperimentSpec())
    assert all(result["summary"]["metrics"] is None for result in report["results"])
    assert all(result["summary"]["failed"] == 20 for result in report["results"])


def test_v38_usage_pricing_and_missing_usage_are_measured(corpus):
    class Metered(RecordingProvider):
        def predict(self, text, configuration, spec):
            result = super().predict(text, configuration, spec)
            return Prediction(
                extraction=result.extraction, usage=Usage(input_tokens=100, output_tokens=20)
            )

    pricing = Pricing(
        model="fake-fixture",
        source="simulation only",
        date="2026-10-08",
        input_usd_per_million=2,
        output_usd_per_million=5,
    )
    spec = ExperimentSpec(pricing=pricing, budget_usd=10)
    report = run_experiment(Metered(), corpus, spec)
    assert report["results"][0]["summary"]["cost_usd"] == pytest.approx(0.006)
    assert report["results"][0]["summary"]["tokens"] == {"input": 2000, "output": 400}
    report["results"][0]["records"][0]["usage"] = None
    report["results"][0]["records_sha256"] = digest(report["results"][0]["records"])
    summary = rescore(report)["results"][0]["summary"]
    assert summary["cost_usd"] is None and summary["tokens"] is None
    assert summary["known_cost_usd"] == pytest.approx(0.0057)


def test_v38_live_preflight_needs_independent_review_and_authorization(corpus):
    spec = ExperimentSpec()
    with pytest.raises(ValueError, match="independently reviewed"):
        plan(corpus, spec, "live")
    reviewed = corpus.model_copy(
        update={
            "review": Review(
                independent=True,
                reviewer="test reviewer",
                method="unit test only, not actual independent annotation",
                revision="test",
            )
        }
    )
    with pytest.raises(ValueError, match="authorization"):
        plan(reviewed, spec, "live")
    with pytest.raises(ValueError, match="pricing"):
        plan(reviewed, spec.model_copy(update={"authorization_reference": "test only"}), "live")


def test_v38_full_cli_freeze_run_rescore_publish(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBINTEL_FIXTURE_ROOT", str(DATA))
    frozen = tmp_path / "corpus.json"
    assert main(["freeze", "--output", str(frozen)]) == 0
    run_output = tmp_path / "run"
    assert main(["run", "--corpus", str(frozen), "--output", str(run_output)]) == 0
    reproduced = tmp_path / "reproduced.json"
    assert (
        main(["rescore", "--report", str(run_output / "report.json"), "--output", str(reproduced)])
        == 0
    )
    assert reproduced.read_bytes() == (run_output / "scores.json").read_bytes()
    assert (
        main(
            [
                "publish",
                "--report",
                str(run_output / "report.json"),
                "--output",
                str(tmp_path / "public"),
            ]
        )
        == 0
    )
    with pytest.raises(SystemExit) as error:
        main(["run", "--corpus", str(frozen), "--output", str(run_output)])
    assert error.value.code == 2


def test_v38_private_corpus_and_prediction_cannot_publish(corpus, tmp_path):
    report = run_experiment(RecordingProvider(), corpus, ExperimentSpec())
    report["results"][0]["records"][0]["raw_prediction"]["requirements"][0]["notes"] = (
        "private input"
    )
    path = tmp_path / "report.json"
    write_json(path, report)
    output = tmp_path / "public"
    with pytest.raises(SystemExit):
        main(["publish", "--report", str(path), "--output", str(output)])
    assert not output.exists()
    modified = corpus.model_dump(mode="json")
    modified["cases"][0]["text"] += "\nprivate input"
    modified["cases"][0]["snapshot_sha256"] = (
        __import__("hashlib").sha256(modified["cases"][0]["text"].encode()).hexdigest()
    )
    private = FrozenCorpus.model_validate(modified)
    frozen = tmp_path / "private.json"
    write_json(frozen, private.model_dump(mode="json"))
    with pytest.raises(SystemExit):
        main(["run", "--corpus", str(frozen), "--output", str(output)])
    assert not output.exists()


def test_v38_public_source_pin_and_path_traversal(tmp_path, corpus):
    (tmp_path / "golden_dataset.json").write_text(
        json.dumps(
            [
                {
                    "job_id": "X",
                    "fixture": "../private.txt",
                    "extraction": Extraction(requirements=[]).model_dump(),
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="escapes"):
        freeze_bundled(tmp_path)


def test_v38_live_cli_never_constructs_fake_fallback(corpus, tmp_path, monkeypatch, capsys):
    from jobintel.experiment_reviewed import freeze_reviewed

    reviewed = freeze_reviewed(DATA)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    frozen = tmp_path / "corpus.json"
    write_json(frozen, reviewed.model_dump(mode="json"))
    config = tmp_path / "config.json"
    write_json(
        config,
        {
            "model": "test-model",
            "max_calls": 75,
            "authorization_reference": "unit test only",
            "budget_usd": 10,
            "pricing": {
                "model": "test-model",
                "source": "simulation only",
                "date": "2026-10-08",
                "input_usd_per_million": 1,
                "output_usd_per_million": 1,
            },
        },
    )

    def forbid_fake(*args):
        raise AssertionError("live selection constructed a fake fallback")

    monkeypatch.setattr(FakeExperimentProvider, "__init__", forbid_fake)
    output = tmp_path / "live"
    with pytest.raises(SystemExit) as error:
        main(
            [
                "run",
                "--provider",
                "openai",
                "--corpus",
                str(frozen),
                "--config",
                str(config),
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2
    assert "OpenAI credentials are missing" in capsys.readouterr().err
    assert not output.exists()


def test_v38_public_normalized_prediction_cannot_smuggle_private_notes(corpus, tmp_path):
    report = run_experiment(RecordingProvider(), corpus, ExperimentSpec())
    result = report["results"][2]
    result["records"][0]["prediction"]["requirements"][0]["notes"] = "private secret"
    result["records_sha256"] = digest(result["records"])
    path = tmp_path / "report.json"
    write_json(path, report)
    output = tmp_path / "public"
    with pytest.raises(SystemExit):
        main(["publish", "--report", str(path), "--output", str(output)])
    assert not output.exists()
