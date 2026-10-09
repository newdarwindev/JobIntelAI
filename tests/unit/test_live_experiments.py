"""V38: fake Responses transports verify the live command; no purchased quality claims."""

import copy
import json
from pathlib import Path

import pytest

from jobintel.experiment_cli import main
from jobintel.experiment_corpus import digest, load_corpus, write_json
from jobintel.experiment_provider import OpenAIExperimentProvider
from jobintel.experiment_publication import audit_draft
from jobintel.experiment_reviewed import freeze_reviewed
from jobintel.experiments import ExperimentSpec, rescore, run_experiment
from jobintel.openai_transport import ProviderError, TransportResponse

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture
def corpus():
    return freeze_reviewed(DATA)


@pytest.fixture
def spec():
    return ExperimentSpec(
        model="test-model",
        max_calls=75,
        budget_usd=10,
        authorization_reference="unit test only; no paid calls authorized",
        pricing={
            "model": "test-model",
            "source": "test simulation, not purchased usage",
            "date": "2026-10-09",
            "input_usd_per_million": 2,
            "output_usd_per_million": 5,
        },
    )


class Responses:
    def __init__(self, corpus, change=None):
        self.gold = {c.text: c.gold for c in corpus.cases}
        self.calls = []
        self.change = change

    def complete(self, payload):
        self.calls.append(copy.deepcopy(payload))
        text = payload["input"][1]["content"]
        body = {
            "id": "synthetic-response",
            "status": "completed",
            "model": "test-model-2026-10-09",
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            "output": [
                {"content": [{"type": "output_text", "text": self.gold[text].model_dump_json()}]}
            ],
        }
        if self.change:
            self.change(body, payload)
        return TransportResponse(body, "synthetic-test-request")


def test_v38_reviewed_freeze_preserves_every_input_and_rejects_label_changes(corpus, tmp_path):
    path = tmp_path / "frozen.json"
    write_json(path, corpus.model_dump(mode="json"))
    assert load_corpus(path) == corpus
    assert len(corpus.cases) == 25
    value = corpus.model_dump(mode="json")
    value["cases"][0]["gold"]["requirements"] = []
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="must match the reviewed"):
        load_corpus(path)


