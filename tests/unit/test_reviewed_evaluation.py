"""V20, V33-V37: hand-calculated metric boundaries and frozen source review."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from jobintel.evaluation import score
from jobintel.evaluation_corpus import ReviewedCorpus, load_reviewed
from jobintel.evaluation_metrics import classification_metrics, reviewed_case_metrics
from jobintel.evaluation_runs import human_summary, run_report, usage_summary
from jobintel.openai_transport import ProviderError
from jobintel.schemas import EvaluationPricing, Extraction
from jobintel.snapshots import validate_grounding

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture
def corpus():
    return load_reviewed(DATA)


def test_v33_frozen_review_is_complete_and_rejects_tampering(corpus, tmp_path):
    assert len(corpus.cases) == 25
    assert {s for c in corpus.cases for s in c.expected_matches} == {
        "COVERED",
        "PARTIAL",
        "MISSING",
        "UNKNOWN",
    }
    assert {"responsibility", "ambiguity", "versions", "negation"} <= {
        t for c in corpus.cases for t in c.tags
    }
    for case in corpus.cases:
        validate_grounding(case.text, case.gold)
    changed = corpus.model_dump(mode="json")
    changed["review"]["reviewer"] = None
    with pytest.raises(ValueError, match="review requires"):
        ReviewedCorpus.model_validate(changed)
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation/reviewed-v1.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="source pin"):
        load_reviewed(tmp_path)


def test_v20_v34_duplicate_type_and_zero_boundaries_have_exact_counts(corpus):
    gold = corpus.cases[0].gold
    wrong = gold.requirements[0].model_copy(update={"requirement_type": "PREFERRED"})
    prediction = Extraction(requirements=[wrong, wrong, gold.requirements[1]])
    result = score([prediction], [gold], [corpus.cases[0].text], counted=True)
    assert result["counts"]["precision"] == {"numerator": 2, "denominator": 3}
    assert result["counts"]["f1"] == {"numerator": 4, "denominator": 5}
    assert result["counts"]["type_accuracy"] == {"numerator": 1, "denominator": 2}
    classes = classification_metrics([prediction], [gold])
    assert classes["type_confusion_matrix"]["MUST"]["PREFERRED"] == 1
    assert classes["must_preferred_accuracy"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    empty = Extraction(requirements=[])
    zero = score([empty], [empty], ["No requirement."], counted=True)
    assert zero["counts"]["precision"]["denominator"] == 0
    assert zero["precision"] is zero["recall"] is zero["f1"] is None
    missing = score([empty], [gold], [corpus.cases[0].text], counted=True)
    assert missing["recall"] == 0 and missing["precision"] is None


def test_v34_alias_alignment_is_separate_from_semantic_entailment(corpus, taxonomy):
    case = corpus.cases[0]
    alias = case.gold.requirements[1].model_copy(update={"skills": ["Postgres"]})
    predicted = case.gold.model_copy(update={"requirements": [case.gold.requirements[0], alias]})
    assert score([predicted], [case.gold], [case.text])["recall"] == 0.5
    semantic = reviewed_case_metrics(predicted, case, corpus, taxonomy)
    assert semantic["semantic_unsupported_claim_rate"] == {
        "numerator": 0,
        "denominator": 2,
        "value": 0.0,
    }


def test_v34_valid_irrelevant_quote_is_semantic_error_not_span_error(corpus, taxonomy):
    case = corpus.cases[20]
    requirement = case.gold.requirements[0]
    quote = "Our product uses Rust."
    irrelevant = requirement.model_copy(
        update={
            "raw_text": quote,
            "evidence": requirement.evidence.model_copy(
                update={"start": 0, "end": len(quote), "quote": quote}
            ),
        }
    )
    prediction = Extraction(requirements=[irrelevant])
    validate_grounding(case.text, prediction)
    assert score([prediction], [case.gold], [case.text])["unsupported_span_rate"] == 0
    metrics = reviewed_case_metrics(prediction, case, corpus, taxonomy)
    assert metrics["semantic_unsupported_claim_rate"] == {
        "numerator": 1,
        "denominator": 1,
        "value": 1.0,
    }


def test_v34_invalid_quote_is_unreviewable_not_semantic_hallucination(corpus, taxonomy):
    case = corpus.cases[20]
    invalid = case.gold.requirements[0].model_copy(
        update={"evidence": case.gold.requirements[0].evidence.model_copy(update={"start": 0})}
    )
    prediction = Extraction(requirements=[invalid])
    assert score([prediction], [case.gold], [case.text])["unsupported_span_rate"] == 1
    metrics = reviewed_case_metrics(prediction, case, corpus, taxonomy)
    assert metrics["semantic_unsupported_claim_rate"] == {
        "numerator": 0,
        "denominator": 0,
        "value": None,
    }
    assert metrics["semantic_unreviewable_span_rate"]["value"] == 1


def test_v34_wrong_years_with_valid_quote_is_not_a_span_error(corpus, taxonomy):
    case = corpus.cases[4]
    payload = case.gold.model_dump(mode="json")
    payload["requirements"][0]["years_required"]["minimum"] = 8
    prediction = Extraction.model_validate(payload)
    assert score([prediction], [case.gold], [case.text])["unsupported_span_rate"] == 0
    assert (
        reviewed_case_metrics(prediction, case, corpus, taxonomy)[
            "semantic_unsupported_claim_rate"
        ]["value"]
        == 1
    )


def test_v34_misgrouped_any_all_is_unsupported(corpus, taxonomy):
    case = corpus.cases[1]
    prediction = case.gold.model_copy(
        update={"requirements": [case.gold.requirements[0].model_copy(update={"operator": "ALL"})]}
    )
    assert score([prediction], [case.gold], [case.text])["recall"] == 0
    assert (
        reviewed_case_metrics(prediction, case, corpus, taxonomy)[
            "semantic_unsupported_claim_rate"
        ]["value"]
        == 1
    )


def test_v35_abstention_precision_and_recall_distinguish_missing_known_predicates(corpus, taxonomy):
    case = corpus.cases[4]
    prediction = case.gold.model_copy(
        update={
            "requirements": [case.gold.requirements[0].model_copy(update={"years_required": None})]
        }
    )
    metrics = reviewed_case_metrics(prediction, case, corpus, taxonomy)
    assert metrics["abstention_precision"] == {"numerator": 5, "denominator": 6, "value": 5 / 6}
    assert metrics["abstention_recall"] == {"numerator": 5, "denominator": 5, "value": 1.0}
    # An omitted fact is not a positive unsupported claim.
    assert metrics["semantic_unsupported_claim_rate"]["value"] == 0
    case = corpus.cases[20]
    payload = case.gold.model_dump(mode="json")
    payload["geography"] = {
        "value": "Berlin",
        "evidence": case.gold.requirements[0].evidence.model_dump(),
    }
    prediction = Extraction.model_validate(payload)
    metrics = reviewed_case_metrics(prediction, case, corpus, taxonomy)
    assert metrics["correct_unknown_rate"] == {"numerator": 6, "denominator": 7, "value": 6 / 7}


def test_v36_false_covered_and_zero_matching_denominators(corpus, taxonomy):
    case = corpus.cases[2]
    metrics = reviewed_case_metrics(case.gold, case, corpus, taxonomy, match_states=["COVERED"])
    assert metrics["matching_agreement"]["value"] == 0
    assert metrics["false_covered_rate"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    empty = corpus.cases[24]
    metrics = reviewed_case_metrics(empty.gold, empty, corpus, taxonomy)
    assert metrics["matching_agreement"]["value"] is None
    assert metrics["semantic_unsupported_claim_rate"]["value"] is None


def test_v34_filter_and_responsibility_multisets(corpus, taxonomy):
    case = corpus.cases[23]
    prediction = case.gold.model_copy(update={"responsibilities": case.gold.responsibilities * 2})
    metrics = reviewed_case_metrics(prediction, case, corpus, taxonomy)
    assert metrics["responsibilities_precision"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert metrics["filters_recall"] == {"numerator": 3, "denominator": 3, "value": 1.0}
    prediction = prediction.model_copy(update={"filters": None})
    assert (
        reviewed_case_metrics(prediction, case, corpus, taxonomy)["filters_recall"]["value"]
        == 2 / 3
    )


def test_v37_pricing_and_missing_usage_are_measured_separately():
    pricing = EvaluationPricing(
        model="synthetic",
        source="synthetic://test-pricing",
        date="2026-10-09",
        input_usd_per_million=2,
        output_usd_per_million=4,
    )
    records = [
        {
            "provenance": {
                "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                "elapsed_seconds": 0.25,
            }
        }
    ] * 2
    result = usage_summary(records, pricing)
    assert result["estimated_cost"] == 0.0008
    assert result["tokens"] == 300 and result["provider_elapsed_seconds"] == 0.5
    assert result["llm_elapsed_seconds"] is None
    result = usage_summary([records[0], {"provenance": None}], pricing)
    assert result["estimated_cost"] is result["tokens"] is None
    assert result["known_cost_usd"] == 0.0004 and result["missing_usage_cases"] == 1


def test_v37_failures_and_frozen_provenance_survive_reporting(provider):
    original = run_report(provider, DATA, ["fixture_normalized"], dataset="reviewed")
    repeated = run_report(provider, DATA, ["fixture_normalized"], dataset="reviewed")
    assert original["dataset_sha256"] == repeated["dataset_sha256"]
    assert original["results"][0]["identity"] == repeated["results"][0]["identity"]
    assert original["results"][0]["succeeded"] == 20
    assert original["results"][0]["failed"] == 5
    assert "REV-21: provider_unavailable" in human_summary(original)
    before = deepcopy(original)
    assert json.loads(json.dumps(original)) == before


def test_v37_all_failed_metrics_are_null_and_exception_bodies_are_redacted():
    class Broken:
        name = "fixture"

        def extract(self, text, configuration):
            raise RuntimeError("SENTINEL_PRIVATE_POSTING_SECRET")

    report = run_report(Broken(), DATA, ["fixture_normalized"])
    assert report["results"][0]["metrics"] is None
    assert report["results"][0]["failed"] == 20
    assert "SENTINEL_PRIVATE" not in json.dumps(report)


def test_v37_live_failure_stops_calls_and_retains_attempt_provenance(provider):
    class BrokenLive:
        name = "openai"
        model = "synthetic"
        calls = 0

        def extract(self, text, configuration):
            self.calls += 1
            error = ProviderError("quota", 502, False)
            error.provenance = {"attempt_count": 1, "usage": None}
            raise error

    live = BrokenLive()
    report = run_report(live, DATA, ["openai_structured_v1"])
    assert live.calls == 1
    assert report["results"][0]["per_case"][0]["provenance"]["attempt_count"] == 1
    assert report["results"][0]["per_case"][1]["status"] == "not_attempted"
