"""V24-V26: sourced predicates, separate axes and conservative unknowns."""

from datetime import date

import pytest
from pydantic import ValidationError

from jobintel.candidate_matching import match_filters
from jobintel.matching import match_requirement
from jobintel.schemas import CandidateProfile, Extraction, GeographyValue, Years

AS_OF = date(2025, 1, 1)


def profile(periods=(), *, complete=True, capability="strong", production="confirmed"):
    return CandidateProfile.model_validate(
        {
            "profile_id": "synthetic-predicates",
            "complete": True,
            "evidence": [
                {
                    "skill": "Python",
                    "current_capability": capability,
                    "production_evidence": production,
                    "source": "synthetic://capability",
                    "quote": "Authored capability statement; employer prestige is not tenure.",
                }
            ],
            "tenure_complete": complete,
            "tenure": [
                {
                    "skill": "Python",
                    "start": start,
                    "end": end,
                    "source": "synthetic://dated-period",
                    "quote": "Authored dated experience.",
                }
                for start, end in periods
            ],
        }
    )


@pytest.mark.parametrize(
    "periods,minimum,maximum,complete,expected",
    [
        ([("2020-01-01", "2023-01-01")], 3, None, True, "COVERED"),
        ([("2021-01-01", "2024-01-01")], 3, 3, True, "COVERED"),
        ([("2020-02-29", "2023-02-28")], 3, None, True, "COVERED"),
        ([("2020-01-01", "2022-01-01"), ("2021-01-01", "2023-01-01")], 4, None, True, "PARTIAL"),
        ([("2020-01-01", "2022-01-01"), ("2022-01-01", "2023-01-01")], 3, 3, True, "COVERED"),
        ([("2020-01-01", "2022-01-01")], 3, None, False, "UNKNOWN"),
        ([("2020-01-01", "2024-01-01")], 3, None, False, "COVERED"),
        ([("2020-01-01", "2024-01-01")], 3, 5, False, "UNKNOWN"),
        ([("2020-01-01", "2024-01-01")], 2, 3, True, "MISSING"),
        ([("2020-01-01", None)], 3, None, True, "UNKNOWN"),
        ([(None, "2024-01-01")], 3, None, True, "UNKNOWN"),
        ([("2020-01-01", "2026-01-01")], 3, None, True, "UNKNOWN"),
        ([], 3, None, False, "UNKNOWN"),
        ([], 3, None, True, "MISSING"),
    ],
)
def test_v24_tenure_bounds_overlap_missing_dates(
    requirement, taxonomy, periods, minimum, maximum, complete, expected
):
    requirement.years_required = Years(minimum=minimum, maximum=maximum)
    requirement.explicit_production_required = False
    matched = match_requirement(requirement, profile(periods, complete=complete), taxonomy, AS_OF)
    assert matched["status"] == expected
    predicate = matched["branches"][0]["predicates"][1]
    assert predicate["requirement_evidence"] == requirement.evidence.model_dump()
    assert len(predicate["candidate_sources"]) == len(periods)
    if len(periods) == 2:
        assert predicate["documented_years"] == 3


def test_v24_no_employer_or_capability_tenure_inference(requirement, taxonomy):
    requirement.years_required = Years(minimum=3)
    assert (
        match_requirement(requirement, profile(complete=False), taxonomy, AS_OF)["status"]
        == "UNKNOWN"
    )
    candidate = profile([("2020-01-01", "2024-01-01")])
    candidate.tenure.append(
        candidate.tenure[0].model_copy(update={"status": "none", "start": None, "end": None})
    )
    assert match_requirement(requirement, candidate, taxonomy, AS_OF)["status"] == "UNKNOWN"


@pytest.mark.parametrize(
    "capability,production,expected",
    [
        ("basic", "confirmed", "PARTIAL"),
        ("strong", "none", "PARTIAL"),
        ("strong", "unknown", "UNKNOWN"),
    ],
)
def test_v26_production_years_do_not_replace_current_capability(
    requirement, taxonomy, capability, production, expected
):
    requirement.years_required = Years(minimum=3)
    requirement.explicit_production_required = True
    candidate = profile(
        [("2020-01-01", "2024-01-01")], capability=capability, production=production
    )
    candidate.tenure[0].kind = "production"
    assert match_requirement(requirement, candidate, taxonomy, AS_OF)["status"] == expected
    candidate.tenure[0].kind = "experience"
    assert match_requirement(requirement, candidate, taxonomy, AS_OF)["status"] != "COVERED"


def test_v24_any_sufficient_tenure_all_requires_each_branch(requirement, taxonomy):
    requirement.years_required = Years(minimum=3)
    requirement.explicit_production_required = False
    requirement.skills = ["Python", "SQL"]
    requirement.operator = "ANY"
    candidate = profile([("2020-01-01", "2024-01-01")])
    assert match_requirement(requirement, candidate, taxonomy, AS_OF)["status"] == "COVERED"
    requirement.operator = "ALL"
    assert match_requirement(requirement, candidate, taxonomy, AS_OF)["status"] == "MISSING"


