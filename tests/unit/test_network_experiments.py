"""Credential-free request bounds, reviewed selection and interrupted-run recovery."""

import copy
import json
from pathlib import Path

import pytest

from jobintel.experiment_cli import save_checkpoint, selected_experiment_provider
from jobintel.experiment_corpus import freeze_bundled
from jobintel.experiment_network import LocalExperimentProvider
from jobintel.experiment_reviewed import freeze_reviewed
from jobintel.experiments import ExperimentSpec, plan, rescore, run_experiment
from jobintel.local_model import MODEL, MODEL_SHA256
from jobintel.openai_transport import ProviderError, TransportResponse

DATA = Path("data")


def settings(**changes):
    return ExperimentSpec(
        **(
            {
                "configurations": ["B", "C"],
                "model": MODEL,
                "max_calls": 2,
                "max_input_tokens": 6144,
                "max_output_tokens": 512,
            }
            | changes
        )
    )


class Chat:
    def __init__(self, case):
        self.case = case
        self.calls = []
        self.interrupt = False

    def complete(self, payload):
        self.calls.append(copy.deepcopy(payload))
        if self.interrupt:
            raise KeyboardInterrupt()
        return TransportResponse(
            {
                "model": MODEL,
                "id": "authored-unit-chat",
                "usage": {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150},
                "timings": {"prompt_ms": 10, "predicted_ms": 20},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": self.case.gold.model_dump_json()},
                    }
                ],
            }
        )


def test_reviewed_subset_preserves_review_and_cannot_replace_labels():
    original = freeze_reviewed(DATA)
    selected = freeze_reviewed(DATA, ["REV-01", "REV-25"])
    assert selected.review == original.review
    assert selected.reviewed == original.reviewed
    assert selected.cases == [original.cases[0], original.cases[-1]]
    assert not freeze_bundled(DATA).review.independent
    for selection in [["missing"], ["REV-25", "REV-01"], ["REV-01", "REV-01"]]:
        with pytest.raises(ValueError):
            freeze_reviewed(DATA, selection)


@pytest.mark.parametrize(
    "changes",
    [
        {"max_calls": 1},
        {"max_input_tokens": 1},
        {"max_output_tokens": 2049},
        {"max_input_tokens": 8192},
        {"model": "wrong"},
        {"budget_usd": 1},
        {"configurations": ["A", "B"]},
        {"authorization_reference": "hosted approval"},
    ],
)
def test_network_budgets_reject_before_any_call(changes):
    corpus = freeze_reviewed(DATA, ["REV-01"])
    transport = Chat(corpus.cases[0])
    with pytest.raises(ValueError):
        run_experiment(LocalExperimentProvider(transport), corpus, settings(**changes))
    assert not transport.calls


def test_network_rejects_generator_labels_and_never_reads_hosted_credentials(monkeypatch):
    with pytest.raises(ValueError, match="source-reviewed"):
        plan(freeze_bundled(DATA), settings(max_calls=40), "local-inference")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", "/does-not-exist/hosted-key")
    assert (
        selected_experiment_provider(
            "local", None, "http://localhost:8080/v1/chat/completions"
        ).mode
        == "local-inference"
    )
    assert (
        selected_experiment_provider("emulator", None, "http://localhost:8033/v1/responses").mode
        == "emulator"
    )
    with pytest.raises(ValueError):
        selected_experiment_provider("local", None, "https://api.openai.com/v1/chat/completions")


def test_actual_payload_cap_frozen_source_identity_and_rescore():
    corpus = freeze_reviewed(DATA, ["REV-01"])
    transport = Chat(corpus.cases[0])
    report = run_experiment(LocalExperimentProvider(transport), corpus, settings())
    assert len(transport.calls) == 2 and transport.calls[0] == transport.calls[1]
    assert transport.calls[0]["max_tokens"] == 512
    assert (
        json.loads(transport.calls[0]["messages"][1]["content"])["posting"] == corpus.cases[0].text
    )
    record = report["results"][0]["records"][0]
    assert record["provenance"]["model_weights_sha256"] == MODEL_SHA256
    assert record["usage"] == {"input_tokens": 50, "output_tokens": 100}
    assert report["results"][0]["summary"]["cost_usd"] is None
    assert rescore(report)["results"][0]["summary"] == report["results"][0]["summary"]
    assert len(transport.calls) == 2


