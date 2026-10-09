from collections import defaultdict

from jobintel.schemas import Extraction


def semantic_key(requirement) -> tuple:
    # Type and exact boundary are scored separately; preserve ANY vs ALL meaning.
    return (
        requirement.operator,
        tuple(sorted(requirement.skills)),
        requirement.explicit_production_required,
        requirement.experience_obligation,
        requirement.production_obligation,
        tuple(
            sorted(
                (v.skill, v.product, v.comparator, v.version)
                for v in requirement.version_constraints
            )
        ),
        None
        if requirement.years_required is None
        else (requirement.years_required.minimum, requirement.years_required.maximum),
    )


def score(
    predictions: list[Extraction], gold: list[Extraction], texts: list[str], *, counted=False
) -> dict:
    if not (len(predictions) == len(gold) == len(texts)) or not gold:
        raise ValueError("evaluation needs nonempty, aligned predictions, gold, and texts")
    tp = predicted = expected = correct_type = correct_evidence = grounded = 0
    for prediction, truth, text in zip(predictions, gold, texts, strict=True):
        # Greedy exact-key multiset alignment. Each gold item can be consumed once.
        remaining = defaultdict(list)
        for requirement in truth.requirements:
            remaining[semantic_key(requirement)].append(requirement)
        predicted += len(prediction.requirements)
        expected += len(truth.requirements)
        for requirement in prediction.requirements:
            if requirement_spans_valid(text, requirement):
                grounded += 1
            options = remaining[semantic_key(requirement)]
            if options:
                reference = options.pop(0)
                tp += 1
                correct_type += requirement.requirement_type == reference.requirement_type
                correct_evidence += requirement.evidence == reference.evidence
    precision = tp / predicted if predicted else None
    recall = tp / expected if expected else None
    result = {
        "true_positives": tp,
        "predicted": predicted,
        "expected": expected,
        "precision": precision,
        "recall": recall,
        "f1": None
        if precision is None or recall is None
        else (2 * precision * recall / (precision + recall) if precision + recall else 0),
        "type_accuracy": correct_type / tp if tp else None,
        "evidence_accuracy": correct_evidence / tp if tp else None,
        "unsupported_span_rate": (predicted - grounded) / predicted if predicted else None,
        "semantic_hallucination_rate": None,
        "abstention_quality": None,
    }
    if counted:
        result["counts"] = {
            "precision": {"numerator": tp, "denominator": predicted},
            "recall": {"numerator": tp, "denominator": expected},
            "f1": {"numerator": 2 * tp, "denominator": predicted + expected},
            "type_accuracy": {"numerator": correct_type, "denominator": tp},
            "evidence_accuracy": {"numerator": correct_evidence, "denominator": tp},
            "unsupported_span_rate": {"numerator": predicted - grounded, "denominator": predicted},
        }
    return result


def requirement_spans_valid(text, requirement):
    evidence = [requirement.evidence, *(v.evidence for v in requirement.version_constraints)]
    return requirement.raw_text == requirement.evidence.quote and all(
        e.end <= len(text) and text[e.start : e.end] == e.quote for e in evidence
    )


def run_evaluation(provider, root, configurations: list[str]) -> dict:
    from jobintel.evaluation_runs import run_report

    return run_report(provider, root, configurations)


def evaluation_tokens(records):
    usages = [r.provenance.get("usage") if r.provenance else None for r in records]
    if any(u is None or u.get("total_tokens") is None for u in usages):
        return None
    return sum(u["total_tokens"] for u in usages)
