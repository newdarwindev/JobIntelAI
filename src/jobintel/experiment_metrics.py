"""Counted experiment diagnostics and source-reviewed metrics from saved predictions."""

from jobintel.evaluation_metrics import (
    aggregate_reviewed,
    classification_metrics,
    reviewed_case_metrics,
)
from jobintel.normalization import Taxonomy
from jobintel.schemas import Extraction


def summarize_reviewed(records, corpus, metrics):
    successful = [r for r in records if r["status"] == "succeeded"]
    by_id = {c.case_id: c for c in corpus.cases}
    predictions = [Extraction.model_validate(r["prediction"]) for r in successful]
    gold = [by_id[r["case_id"]].gold for r in successful]
    if metrics is not None:
        metrics.update(classification_metrics(predictions, gold))
    reviewed = getattr(corpus, "reviewed", None)
    details = reviewed_details(successful, reviewed, corpus.taxonomy) if reviewed else []
    rates = aggregate_reviewed(details)
    if metrics is not None and rates:
        metrics.update(
            reviewed_metrics=rates,
            semantic_hallucination_rate=rates["semantic_unsupported_claim_rate"]["value"],
            abstention_quality=rates["correct_unknown_rate"]["value"],
        )
    provenances = [r.get("provenance") for r in records]
    elapsed = [p.get("elapsed_seconds") if p else None for p in provenances]
    return {
        "reviewed_per_case": details if reviewed else None,
        "not_attempted": sum(r["status"] == "not_attempted" for r in records),
        "provider_elapsed_seconds": sum(elapsed)
        if elapsed and all(e is not None for e in elapsed)
        else None,
        "llm_elapsed_seconds": None,
    }


def reviewed_details(records, reviewed, taxonomy_records):
    taxonomy = Taxonomy.from_records(taxonomy_records)
    cases = {c.case_id: c for c in reviewed.cases}
    return [
        {
            "case_id": r["case_id"],
            "reviewed_metrics": reviewed_case_metrics(
                Extraction.model_validate(r["prediction"]), cases[r["case_id"]], reviewed, taxonomy
            ),
        }
        for r in records
    ]
