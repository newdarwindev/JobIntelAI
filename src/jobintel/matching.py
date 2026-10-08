import re

from jobintel.normalization import Taxonomy
from jobintel.schemas import CandidateProfile, Requirement


def match_requirement(
    requirement: Requirement, profile: CandidateProfile, taxonomy: Taxonomy
) -> dict:
    states = []
    sources = []
    for skill in requirement.skills:
        records = [
            e for e in profile.evidence if taxonomy.canonical(e.skill) == taxonomy.canonical(skill)
        ]
        # Multiple records can disagree. Abstain rather than cherry-pick the strongest.
        signatures = {(e.current_capability, e.production_evidence) for e in records}
        sources.extend(e.model_dump() for e in records)
        if len(signatures) > 1:
            state = "UNKNOWN"
        elif not records:
            state = "MISSING" if profile.complete else "UNKNOWN"
        else:
            record = records[0]
            if record.current_capability == "unknown":
                state = "UNKNOWN"
            elif record.current_capability == "none":
                state = "MISSING"
            elif record.current_capability == "basic":
                state = "PARTIAL"
            elif requirement.explicit_production_required is True:
                state = {
                    "confirmed": "COVERED",
                    "unknown": "UNKNOWN",
                    "limited": "PARTIAL",
                    "none": "PARTIAL",
                }[record.production_evidence]
            else:
                state = "COVERED"
        states.append(state)
    if requirement.operator == "ANY":
        state = next(
            (s for s in ["COVERED", "PARTIAL", "UNKNOWN", "MISSING"] if s in states), "UNKNOWN"
        )
    else:
        state = next(
            (s for s in ["MISSING", "UNKNOWN", "PARTIAL", "COVERED"] if s in states), "UNKNOWN"
        )
    # The scaffold has no candidate tenure/geography/work-authorization schema.
    # Never claim these predicates are covered merely because a skill is present.
    if (
        requirement.years_required is not None
        or requirement.version_constraints
        or any(re.search(r"\d+\.\d+", skill) for skill in requirement.skills)
        or requirement.requirement_type.value == "OTHER"
    ):
        state = "UNKNOWN"
    return {
        "status": state,
        "skills": requirement.skills,
        "operator": requirement.operator,
        "candidate_sources": sources,
        "explanation": f"{state}: explicit capability and production records only; absence is a gap only for a complete profile. Tenure and OTHER filters require future candidate predicates.",
    }