@pytest.mark.parametrize(
    "kind", ["location", "work_authorization", "travel", "residency", "attendance"]
)
@pytest.mark.parametrize(
    "statuses,complete,expected",
    [
        (["confirmed"], False, "COVERED"),
        (["denied"], False, "MISSING"),
        (["unknown"], True, "UNKNOWN"),
        (["confirmed", "denied"], True, "UNKNOWN"),
        ([], False, "UNKNOWN"),
        ([], True, "MISSING"),
    ],
)
def test_v25_scoped_eligibility_states(requirement, kind, statuses, complete, expected):
    fact = {"value": "Georgia", "evidence": requirement.evidence.model_dump()}
    extraction = (
        Extraction(requirements=[], geography=GeographyValue(**fact))
        if kind == "location"
        else Extraction(requirements=[], filters=[{"kind": kind, **fact}])
    )
    candidate = CandidateProfile.model_validate(
        {
            "profile_id": "synthetic",
            "evidence": [],
            "eligibility_complete": [kind] if complete else [],
            "eligibility": [
                {
                    "kind": kind,
                    "value": "  georgia ",
                    "status": status,
                    "observed_on": "2020-01-01",
                    "source": "synthetic://eligibility",
                    "quote": "Explicit authored eligibility statement.",
                }
                for status in statuses
            ],
        }
    )
    matched = match_filters(extraction, candidate, AS_OF)[0]
    assert matched["status"] == expected
    assert matched["requirement_evidence"] == requirement.evidence.model_dump()
    assert len(matched["candidate_sources"]) == len(statuses)


@pytest.mark.parametrize(
    "change",
    [{"value": "United States"}, {"observed_on": "2026-01-01"}, {"valid_until": "2024-12-31"}],
)
def test_v25_wrong_scope_future_and_expired_cannot_cover(requirement, change):
    extraction = Extraction(
        requirements=[], geography=GeographyValue(value="Georgia", evidence=requirement.evidence)
    )
    candidate = CandidateProfile.model_validate(
        {
            "profile_id": "synthetic",
            "evidence": [],
            "eligibility": [
                {
                    "kind": "location",
                    "value": "Georgia",
                    "status": "confirmed",
                    "observed_on": "2020-01-01",
                    "source": "synthetic://dated",
                    "quote": "Authored location statement.",
                    **change,
                }
            ],
        }
    )
    assert match_filters(extraction, candidate, AS_OF)[0]["status"] == "UNKNOWN"


@pytest.mark.parametrize(
    "record",
    [
        {
            "skill": "Python",
            "start": "2024-01-01",
            "end": "2020-01-01",
            "source": "synthetic://x",
            "quote": "dates",
        },
        {"skill": "Python", "source": "", "quote": "unsourced"},
        {
            "skill": "Python",
            "status": "none",
            "start": "2020-01-01",
            "source": "synthetic://x",
            "quote": "dates",
        },
        {
            "skill": "Python",
            "employer": "Prestigious",
            "source": "synthetic://x",
            "quote": "employer",
        },
    ],
)
def test_v24_strict_tenure_rejects_malformed_or_unsourced(record):
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            {"profile_id": "synthetic", "evidence": [], "tenure": [record]}
        )


def test_v26_all_contradiction_abstains_even_with_missing_other_branch(requirement, taxonomy):
    candidate = profile()
    candidate.evidence.append(
        candidate.evidence[0].model_copy(update={"current_capability": "none"})
    )
    requirement.skills = ["Python", "SQL"]
    requirement.operator = "ALL"
    assert match_requirement(requirement, candidate, taxonomy, AS_OF)["status"] == "UNKNOWN"


def test_v25_other_uses_only_matching_grounded_fact(requirement, taxonomy):
    from jobintel.schemas import RequirementType

    requirement.requirement_type = RequirementType.OTHER
    candidate = profile()
    sourced_fact = {
        "predicate": "location",
        "status": "COVERED",
        "requirement_evidence": requirement.evidence.model_dump(),
        "candidate_sources": [{"source": "synthetic://scope", "quote": "Authored location"}],
        "explanation": "Exact scope confirmed.",
    }
    assert (
        match_requirement(requirement, candidate, taxonomy, AS_OF, [sourced_fact])["status"]
        == "COVERED"
    )
    sourced_fact["requirement_evidence"] = {"start": 0, "end": 1, "quote": "x"}
    assert (
        match_requirement(requirement, candidate, taxonomy, AS_OF, [sourced_fact])["status"]
        == "UNKNOWN"
    )


@pytest.mark.parametrize(
    "as_of,expected",
    [
        ("2020-01-01", "COVERED"),
        ("2024-12-31", "COVERED"),
        ("2019-12-31", "UNKNOWN"),
        ("2025-01-01", "UNKNOWN"),
    ],
)
def test_v25_inclusive_observation_expiry_boundaries(requirement, as_of, expected):
    extraction = Extraction(
        requirements=[], geography=GeographyValue(value="Georgia", evidence=requirement.evidence)
    )
    candidate = CandidateProfile.model_validate(
        {
            "profile_id": "synthetic",
            "evidence": [],
            "eligibility": [
                {
                    "kind": "location",
                    "value": "Georgia",
                    "status": "confirmed",
                    "observed_on": "2020-01-01",
                    "valid_until": "2024-12-31",
                    "source": "synthetic://dated",
                    "quote": "Authored dated location.",
                }
            ],
        }
    )
    assert match_filters(extraction, candidate, date.fromisoformat(as_of))[0]["status"] == expected


def test_v24_alias_periods_merge_without_double_counting(requirement, taxonomy):
    requirement.skills = ["PostgreSQL"]
    requirement.years_required = Years(minimum=4)
    requirement.explicit_production_required = False
    candidate = profile([("2020-01-01", "2022-01-01"), ("2021-01-01", "2023-01-01")])
    candidate.evidence[0].skill = "Postgres"
    candidate.tenure[0].skill = "Postgres"
    candidate.tenure[1].skill = "PostgreSQL"
    matched = match_requirement(requirement, candidate, taxonomy, AS_OF)
    assert matched["status"] == "PARTIAL"
    assert matched["branches"][0]["predicates"][1]["documented_years"] == 3
