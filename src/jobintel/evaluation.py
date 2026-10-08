import json
from collections import defaultdict
from time import perf_counter

from jobintel.schemas import Extraction
from jobintel.snapshots import GroundingError, validate_grounding


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


def score(predictions: list[Extraction], gold: list[Extraction], texts: list[str]) -> dict:
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
            try:
                validate_grounding(text, Extraction(requirements=[requirement]))
                grounded += 1
            except GroundingError:
                pass
            options = remaining[semantic_key(requirement)]
            if options:
                reference = options.pop(0)
                tp += 1
                correct_type += requirement.requirement_type == reference.requirement_type
                correct_evidence += requirement.evidence == reference.evidence
    precision = tp / predicted if predicted else None
    recall = tp / expected if expected else None
    return {
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


def run_evaluation(provider, root, configurations: list[str]) -> dict:
    labels = json.loads((root / "golden_dataset.json").read_text())
    texts = [(root / record["fixture"]).read_text() for record in labels]
    if any(record["extraction"].get("schema_version") != 2 for record in labels):
        raise ValueError("golden labels require extraction schema v2")
    gold = [Extraction.model_validate(record["extraction"]) for record in labels]
    for text, extraction in zip(texts, gold, strict=True):
        validate_grounding(text, extraction)
    results = []
    for configuration in configurations:
        started = perf_counter()
        predictions = [provider.extract(text, configuration) for text in texts]
        results.append(
            {
                "configuration": configuration,
                "metrics": score(predictions, gold, texts),
                "elapsed_seconds": perf_counter() - started,
                "tokens": None,
                "estimated_cost": None,
            }
        )
    return {
        "mode": "fixture replay — plumbing regression, not live LLM quality",
        "dataset_size": len(labels),
        "results": results,
    }
