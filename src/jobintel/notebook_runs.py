"""Shared database-independent execution for Python, fresh kernels and the CLI."""

from datetime import UTC, datetime
from pathlib import Path

from jobintel.experiment_cli import save_checkpoint
from jobintel.experiment_corpus import digest, freeze_bundled, read_json, verify_public, write_json
from jobintel.experiment_publication import comparison
from jobintel.experiment_reviewed import freeze_reviewed, public_reference
from jobintel.experiments import (
    ExperimentSpec,
    FakeExperimentProvider,
    code_provenance,
    parse_corpus,
    plan,
    rescore,
    run_experiment,
)
from jobintel.local_model import MODEL_SHA256
from jobintel.local_transport import HttpLocalTransport, local_endpoint
from jobintel.notebook_artifacts import file_hash, save_manifest, seal_manifest
from jobintel.notebook_contracts import NotebookRejected, NotebookRequest

# Exact corpus retained in results/experiments/fake/report.json, format v1.
LEGACY_PUBLIC_CORPUS = "8ecb4b2db7575a2a1600c7f61231b400637efa974b13a0bcd5d7593baeb48784"


def utc_now():
    return datetime.now(UTC).isoformat()


def load_inputs(request, root):
    if request.mode == "saved-report":
        if request.report_sha256 and file_hash(request.report) != request.report_sha256:
            raise NotebookRejected("report_checksum")
        report = read_json(request.report)
        rescore(report)
        corpus = parse_corpus(report["corpus"])
        spec = ExperimentSpec.model_validate(report["spec"])
        if request.spec is not None and request.spec != spec:
            raise NotebookRejected("config_mismatch")
        return corpus, spec, report
    corpus = (
        freeze_reviewed(root, request.cases)
        if request.dataset == "reviewed"
        else freeze_bundled(root)
    )
    spec = request.spec or ExperimentSpec(max_calls=len(corpus.cases) * 3)
    return corpus, spec, None


def validate_selection(request, corpus, spec, report):
    actual_dataset = "reviewed" if hasattr(corpus, "reviewed") else "fixture"
    if request.dataset != actual_dataset:
        raise NotebookRejected("dataset_mismatch")
    split = "development" if actual_dataset == "reviewed" else "regression"
    if request.split != split:
        raise NotebookRejected("unsupported_split")
    if request.cases is not None and request.cases != [c.case_id for c in corpus.cases]:
        raise NotebookRejected("case_selection")
    if request.corpus_sha256 and request.corpus_sha256 != digest(corpus.model_dump(mode="json")):
        raise NotebookRejected("corpus_checksum")
    evidence_mode = (
        report["mode"] if report else {"fixture": "fake"}.get(request.mode, request.mode)
    )
    if evidence_mode == "fake" and spec.model != "fake-fixture":
        raise NotebookRejected("model_mismatch")
    if request.model_weights_sha256:
        if evidence_mode != "local-inference" or request.model_weights_sha256 != MODEL_SHA256:
            raise NotebookRejected("model_checksum")
    return evidence_mode


def prepare(request, data_root):
    if request.mode == "training":
        raise NotebookRejected("training_runner_unavailable_issue_81")
    if request.output.exists():
        raise NotebookRejected("output_exists")
    if request.mode == "local-inference":
        local_endpoint(request.endpoint)
        if request.seed != 42:
            raise NotebookRejected("unsupported_local_seed")
    corpus, spec, report = load_inputs(request, data_root)
    evidence_mode = validate_selection(request, corpus, spec, report)
    legacy = report is not None and digest(report["corpus"]) == LEGACY_PUBLIC_CORPUS
    if corpus.public and not legacy:
        verify_public(corpus, public_reference(corpus, data_root))
    if not corpus.public and not request.output.resolve().is_relative_to(
        Path("local_data").resolve()
    ):
        raise NotebookRejected("private_output_location")
    reservation = report["reservation"] if report else plan(corpus, spec, evidence_mode)
    return corpus, spec, report, evidence_mode, reservation


def envelope(request, corpus, spec, report, evidence_mode, reservation):
    parameters = {
        "mode": request.mode,
        "dataset": request.dataset,
        "split": request.split,
        "seed": request.seed,
        "cases": [c.case_id for c in corpus.cases],
        "spec": spec.model_dump(mode="json"),
        "corpus_sha256": digest(corpus.model_dump(mode="json")),
        "model_weights_sha256": MODEL_SHA256 if evidence_mode == "local-inference" else None,
        "timeout_seconds": request.timeout_seconds if request.mode == "local-inference" else None,
    }
    return {
        "format_version": 1,
        "mode": request.mode,
        "evidence_mode": evidence_mode,
        "status": "planned",
        "created_at": utc_now(),
        "completed_at": None,
        "parameters": parameters,
        "parameters_sha256": digest(parameters),
        "input_sha256": digest(report) if report else parameters["corpus_sha256"],
        "code": code_provenance(),
        "reservation": reservation,
        "error_code": None,
        "artifacts": [],
    }


def plan_notebook(request, *, data_root=Path("data")):
    request = NotebookRequest.model_validate(request)
    corpus, spec, report, mode, reservation = prepare(request, Path(data_root))
    return seal_manifest(envelope(request, corpus, spec, report, mode, reservation))


def execute_report(request, corpus, spec, report, root, transport):
    if report is not None:
        return report
    if request.mode == "fixture":
        provider = FakeExperimentProvider(root)
    else:
        from jobintel.experiment_network import LocalExperimentProvider

        provider = LocalExperimentProvider(
            transport or HttpLocalTransport(request.endpoint, timeout=request.timeout_seconds)
        )
    result = run_experiment(
        provider,
        corpus,
        spec,
        checkpoint=lambda value: save_checkpoint(request.output / "report.json", value),
    )
    save_checkpoint(request.output / "report.json", result)
    return result


def run_notebook(request, *, data_root=Path("data"), transport=None):
    request = NotebookRequest.model_validate(request)
    root = Path(data_root)
    corpus, spec, report, mode, reservation = prepare(request, root)
    value = envelope(request, corpus, spec, report, mode, reservation)
    request.output.mkdir(parents=True, exist_ok=False)
    try:
        report = execute_report(request, corpus, spec, report, root, transport)
        write_json(request.output / "scores.json", rescore(report))
        (request.output / "comparison.md").write_text(comparison(report), encoding="utf-8")
        value["status"] = (
            "completed_with_failures"
            if any(r["summary"]["failed"] for r in report["results"])
            else "succeeded"
        )
    except (Exception, KeyboardInterrupt) as error:
        value["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        value["error_code"] = value["status"]
    value["completed_at"] = utc_now()
    return save_manifest(request.output, value)
