import pytest

from jobintel.matching import match_requirement
from jobintel.schemas import CandidateEvidence, CandidateProfile, RequirementType, Years


def profile(capability="strong", production="confirmed", complete=False, skill="Python"):
    return CandidateProfile(
        profile_id="synthetic",
        complete=complete,
        evidence=[
            CandidateEvidence(
                skill=skill,
                current_capability=capability,
                production_evidence=production,
                source="synthetic://example",
                quote="Explicit authored evidence.",
            )
        ],
    )


@pytest.mark.parametrize(
    "capability,production,required,expected",
    [
        ("strong", "confirmed", True, "COVERED"),
        ("strong", "limited", True, "PARTIAL"),
        ("strong", "none", True, "PARTIAL"),
        ("strong", "unknown", True, "UNKNOWN"),
        ("basic", "confirmed", True, "PARTIAL"),
        ("none", "confirmed", False, "MISSING"),
        ("unknown", "confirmed", False, "UNKNOWN"),
        ("strong", "none", None, "COVERED"),
    ],
)
def test_capability_is_independent_from_history(
    requirement, taxonomy, capability, production, required, expected
):
    requirement = requirement.model_copy(update={"explicit_production_required": required})
    result = match_requirement(requirement, profile(capability, production), taxonomy)
    assert result["status"] == expected
    assert result["candidate_sources"][0]["source"] == "synthetic://example"


def test_absence_unknown_until_profile_complete(requirement, taxonomy):
    empty = CandidateProfile(profile_id="x", evidence=[])
    assert match_requirement(requirement, empty, taxonomy)["status"] == "UNKNOWN"
    empty.complete = True
    assert match_requirement(requirement, empty, taxonomy)["status"] == "MISSING"


def test_alternatives_are_not_conjunctions(requirement, taxonomy):
    grouped = requirement.model_copy(update={"skills": ["Python", "SQL"], "operator": "ANY"})
    assert match_requirement(grouped, profile(complete=True), taxonomy)["status"] == "COVERED"
    grouped.operator = "ALL"
    assert match_requirement(grouped, profile(complete=True), taxonomy)["status"] == "MISSING"


def test_conflicting_records_and_unimplemented_predicates_abstain(requirement, taxonomy):
    candidate = profile()
    candidate.evidence.append(profile("none").evidence[0])
    assert match_requirement(requirement, candidate, taxonomy)["status"] == "UNKNOWN"
    requirement.years_required = Years(minimum=3)
    assert match_requirement(requirement, profile(), taxonomy)["status"] == "UNKNOWN"
    requirement.years_required = None
    requirement.requirement_type = RequirementType.OTHER
    assert match_requirement(requirement, profile(), taxonomy)["status"] == "UNKNOWN"
