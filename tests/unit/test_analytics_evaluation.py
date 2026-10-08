import pytest

from jobintel.analytics import skill_counts
from jobintel.evaluation import score
from jobintel.providers import FixtureProvider, ProviderUnavailable
from jobintel.schemas import Extraction


def test_counts_are_per_job_and_per_type(requirement):
    must = requirement.model_dump(mode="json")
    preferred = {**must, "requirement_type": "PREFERRED"}
    alternative = {**must, "skills": ["AWS", "Azure"], "operator": "ANY"}
    report = skill_counts(
        [
            {"job_id": "1", "requirements": [must, must, preferred, alternative]},
            {"job_id": "2", "requirements": []},
        ]
    )
    assert report["N"] == 2
    assert report["skills"] == [
        {
            "skill": "Python",
            "N": 2,
            "n": 1,
            "must_n": 1,
            "preferred_n": 1,
            "experience_n": 0,
            "other_n": 0,
        }
    ]
    assert report["alternatives"][0]["skills"] == ["AWS", "Azure"]
    assert skill_counts([])["N"] == 0


def test_metrics_detect_missing_duplicate_and_wrong_type(requirement):
    gold = Extraction(requirements=[requirement])
    text = " " * requirement.evidence.start + requirement.evidence.quote
    wrong_type = requirement.model_copy(update={"requirement_type": "PREFERRED"})
    report = score([Extraction(requirements=[wrong_type, wrong_type])], [gold], [text])
    assert report["precision"] == 0.5
    assert report["recall"] == 1
    assert report["type_accuracy"] == 0
    assert report["unsupported_span_rate"] == 0
    empty = score([Extraction(requirements=[])], [gold], [text])
    assert empty["precision"] is None and empty["recall"] == 0
    assert empty["semantic_hallucination_rate"] is None
    with pytest.raises(ValueError):
        score([], [], [])


def test_invalid_evidence_is_measured_not_hidden(requirement):
    gold = Extraction(requirements=[requirement])
    invalid = requirement.model_copy(
        update={"evidence": requirement.evidence.model_copy(update={"quote": "invented"})}
    )
    report = score(
        [Extraction(requirements=[invalid])],
        [gold],
        [" " * requirement.evidence.start + requirement.evidence.quote],
    )
    assert report["unsupported_span_rate"] == 1
    assert report["evidence_accuracy"] == 0


def test_fixture_provider_never_reads_golden_labels(tmp_path, provider):
    import shutil
    from pathlib import Path

    data = Path(__file__).resolve().parents[2] / "data"
    for name in ["provider_responses.json", "taxonomy.json"]:
        shutil.copy(data / name, tmp_path / name)
    independent = FixtureProvider(tmp_path)
    text = (data / "sample_jobs/SYN-01.txt").read_text()
    assert independent.extract(text, "fixture_normalized").requirements[1].skills == ["PostgreSQL"]
    with pytest.raises(ProviderUnavailable):
        independent.extract("A new real posting.", "fixture_normalized")
