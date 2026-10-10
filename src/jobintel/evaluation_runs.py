"""Reproducible evaluation reports including unsuccessful provider outcomes."""

import json
from datetime import UTC, datetime
from time import perf_counter

from jobintel.evaluation_corpus import load_reviewed
from jobintel.evaluation_metrics import (
    aggregate_reviewed,
    classification_metrics,
    reviewed_case_metrics,
)
from jobintel.experiment_corpus import FrozenCase, digest
from jobintel.normalization import Taxonomy
from jobintel.openai_transport import ProviderError
from jobintel.provider_config import configuration_for, identity
from jobintel.provider_execution import execution_mode
from jobintel.providers import ProviderUnavailable, extract_result
from jobintel.schemas import Extraction
from jobintel.snapshots import GroundingError, content_hash, validate_grounding


def inputs(root, dataset):
    taxonomy = Taxonomy(root / "taxonomy.json")
    if dataset == "reviewed":
        corpus = load_reviewed(root)
        return corpus.cases, corpus, taxonomy
    if dataset != "fixture":
        raise ValueError("unknown evaluation dataset")
    labels = json.loads((root / "golden_dataset.json").read_text())
    cases = []
    for label in labels:
        path = (root / label["fixture"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("fixture path escapes evaluation root")
        text = path.read_text()
        cases.append(
            FrozenCase(
                case_id=label["job_id"],
                text=text,
                snapshot_sha256=content_hash(text),
                gold=Extraction.model_validate(label["extraction"]),
            )
        )
    return cases, None, taxonomy


def case_record(provider, case, configuration, corpus, taxonomy):
    started = perf_counter()
    result = {
        "case_id": case.case_id,
        "source_sha256": case.snapshot_sha256,
        "status": "failed",
        "prediction": None,
        "provenance": None,
        "error": None,
        "reviewed_metrics": None,
    }
    try:
        record = extract_result(provider, case.text, configuration)
        prediction = Extraction.model_validate(record.extraction.model_dump(mode="json"))
        validate_grounding(case.text, prediction)
        result.update(
            status="succeeded",
            prediction=prediction.model_dump(mode="json"),
            provenance=record.provenance,
        )
        from jobintel.evaluation import score

        result["metrics"] = score([prediction], [case.gold], [case.text], counted=True)
        if corpus:
            result["reviewed_metrics"] = reviewed_case_metrics(prediction, case, corpus, taxonomy)
    except Exception as error:
        result.update(status="failed", prediction=None, metrics=None, reviewed_metrics=None)
        result["error"] = failure(error)
        result["provenance"] = getattr(error, "provenance", result["provenance"])
    result["posting_elapsed_seconds"] = perf_counter() - started
    return result


def failure(error):
    if isinstance(error, ProviderError):
        return {
            "code": error.code,
            "status": error.status,
            "retryable": error.retryable,
            "message": str(error),
        }
    if isinstance(error, ProviderUnavailable):
        return {"code": "provider_unavailable", "status": 501, "retryable": False}
    if isinstance(error, (GroundingError, ValueError)):
        return {"code": "invalid_output", "status": 422, "retryable": False}
    return {"code": "provider_failure", "status": 502, "retryable": False}


def configuration_records(provider, cases, configuration, corpus, taxonomy):
    records = []
    stopped = None
    for case in cases:
        if stopped:
            records.append(
                {
                    "case_id": case.case_id,
                    "source_sha256": case.snapshot_sha256,
                    "status": "not_attempted",
                    "prediction": None,
                    "provenance": None,
                    "error": {**stopped, "code": "not_attempted"},
                    "reviewed_metrics": None,
                    "posting_elapsed_seconds": None,
                }
            )
            continue
        record = case_record(provider, case, configuration, corpus, taxonomy)
        records.append(record)
        if record["error"] and provider.name == "openai":
            stopped = record["error"]
    return records


def usage_summary(records, pricing):
    provenances = [r["provenance"] for r in records]
    usage = [p.get("usage") if p else None for p in provenances]
    complete = bool(records) and all(
        u and all(type(u.get(k)) is int for k in ["input_tokens", "output_tokens", "total_tokens"])
        for u in usage
    )
    known = [
        u
        for u in usage
        if u and all(type(u.get(k)) is int for k in ["input_tokens", "output_tokens"])
    ]
    cost = None
    if pricing and known:
        cost = (
            sum(
                u["input_tokens"] * pricing.input_usd_per_million
                + u["output_tokens"] * pricing.output_usd_per_million
                for u in known
            )
            / 1_000_000
        )
    return {
        "tokens": sum(u["total_tokens"] for u in usage) if complete else None,
        "usage": {
            k: sum(u[k] for u in usage) for k in ["input_tokens", "output_tokens", "total_tokens"]
        }
        if complete
        else None,
        "estimated_cost": cost if complete else None,
        "known_cost_usd": cost,
        "missing_usage_cases": sum(
            u is None
            or any(u.get(k) is None for k in ["input_tokens", "output_tokens", "total_tokens"])
            for u in usage
        ),
        "pricing": pricing.model_dump(mode="json") if pricing else None,
        "provider_elapsed_seconds": sum(p["elapsed_seconds"] for p in provenances)
        if provenances and all(p and p.get("elapsed_seconds") is not None for p in provenances)
        else None,
        "llm_elapsed_seconds": None,
    }


def result_summary(records, cases, pricing):
    from jobintel.evaluation import score

    by_id = {c.case_id: c for c in cases}
    successes = [r for r in records if r["status"] == "succeeded"]
    predictions = [Extraction.model_validate(r["prediction"]) for r in successes]
    gold = [by_id[r["case_id"]].gold for r in successes]
    metrics = (
        score(predictions, gold, [by_id[r["case_id"]].text for r in successes], counted=True)
        if successes
        else None
    )
    reviewed = aggregate_reviewed(records)
    if metrics is not None:
        metrics.update(classification_metrics(predictions, gold))
        if reviewed:
            metrics.update(
                reviewed_metrics=reviewed,
                semantic_hallucination_rate=reviewed["semantic_unsupported_claim_rate"]["value"],
                abstention_quality=reviewed["correct_unknown_rate"]["value"],
            )
    return {
        "metrics": metrics,
        "succeeded": len(successes),
        "failed": len(records) - len(successes),
        "metric_scope": "successful cases only; failures retained separately; matching uses gold requirements and sourced candidate",
        **usage_summary(records, pricing),
    }


def run_report(provider, root, configurations, *, dataset="fixture", pricing=None):
    from jobintel.experiments import code_provenance

    cases, corpus, taxonomy = inputs(root, dataset)
    if not configurations or len(set(configurations)) != len(configurations):
        raise ValueError("evaluation requires distinct nonempty configurations")
    for configuration in configurations:
        configuration_for(configuration, provider.name)
    model = getattr(provider, "model", None)
    mode = execution_mode(provider)
    if pricing and (mode != "hosted" or pricing.model != model):
        raise ValueError("evaluation pricing must match the selected live model")
    started = perf_counter()
    report = {
        "format_version": 2,
        "dataset": dataset,
        "dataset_size": len(cases),
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "fixture replay — plumbing regression, not live LLM quality"
        if provider.name == "fixture"
        else "Responses contract emulator — authored replay, not model quality"
        if mode == "emulator"
        else "live structured extraction — independently source-reviewed labels"
        if corpus
        else "live structured extraction — authored fixture labels",
        "dataset_sha256": digest(
            corpus.model_dump(mode="json") if corpus else [c.model_dump(mode="json") for c in cases]
        ),
        "review": corpus.review.model_dump() if corpus else None,
        "dataset_revision": corpus.revision if corpus else "authored-synthetic-v2",
        "candidate_sha256": digest(corpus.candidate.model_dump(mode="json")) if corpus else None,
        "code_provenance": code_provenance(),
        "results": [],
    }
    for configuration in configurations:
        config_started = perf_counter()
        records = configuration_records(provider, cases, configuration, corpus, taxonomy)
        result = {
            "configuration": configuration,
            "identity": {
                **identity(provider.name, configuration, model, taxonomy),
                "execution_mode": mode,
            },
            "model_sha256": digest({"provider": provider.name, "model": model}),
            "configuration_sha256": digest(
                configuration_for(configuration, provider.name).__dict__
            ),
            "per_case": records,
            "provenance": [r["provenance"] for r in records],
            "elapsed_seconds": perf_counter() - config_started,
            **result_summary(records, cases, pricing),
        }
        report["results"].append(result)
    report.update(
        completed_at=datetime.now(UTC).isoformat(),
        end_to_end_elapsed_seconds=perf_counter() - started,
        status="partial" if any(r["failed"] for r in report["results"]) else "completed",
    )
    return report


def human_summary(report):
    lines = [
        f"Evaluation: {report.get('dataset_revision', 'legacy')} ({report['dataset_size']} cases), {report.get('status', 'legacy')}.",
        report["mode"],
    ]
    for result in report["results"]:
        metrics = result["metrics"]
        lines.append(
            f"{result['configuration']}: {result.get('succeeded', 'unavailable')} succeeded, {result.get('failed', 'unavailable')} failed; precision={metrics['precision'] if metrics else None}, recall={metrics['recall'] if metrics else None}."
        )
        lines.extend(
            f"  {r['case_id']}: {r['error']['code']}"
            for r in result.get("per_case", [])
            if r["error"]
        )
        for record in result.get("per_case", []):
            reviewed = record.get("reviewed_metrics")
            if reviewed and reviewed["semantic_unsupported_claim_rate"]["numerator"]:
                rate = reviewed["semantic_unsupported_claim_rate"]
                lines.append(
                    f"  {record['case_id']}: unsupported reviewed claims {rate['numerator']}/{rate['denominator']}"
                )
    return "\n".join(lines) + "\n"