def test_resume_retains_unknown_active_request_without_repeating_it(tmp_path):
    corpus = freeze_reviewed(DATA, ["REV-01"])
    transport = Chat(corpus.cases[0])
    transport.interrupt = True
    path = tmp_path / "report.json"
    with pytest.raises(KeyboardInterrupt):
        run_experiment(
            LocalExperimentProvider(transport),
            corpus,
            settings(),
            lambda r: save_checkpoint(path, r),
        )
    saved = json.loads(path.read_text())
    assert saved["complete"] is False and saved["active_case"] == {
        "configuration": "B",
        "case_id": "REV-01",
    }
    with pytest.raises(ValueError, match="incomplete"):
        rescore(saved)
    transport.interrupt = False
    report = run_experiment(LocalExperimentProvider(transport), corpus, settings(), resume=saved)
    assert len(transport.calls) == 2
    interrupted = report["results"][0]["records"][0]
    assert interrupted["status"] == "failed" and interrupted["error_code"] == "interrupted"
    assert (
        interrupted["prediction"] is interrupted["usage"] is interrupted["elapsed_seconds"] is None
    )
    assert report["results"][1]["summary"]["succeeded"] == 1
    assert rescore(report)["results"][0]["summary"]["failed"] == 1
    saved["spec"]["max_output_tokens"] = 1
    with pytest.raises(ValueError):
        run_experiment(LocalExperimentProvider(transport), corpus, settings(), resume=saved)
    assert len(transport.calls) == 2


def test_runtime_failure_stops_all_later_network_calls():
    corpus = freeze_reviewed(DATA, ["REV-01"])

    class Failed(Chat):
        def complete(self, payload):
            self.calls.append(payload)
            raise ProviderError("timeout", 504, True)

    transport = Failed(corpus.cases[0])
    report = run_experiment(LocalExperimentProvider(transport), corpus, settings())
    assert len(transport.calls) == 1
    assert report["results"][1]["records"][0]["status"] == "not_attempted"
    assert report["results"][0]["records"][0]["usage"] is None
    assert rescore(report)["results"][0]["summary"]["metrics"] is None


def test_network_publication_requires_audit_and_cannot_replace_hosted_readme(tmp_path):
    from jobintel.experiment_cli import main
    from jobintel.experiment_corpus import write_json
    from jobintel.experiment_publication import audit_draft

    corpus = freeze_reviewed(DATA, ["REV-01"])
    report = run_experiment(LocalExperimentProvider(Chat(corpus.cases[0])), corpus, settings())
    path, review = tmp_path / "report.json", tmp_path / "audit.json"
    write_json(path, report)
    audit = audit_draft(report, DATA)
    write_json(review, audit)
    arguments = ["publish", "--report", str(path), "--audit", str(review)]
    with pytest.raises(SystemExit):
        main([*arguments, "--output", str(tmp_path / "unapproved")])
    audit.update(
        approved=True,
        findings=[],
        reviewer="automated unit-test reviewer",
        method="Authored Chat transport simulation only; not a real model result",
        revision="unit-1",
    )
    review.write_text(json.dumps(audit))
    readme = tmp_path / "README.md"
    readme.write_text("# Preserve authorized hosted evidence\n")
    with pytest.raises(SystemExit):
        main([*arguments, "--readme", str(readme), "--output", str(tmp_path / "blocked-readme")])
    assert readme.read_text() == "# Preserve authorized hosted evidence\n"
    assert main([*arguments, "--output", str(tmp_path / "published")]) == 0
    saved = json.loads((tmp_path / "published/configuration-B.json").read_text())
    assert saved["mode"] == "local-inference"
    assert saved["result"] == report["results"][0]