def test_v38_full_live_cli_uses_frozen_inputs_and_rescores_without_requests(
    corpus, spec, tmp_path, monkeypatch
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    frozen, settings = tmp_path / "corpus.json", tmp_path / "spec.json"
    write_json(frozen, corpus.model_dump(mode="json"))
    write_json(settings, spec.model_dump(mode="json"))
    transport = Responses(corpus)
    output = tmp_path / "run"
    assert (
        main(
            [
                "run",
                "--provider",
                "openai",
                "--corpus",
                str(frozen),
                "--config",
                str(settings),
                "--output",
                str(output),
            ],
            transport=transport,
        )
        == 0
    )
    report = json.loads((output / "report.json").read_text())
    assert len(transport.calls) == 75
    texts = [c.text for c in corpus.cases]
    assert [p["input"][1]["content"] for p in transport.calls] == texts * 3
    assert all(
        p["model"] == "test-model" and p["store"] is False and p["max_output_tokens"] == 4096
        for p in transport.calls
    )
    assert all("text" not in p for p in transport.calls[:25])
    assert all(p["text"]["format"]["strict"] is True for p in transport.calls[25:])
    assert transport.calls[25:] == transport.calls[25:50] * 2
    for result in report["results"]:
        summary = result["summary"]
        assert summary["succeeded"] == 25 and summary["failed"] == 0
        assert summary["tokens"] == {"input": 2500, "output": 500}
        assert summary["cost_usd"] == pytest.approx(0.0075)
        assert (
            summary["metrics"]["counts"]["precision"]["numerator"] == summary["metrics"]["expected"]
        )
        rates = summary["metrics"]["reviewed_metrics"]
        assert rates["semantic_unsupported_claim_rate"]["numerator"] == 0
        assert rates["abstention_precision"]["value"] == 1
        assert rates["matching_agreement"]["value"] == 1
        assert summary["provider_elapsed_seconds"] >= 0 and summary["llm_elapsed_seconds"] is None
    count = len(transport.calls)
    assert (
        main(
            [
                "rescore",
                "--report",
                str(output / "report.json"),
                "--output",
                str(tmp_path / "scores.json"),
            ]
        )
        == 0
    )
    assert (tmp_path / "scores.json").read_bytes() == (output / "scores.json").read_bytes()
    assert len(transport.calls) == count


@pytest.mark.parametrize("change", ["calls", "tokens", "cost", "authorization", "pricing_date"])
def test_v38_live_limits_reject_before_transport(corpus, spec, change):
    modified = spec.model_dump(mode="json")
    if change == "calls":
        modified["max_calls"] = 74
    elif change == "tokens":
        modified["max_input_tokens"] = 1
    elif change == "cost":
        modified["budget_usd"] = 0
    elif change == "authorization":
        modified["authorization_reference"] = None
    else:
        modified["pricing"]["date"] = "2026-99-99"
    transport = Responses(corpus)
    with pytest.raises(ValueError):
        run_experiment(
            OpenAIExperimentProvider(transport), corpus, ExperimentSpec.model_validate(modified)
        )
    assert transport.calls == []


def test_v38_a_audits_invalid_quotes_b_c_reject_without_production_writes(corpus, spec):
    def wrong_quote(body, payload):
        if payload["input"][1]["content"] == corpus.cases[0].text:
            extraction = json.loads(body["output"][0]["content"][0]["text"])
            extraction["requirements"][0]["evidence"]["quote"] = "unsupported authored test claim"
            body["output"][0]["content"][0]["text"] = json.dumps(extraction)

    report = run_experiment(OpenAIExperimentProvider(Responses(corpus, wrong_quote)), corpus, spec)
    a, b, c = report["results"]
    assert a["summary"]["succeeded"] == 25
    assert a["summary"]["metrics"]["unsupported_span_rate"] > 0
    assert (
        a["summary"]["metrics"]["reviewed_metrics"]["semantic_unreviewable_span_rate"]["numerator"]
        == 1
    )
    for result in [b, c]:
        assert result["summary"]["succeeded"] == 24 and result["summary"]["failed"] == 1
        failed = result["records"][0]
        assert failed["prediction"] is None and failed["raw_prediction"] is not None
        assert failed["error_code"] == "invalid_evidence"
        assert failed["usage"] == {"input_tokens": 100, "output_tokens": 20}


@pytest.mark.parametrize(
    "failure",
    [
        "quota",
        "model",
        "usage_limit",
        "invalid_json_model",
        "invalid_json_usage",
        "missing_model",
        "partial_over_limit",
    ],
)
def test_v38_fatal_response_stops_remaining_paid_attempts(corpus, spec, failure):
    def broken(body, payload):
        if failure == "quota":
            raise ProviderError("quota", 502, False)
        if failure in {"model", "invalid_json_model"}:
            body["model"] = "different-model"
        elif failure == "missing_model":
            body.pop("model")
        else:
            body["usage"]["input_tokens"] = spec.max_input_tokens + 1
        if failure.startswith("invalid_json"):
            body["output"][0]["content"][0]["text"] = "{"
        if failure == "partial_over_limit":
            body["usage"].pop("output_tokens")

    transport = Responses(corpus, broken)
    report = run_experiment(OpenAIExperimentProvider(transport), corpus, spec)
    assert len(transport.calls) == 1
    assert sum(r["summary"]["not_attempted"] for r in report["results"]) == 74
    assert all(r["summary"]["metrics"] is None for r in report["results"])
    assert (
        report["results"][0]["records"][0]["error_code"]
        == {
            "quota": "quota",
            "model": "model_mismatch",
            "usage_limit": "token_limit",
            "invalid_json_model": "model_mismatch",
            "invalid_json_usage": "token_limit",
            "missing_model": "model_unavailable",
            "partial_over_limit": "token_limit",
        }[failure]
    )
    assert rescore(report)["results"][0]["summary"]["failed"] == 25


def test_v38_malformed_output_shape_retains_real_usage(corpus, spec):
    def malformed(body, payload):
        body["output"] = None

    transport = Responses(corpus, malformed)
    report = run_experiment(OpenAIExperimentProvider(transport), corpus, spec)
    assert len(transport.calls) == 75
    for result in report["results"]:
        assert result["summary"]["failed"] == 25
        assert result["summary"]["cost_usd"] == pytest.approx(0.0075)
        record = result["records"][0]
        assert record["error_code"] == "invalid_schema"
        assert record["usage"] == {"input_tokens": 100, "output_tokens": 20}
        assert record["output_text"] is None


def test_v38_missing_usage_remains_unknown_and_parse_failures_keep_output(corpus, spec):
    def malformed(body, payload):
        body.pop("usage")
        body["output"][0]["content"][0]["text"] = "{"

    transport = Responses(corpus, malformed)
    report = run_experiment(OpenAIExperimentProvider(transport), corpus, spec)
    assert len(transport.calls) == 75
    for result in report["results"]:
        assert result["summary"]["failed"] == 25
        assert (
            result["summary"]["metrics"]
            is result["summary"]["tokens"]
            is result["summary"]["cost_usd"]
            is None
        )
        assert result["records"][0]["output_text"] == "{"
        assert result["records"][0]["provenance"]["attempt_count"] == 1


def test_v38_first_request_interruption_keeps_atomic_active_case(corpus, spec, tmp_path):
    from jobintel.experiment_cli import save_checkpoint

    class Interrupted:
        def complete(self, payload):
            raise KeyboardInterrupt()

    path = tmp_path / "report.json"
    with pytest.raises(KeyboardInterrupt):
        run_experiment(
            OpenAIExperimentProvider(Interrupted()),
            corpus,
            spec,
            checkpoint=lambda r: save_checkpoint(path, r),
        )
    report = json.loads(path.read_text())
    assert report["complete"] is False
    assert report["active_case"] == {"configuration": "A", "case_id": "REV-01"}
    with pytest.raises(ValueError, match="incomplete"):
        rescore(report)


def test_v38_reviewed_fake_cli_keeps_five_unavailable_cases_per_config(tmp_path):
    frozen = tmp_path / "corpus.json"
    assert main(["freeze", "--dataset", "reviewed", "--output", str(frozen)]) == 0
    output = tmp_path / "run"
    assert main(["run", "--corpus", str(frozen), "--output", str(output)]) == 1
    report = json.loads((output / "report.json").read_text())
    assert [r["summary"]["failed"] for r in report["results"]] == [5, 5, 5]
    assert "Fake provider regression only" in (output / "comparison.md").read_text()
    assert (
        main(
            [
                "publish",
                "--report",
                str(output / "report.json"),
                "--output",
                str(tmp_path / "public"),
            ]
        )
        == 0
    )
    assert json.loads((tmp_path / "public/scores.json").read_text()) == rescore(report)


def test_v38_live_publication_requires_exact_completed_privacy_audit(corpus, spec, tmp_path):
    report = run_experiment(OpenAIExperimentProvider(Responses(corpus)), corpus, spec)
    source, review = tmp_path / "report.json", tmp_path / "audit.json"
    readme = tmp_path / "README.md"
    readme.write_text("# Authored test\n\nKeep this introduction.\n")
    write_json(source, report)
    audit = audit_draft(report, DATA)
    write_json(review, audit)

    def publish(output):
        return main(
            [
                "publish",
                "--report",
                str(source),
                "--audit",
                str(review),
                "--output",
                str(output),
                "--readme",
                str(readme),
            ]
        )

    with pytest.raises(SystemExit):
        publish(tmp_path / "blocked")
    audit.update(
        approved=True,
        findings=[],
        reviewer="automated unit-test reviewer",
        method="simulated authored output only; not an actual live run",
        revision="test-1",
    )
    review.write_text(json.dumps(audit))
    assert publish(tmp_path / "published") == 0
    public = json.loads((tmp_path / "published/report.json").read_text())
    assert public == report
    assert "Keep this introduction." in readme.read_text()
    assert "[A](published/configuration-A.json)" in readme.read_text()
    assert (
        json.loads((tmp_path / "published/configuration-B.json").read_text())["result"]
        == report["results"][1]
    )
    report["provenance"]["git_dirty"] = not report["provenance"]["git_dirty"]
    source.write_text(json.dumps(report))
    with pytest.raises(SystemExit):
        publish(tmp_path / "stale-audit")


def test_v38_publication_blocks_credentials_and_private_source_labels(corpus, spec):
    report = run_experiment(OpenAIExperimentProvider(Responses(corpus)), corpus, spec)
    report["quality_claim"] = "sk-SYNTHETIC_SENTINEL_1234567890"
    with pytest.raises(ValueError, match="credential"):
        audit_draft(report, DATA)
    report["quality_claim"] = "simulated unit test"
    report["corpus"]["cases"][0]["gold"]["requirements"][0]["notes"] = "private notes"
    report["corpus_sha256"] = digest(report["corpus"])
    with pytest.raises(ValueError):
        audit_draft(report, DATA)


def test_v38_legacy_public_fake_report_rescores_exactly():
    report = json.loads((DATA.parent / "results/experiments/fake/report.json").read_text())
    expected = json.loads((DATA.parent / "results/experiments/fake/scores.json").read_text())
    assert rescore(report) == expected


def test_v38_public_audit_rejects_fabricated_summary(corpus, spec):
    report = run_experiment(OpenAIExperimentProvider(Responses(corpus)), corpus, spec)
    report["results"][0]["summary"]["metrics"]["precision"] = 0.123
    with pytest.raises(ValueError, match="summaries differ"):
        audit_draft(report, DATA)


def test_v38_rehashed_structured_output_still_requires_grounding(corpus, spec):
    report = run_experiment(OpenAIExperimentProvider(Responses(corpus)), corpus, spec)
    result = report["results"][1]
    for field in ["prediction", "raw_prediction"]:
        result["records"][0][field]["requirements"][0]["evidence"]["quote"] = (
            "invalid authored quote"
        )
    result["records_sha256"] = digest(result["records"])
    with pytest.raises(ValueError):
        rescore(report)
