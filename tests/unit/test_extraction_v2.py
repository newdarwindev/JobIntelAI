"""V19, V21-V23: source-grounded metadata, obligations, and version predicates."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from jobintel.compatibility import stored_extraction
from jobintel.experiments import rescore
from jobintel.matching import match_requirement
from jobintel.normalization import Taxonomy
from jobintel.schemas import CandidateProfile, Extraction, Requirement
from jobintel.snapshots import GroundingError, validate_grounding


def evidence(text, quote):
    start = text.index(quote)
    return {"start": start, "end": start + len(quote), "quote": quote}


def requirement(quote, **updates):
    return Requirement.model_validate(
        {
            "raw_text": quote,
            "normalized_skill_or_requirement": "Python",
            "skills": ["Python"],
            "requirement_type": "EXPERIENCE",
            "category": "backend",
            "confidence": 1,
            "evidence": evidence(quote, quote),
            **updates,
        }
    )


def test_v19_unicode_non_bmp_metadata_and_filters():
    text = "🧪 café\nRemote work within Georgia only.\nEU work authorization is required."
    quote = "Remote work within Georgia only."
    result = Extraction(
        requirements=[],
        geography={"value": "Georgia", "evidence": evidence(text, quote)},
        work_mode={"value": "remote", "evidence": evidence(text, quote)},
        filters=[
            {
                "kind": "work_authorization",
                "value": "EU work authorization",
                "evidence": evidence(text, "EU work authorization is required."),
            }
        ],
    )
    validate_grounding(text, result)
    with pytest.raises(GroundingError):
        validate_grounding("x" + text, result)


@pytest.mark.parametrize(
    "quote,value",
    [
        ("Company address: Berlin.", "Berlin"),
        ("Our headquarters are in Berlin.", "Berlin"),
        ("Our remote offices are in Berlin.", "Berlin"),
        ("The job may be based in Berlin.", "Berlin"),
        ("The role is in Georgia or Armenia.", "Georgia"),
        ("The job is in Georgian territory.", "Georgia"),
        ("Our job postings mention Berlin.", "Berlin"),
    ],
)
def test_v19_irrelevant_or_ambiguous_geography_cannot_be_claimed(quote, value):
    result = Extraction(
        requirements=[], geography={"value": value, "evidence": evidence(quote, quote)}
    )
    with pytest.raises(GroundingError):
        validate_grounding(quote, result)
    validate_grounding(quote, Extraction(requirements=[]))


@pytest.mark.parametrize(
    "quote",
    [
        "Our company has remote offices.",
        "The job is not remote.",
        "The job is remote or hybrid.",
        "The job may be remote.",
    ],
)
def test_v19_work_mode_must_describe_an_unambiguous_job(quote):
    result = Extraction(
        requirements=[], work_mode={"value": "remote", "evidence": evidence(quote, quote)}
    )
    with pytest.raises(GroundingError):
        validate_grounding(quote, result)


def test_v19_strict_metadata_requires_evidence():
    for field in ["geography", "work_mode"]:
        with pytest.raises(ValidationError):
            Extraction.model_validate({"requirements": [], field: {"value": "remote"}})
    with pytest.raises(ValidationError):
        Extraction.model_validate(
            {"requirements": [], "filters": [{"kind": "travel", "value": "20%"}]}
        )
    with pytest.raises(ValidationError):
        Extraction.model_validate({"requirements": [], "schema_version": 3})


@pytest.mark.parametrize("kind,obligation", [("required", "MUST"), ("preferred", "PREFERRED")])
def test_v21_years_and_obligation_are_distinct(kind, obligation):
    quote = f"Three or more years of Python experience is {kind}."
    row = requirement(quote, years_required={"minimum": 3}, experience_obligation=obligation)
    validate_grounding(quote, Extraction(requirements=[row]))
    invalid = row.model_copy(
        update={"experience_obligation": "PREFERRED" if obligation == "MUST" else "MUST"}
    )
    with pytest.raises(GroundingError):
        validate_grounding(quote, Extraction(requirements=[invalid]))
    with pytest.raises(GroundingError):
        validate_grounding(
            quote, Extraction(requirements=[requirement(quote, years_required={"minimum": 5})])
        )


@pytest.mark.parametrize(
    "kind,obligation,mandatory",
    [
        ("required", "MUST", True),
        ("preferred", "PREFERRED", False),
    ],
)
def test_v21_production_preference_is_not_necessity(kind, obligation, mandatory):
    quote = f"Production experience with Python is {kind}."
    row = requirement(
        quote,
        experience_obligation=obligation,
        production_obligation=obligation,
        explicit_production_required=mandatory,
    )
    validate_grounding(quote, Extraction(requirements=[row]))
    bad = row.model_copy(update={"explicit_production_required": not mandatory})
    with pytest.raises(GroundingError):
        validate_grounding(quote, Extraction(requirements=[bad]))


def test_v21_absent_predicates_remain_unknown():
    quote = "Python experience."
    row = requirement(quote)
    validate_grounding(quote, Extraction(requirements=[row]))
    assert row.experience_obligation == row.production_obligation == "UNKNOWN"
    assert row.years_required is row.explicit_production_required is None
    with pytest.raises(GroundingError):
        validate_grounding(
            quote,
            Extraction(requirements=[row.model_copy(update={"experience_obligation": "MUST"})]),
        )


def test_v21_upper_bound_is_not_a_minimum():
    quote = "Up to three years of Python experience is preferred."
    row = requirement(quote, years_required={"minimum": 3}, experience_obligation="PREFERRED")
    with pytest.raises(GroundingError):
        validate_grounding(quote, Extraction(requirements=[row]))


def version_requirement(phrase="Python 3.11+", product="Python", source_product="Python"):
    quote = phrase + " is required."
    return requirement(
        quote,
        skills=[phrase],
        requirement_type="MUST",
        version_constraints=[
            {
                "skill": phrase,
                "product": product,
                "source_product": source_product,
                "raw_text": phrase,
                "comparator": "GTE",
                "version": "3.11",
                "evidence": evidence(quote, phrase),
            }
        ],
    )


def test_v22_versions_are_explicit_and_not_unversioned(taxonomy):
    row = version_requirement()
    validate_grounding(row.raw_text, Extraction(requirements=[row]))
    normalized = taxonomy.normalize(row)
    assert normalized.skills == ["Python 3.11+"]
    assert normalized.version_constraints[0].comparator == "GTE"
    assert normalized.raw_text == row.raw_text
    assert normalized.evidence == row.evidence
    plain = requirement("Python is required.", requirement_type="MUST")
    assert normalized.skills != plain.skills
    bad = row.model_copy(update={"version_constraints": []})
    with pytest.raises(GroundingError):
        validate_grounding(row.raw_text, Extraction(requirements=[bad]))


def test_v22_no_partial_version_drop_or_wrong_comparator():
    row = version_requirement()
    changed = row.version_constraints[0].model_copy(update={"comparator": "EQ"})
    with pytest.raises(GroundingError):
        validate_grounding(
            row.raw_text,
            Extraction(requirements=[row.model_copy(update={"version_constraints": [changed]})]),
        )
    quote = "Python 3.11+ or Python 2.7 is required."
    bad = requirement(
        quote,
        skills=["Python 3.11+", "Python 2.7"],
        operator="ANY",
        version_constraints=[row.version_constraints[0]],
    )
    with pytest.raises(GroundingError):
        validate_grounding(quote, Extraction(requirements=[bad]))


@pytest.mark.parametrize("operator", ["ANY", "ALL"])
def test_v23_alias_deduplication_preserves_group_operator(taxonomy, operator):
    row = requirement(
        "Postgres or PostgreSQL experience.", skills=["Postgres", "PostgreSQL"], operator=operator
    )
    result = taxonomy.normalize(row)
    assert result.skills == ["PostgreSQL"]
    assert result.source_skills == ["Postgres", "PostgreSQL"]
    assert result.operator == operator
    assert result.raw_text == row.raw_text
    assert taxonomy.normalize(result) == result


def test_v23_colliding_aliases_fail_and_products_stay_distinct(taxonomy):
    with pytest.raises(ValueError, match="ambiguous taxonomy alias"):
        Taxonomy.from_records(
            [
                {"canonical": "AWS", "aliases": ["shared"]},
                {"canonical": "AWS Bedrock", "aliases": [" SHARED "]},
            ]
        )
    row = requirement(
        "AWS and AWS Bedrock experience.", skills=["AWS", "AWS Bedrock"], operator="ALL"
    )
    assert taxonomy.normalize(row).skills == ["AWS", "AWS Bedrock"]


@pytest.mark.parametrize("operator", ["ANY", "ALL"])
def test_v22_v23_incompatible_versions_keep_their_branches(taxonomy, operator):
    quote = "Python 3.11+ or Python 2.7 is required."
    versions = [
        {
            "skill": phrase,
            "product": "Python",
            "source_product": "Python",
            "raw_text": phrase,
            "comparator": comparator,
            "version": version,
            "evidence": evidence(quote, phrase),
        }
        for phrase, comparator, version in [
            ("Python 3.11+", "GTE", "3.11"),
            ("Python 2.7", "EQ", "2.7"),
        ]
    ]
    row = requirement(
        quote,
        skills=["Python 3.11+", "Python 2.7"],
        operator=operator,
        version_constraints=versions,
    )
    validate_grounding(quote, Extraction(requirements=[row]))
    result = taxonomy.normalize(row)
    assert result.operator == operator
    assert result.skills == ["Python 3.11+", "Python 2.7"]
    assert [(v.product, v.comparator, v.version) for v in result.version_constraints] == [
        ("Python", "GTE", "3.11"),
        ("Python", "EQ", "2.7"),
    ]


def test_v19_legacy_read_has_no_invented_evidence_or_history_mutation():
    legacy = {
        "requirements": [requirement("Python experience.").model_dump(mode="json")],
        "responsibilities": [],
        "geography": "Berlin",
        "work_mode": "remote",
    }
    legacy["requirements"][0]["explicit_production_required"] = True
    original = deepcopy(legacy)
    result = stored_extraction(legacy)
    assert result.schema_version == 2
    assert result.geography is result.work_mode is result.filters is None
    assert result.requirements[0].explicit_production_required is None
    assert legacy == original


def test_v19_historical_v1_experiment_hashes_and_scores_still_reproduce():
    root = Path(__file__).resolve().parents[2] / "results/experiments/fake"
    report = json.loads((root / "report.json").read_text())
    original = deepcopy(report)
    assert rescore(report) == json.loads((root / "scores.json").read_text())
    assert report == original


def test_v22_opaque_legacy_versions_cannot_claim_candidate_coverage(taxonomy):
    row = requirement("Python 3.11+ is required.", skills=["Python 3.11+"], requirement_type="MUST")
    profile = CandidateProfile(
        profile_id="synthetic",
        complete=True,
        evidence=[
            {
                "skill": "Python 3.11+",
                "current_capability": "strong",
                "production_evidence": "confirmed",
                "source": "synthetic://profile",
                "quote": "Authored generic skill record.",
            }
        ],
    )
    assert match_requirement(row, profile, taxonomy)["status"] == "UNKNOWN"
