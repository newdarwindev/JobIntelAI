"""Resume zero-cost checkpoints without repeating an uncertain in-flight request."""

from copy import deepcopy
from datetime import UTC, datetime

from jobintel.experiment_corpus import digest


def restore_checkpoint(saved, fresh, corpus, spec):
    from jobintel.experiment_network import NETWORK_MODES, configurations

    if fresh["mode"] not in NETWORK_MODES:
        raise ValueError("resume is supported only for credential-free network experiments")
    if saved.get("complete") is not False or saved.get("format_version") != 2:
        raise ValueError("resume requires an incomplete format-v2 checkpoint")
    value = {k: v for k, v in saved.items() if k != "checkpoint_sha256"}
    if saved.get("checkpoint_sha256") != digest(value):
        raise ValueError("checkpoint hash mismatch")
    for field in ["mode", "corpus", "corpus_sha256", "spec", "spec_sha256", "schema_sha256"]:
        if saved.get(field) != fresh[field]:
            raise ValueError("checkpoint input/protocol identity differs from this run")
    if saved["provenance"]["source_sha256"] != fresh["provenance"]["source_sha256"]:
        raise ValueError("checkpoint code differs from this run")
    report = deepcopy(saved)
    report.pop("checkpoint_sha256")
    validate_prefix(report, corpus, spec, configurations(fresh["mode"]))
    active = report.get("active_case")
    if active:
        retain_interruption(report, corpus, active, spec)
    report["active_case"] = None
    report.setdefault("resumptions", []).append(
        {
            "at": datetime.now(UTC).isoformat(),
            "active_case": active,
            "uncertain_request_repeated": False,
            "code_provenance": fresh["provenance"],
        }
    )
    return report


def validate_prefix(report, corpus, spec, configs):
    from jobintel.experiments import CaseRecord, validate_saved_predictions

    names = [r["configuration"] for r in report["results"]]
    if names != spec.configurations[: len(names)]:
        raise ValueError("checkpoint configurations are not an ordered prefix")
    for index, result in enumerate(report["results"]):
        config = configs[result["configuration"]]
        if result["config"] != config or result["config_sha256"] != digest(config):
            raise ValueError("checkpoint configuration hash mismatch")
        records = result["records"]
        expected = [(c.case_id, c.snapshot_sha256) for c in corpus.cases[: len(records)]]
        if [(r["case_id"], r["snapshot_sha256"]) for r in records] != expected:
            raise ValueError("checkpoint cases are not an ordered prefix")
        if index < len(names) - 1 and len(records) != len(corpus.cases):
            raise ValueError("checkpoint skipped unfinished configuration")
        for record in records:
            CaseRecord.model_validate(record)
        # Partial checkpoints intentionally have no final records digest/summary.
        validate_saved_predictions(
            result, corpus.model_copy(update={"cases": corpus.cases[: len(records)]})
        )


def retain_interruption(report, corpus, active, spec):
    from jobintel.experiment_network import local_payload
    from jobintel.experiment_provider import request_payload
    from jobintel.experiments import unattempted

    if not report["results"]:
        raise ValueError("checkpoint active case has no configuration")
    result = report["results"][-1]
    index = len(result["records"])
    if index >= len(corpus.cases) or active != {
        "configuration": result["configuration"],
        "case_id": corpus.cases[index].case_id,
    }:
        raise ValueError("checkpoint active case is not the next frozen input")
    record = unattempted(corpus.cases[index])
    builder = local_payload if report["mode"] == "local-inference" else request_payload
    payload = builder(corpus.cases[index].text, result["config"], spec)
    record.update(
        status="failed",
        error_code="interrupted",
        provenance={
            "attempt_count": 1,
            "request_sha256": digest(payload),
            "source_sha256": corpus.cases[index].snapshot_sha256,
            "execution_mode": report["mode"],
            "requested_model": spec.model,
            **result["config"].get("model_identity", {}),
            "request_outcome": "unknown after interruption",
            "usage": None,
            "response_model": None,
            "request_id": None,
        },
    )
    result["records"].append(record)
