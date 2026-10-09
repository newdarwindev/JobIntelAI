"""Reviewed finite-corpus entailment, abstention and matching; no LLM judge."""

from collections import Counter

from jobintel.candidate_matching import match_filters
from jobintel.matching import match_requirement


def ratio(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def supports(requirement, reference, taxonomy):
    # Reviewed gold is exhaustive for this frozen input, not a general semantic oracle.
    # Alias differences do not change entailment; a valid irrelevant quote does.
    actual = taxonomy.normalize(requirement)
    expected = taxonomy.normalize(reference)
    if (actual.operator, sorted(actual.skills), actual.requirement_type) != (
        expected.operator,
        sorted(expected.skills),
        expected.requirement_type,
    ):
        return False
    fields = [
        "years_required",
        "explicit_production_required",
        "experience_obligation",
        "production_obligation",
        "version_constraints",
    ]
    predicates = all(
        getattr(actual, f) in (None, "UNKNOWN", []) or getattr(actual, f) == getattr(expected, f)
        for f in fields
    )
    return (
        predicates
        and requirement.evidence == reference.evidence
        and requirement.raw_text == reference.raw_text
    )


def valid_span(evidence, text):
    return evidence.end <= len(text) and text[evidence.start : evidence.end] == evidence.quote


def semantic_counts(prediction, case, taxonomy):
    requirements = [
        r
        for r in prediction.requirements
        if valid_span(r.evidence, case.text) and r.raw_text == r.evidence.quote
    ]
    supported = sum(
        any(supports(r, g, taxonomy) for g in case.gold.requirements) for r in requirements
    )
    facts = [
        f
        for f in [prediction.geography, prediction.work_mode, *(prediction.filters or [])]
        if f is not None
    ]
    valid_facts = [f for f in facts if valid_span(f.evidence, case.text)]
    supported_facts = sum(
        f in [case.gold.geography, case.gold.work_mode, *(case.gold.filters or [])]
        for f in valid_facts
    )
    responsibilities = [e for e in prediction.responsibilities if valid_span(e, case.text)]
    supported_responsibilities = sum(e in case.gold.responsibilities for e in responsibilities)
    reviewed = len(requirements) + len(valid_facts) + len(responsibilities)
    claims = len(prediction.requirements) + len(facts) + len(prediction.responsibilities)
    return (
        reviewed - supported - supported_facts - supported_responsibilities,
        reviewed,
        claims - reviewed,
    )


def metadata_claims(extraction):
    claims = []
    for name in ["geography", "work_mode"]:
        fact = getattr(extraction, name)
        if fact:
            claims.append((name, fact.value, fact.evidence.model_dump_json()))
    claims.extend((f.kind, f.value, f.evidence.model_dump_json()) for f in extraction.filters or [])
    return claims


def slots(extraction, references, taxonomy):
    result = {
        "geography": extraction.geography is None,
        "work_mode": extraction.work_mode is None,
        "filters": extraction.filters is None,
    }
    remaining = list(extraction.requirements)
    for index, reference in enumerate(references):
        found = slot_requirement(remaining, reference, taxonomy)
        if found is not None:
            remaining.remove(found)
        for field in [
            "years_required",
            "explicit_production_required",
            "experience_obligation",
            "production_obligation",
        ]:
            value = getattr(found, field) if found else None
            result[f"requirement.{index}.{field}"] = value is None or value == "UNKNOWN"
    return result


def slot_requirement(remaining, reference, taxonomy):
    skills = sorted(taxonomy.normalize(reference).skills)
    candidates = [
        r
        for r in remaining
        if sorted(taxonomy.normalize(r).skills) == skills and r.operator == reference.operator
    ]
    return next(
        (r for r in candidates if r.evidence == reference.evidence),
        candidates[0] if candidates else None,
    )


def reviewed_case_metrics(prediction, case, corpus, taxonomy, *, match_states=None):
    gold = case.gold
    unsupported, claims, unreviewable = semantic_counts(prediction, case, taxonomy)
    predicted_facts = metadata_claims(prediction)
    gold_facts = metadata_claims(gold)
    expected_slots = slots(gold, gold.requirements, taxonomy)
    actual_slots = slots(prediction, gold.requirements, taxonomy)
    correct_unknown = sum(v and actual_slots[k] for k, v in expected_slots.items())
    eligibility = match_filters(gold, corpus.candidate, corpus.as_of)
    states = (
        match_states
        if match_states is not None
        else [
            match_requirement(r, corpus.candidate, taxonomy, corpus.as_of, eligibility)["status"]
            for r in gold.requirements
        ]
    )
    expected = case.expected_matches + case.expected_filter_matches
    actual = states + [f["status"] for f in eligibility]
    if len(states) != len(case.expected_matches):
        raise ValueError("matching predictions must align to reviewed requirements")
    return {
        "semantic_unsupported_claim_rate": ratio(unsupported, claims),
        "semantic_unreviewable_span_rate": ratio(unreviewable, claims + unreviewable),
        "abstention_precision": ratio(correct_unknown, sum(actual_slots.values())),
        "abstention_recall": ratio(correct_unknown, sum(expected_slots.values())),
        "correct_unknown_rate": ratio(correct_unknown, sum(expected_slots.values())),
        "matching_agreement": ratio(
            sum(a == e for a, e in zip(actual, expected, strict=True)), len(expected)
        ),
        "false_covered_rate": ratio(
            sum(a == "COVERED" and e != "COVERED" for a, e in zip(actual, expected, strict=True)),
            actual.count("COVERED"),
        ),
        **overlap_metrics("filters", predicted_facts, gold_facts),
        **overlap_metrics("responsibilities", prediction.responsibilities, gold.responsibilities),
    }


def overlap_metrics(name, predicted, expected):
    # Evidence models are mutable/unhashable: encode each multiset member deterministically.
    def keys(items):
        return Counter(str(item) for item in items)

    aligned = sum((keys(predicted) & keys(expected)).values())
    return {
        f"{name}_precision": ratio(aligned, len(predicted)),
        f"{name}_recall": ratio(aligned, len(expected)),
    }


def aggregate_reviewed(records):
    metrics = [r["reviewed_metrics"] for r in records if r.get("reviewed_metrics") is not None]
    if not metrics:
        return None
    return {
        name: ratio(
            sum(m[name]["numerator"] for m in metrics), sum(m[name]["denominator"] for m in metrics)
        )
        for name in metrics[0]
    }


def classification_metrics(predictions, gold):
    from jobintel.evaluation import semantic_key

    matrix = {
        str(kind): {str(other): 0 for other in ["MUST", "PREFERRED", "EXPERIENCE", "OTHER"]}
        for kind in ["MUST", "PREFERRED", "EXPERIENCE", "OTHER"]
    }
    obligations = [0, 0]
    for prediction, truth in zip(predictions, gold, strict=True):
        remaining = list(truth.requirements)
        for requirement in prediction.requirements:
            reference = next(
                (r for r in remaining if semantic_key(r) == semantic_key(requirement)), None
            )
            if reference is not None:
                remaining.remove(reference)
                matrix[str(reference.requirement_type)][str(requirement.requirement_type)] += 1
                if reference.requirement_type in {"MUST", "PREFERRED"}:
                    obligations[0] += requirement.requirement_type == reference.requirement_type
                    obligations[1] += 1
    return {"type_confusion_matrix": matrix, "must_preferred_accuracy": ratio(*obligations)}
