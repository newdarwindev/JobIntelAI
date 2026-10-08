import re
from datetime import date

from jobintel.candidate_matching import aggregate, match_tenure, result
from jobintel.normalization import Taxonomy
from jobintel.schemas import CandidateProfile, Requirement


def capability_state(records, requirement, complete):
    signatures = {(r.current_capability, r.production_evidence) for r in records}
    if len(signatures) > 1:
        return "UNKNOWN", "Conflicting capability or production statements."
    if not records:
        return ("MISSING" if complete else "UNKNOWN"), "No sourced capability record."
    record = records[0]
    states = {"unknown": "UNKNOWN", "none": "MISSING", "basic": "PARTIAL"}
    if record.current_capability in states:
        return states[
            record.current_capability
        ], "Current capability is " + record.current_capability + "."
    if requirement.explicit_production_required is True:
        return (
            {"confirmed": "COVERED", "unknown": "UNKNOWN", "limited": "PARTIAL", "none": "PARTIAL"}[
                record.production_evidence
            ],
            "Strong current capability; required production evidence is "
            + record.production_evidence
            + ".",
        )
    return "COVERED", "Strong sourced current capability; production is not mandatory."


def match_branch(requirement, skill, profile, taxonomy, as_of):
    records = [
        r for r in profile.evidence if taxonomy.canonical(r.skill) == taxonomy.canonical(skill)
    ]
    state, explanation = capability_state(records, requirement, profile.complete)
    predicates = [
        result(
            state,
            "capability_production",
            explanation,
            records,
            requirement.evidence,
            skill=skill,
            contradictory=len({(r.current_capability, r.production_evidence) for r in records}) > 1,
        )
    ]
    if requirement.years_required:
        predicates.append(match_tenure(requirement, skill, profile, taxonomy, as_of))
    unsupported = (
        requirement.version_constraints
        or re.search(r"\d+\.\d+", skill)
        or requirement.requirement_type.value == "OTHER"
    )
    if unsupported:
        predicates.append(
            result(
                "UNKNOWN",
                "unsupported",
                "Version or OTHER requirement has no supported candidate predicate.",
                [],
                requirement.evidence,
                skill=skill,
            )
        )
    # A contradiction must abstain even when another axis demonstrates a deficit.
    status = "UNKNOWN" if unsupported else aggregate([p["status"] for p in predicates])
    contradictory = any(p.get("contradictory", False) for p in predicates)
    if contradictory:
        status = "UNKNOWN"
    return {
        "skill": skill,
        "status": status,
        "predicates": predicates,
        "contradictory": contradictory,
    }


def match_requirement(
    requirement: Requirement,
    profile: CandidateProfile,
    taxonomy: Taxonomy,
    as_of: date | None = None,
    eligibility: list | None = None,
) -> dict:
    if requirement.requirement_type.value == "OTHER" and requirement.operator == "SINGLE":
        facts = [
            f
            for f in eligibility or []
            if f["requirement_evidence"] == requirement.evidence.model_dump()
        ]
        if facts:
            status = (
                "UNKNOWN"
                if any(f.get("contradictory", False) for f in facts)
                else aggregate([f["status"] for f in facts])
            )
            return {
                "status": status,
                "skills": requirement.skills,
                "operator": requirement.operator,
                "requirement_evidence": requirement.evidence.model_dump(),
                "branches": [
                    {"skill": requirement.skills[0], "status": status, "predicates": facts}
                ],
                "candidate_sources": [r for f in facts for r in f["candidate_sources"]],
                "explanation": f"{status}: " + " ".join(f["explanation"] for f in facts),
            }
    branches = [
        match_branch(requirement, skill, profile, taxonomy, as_of or date.today())
        for skill in requirement.skills
    ]
    status = aggregate([b["status"] for b in branches], requirement.operator)
    if requirement.operator != "ANY" and any(b["contradictory"] for b in branches):
        status = "UNKNOWN"
    predicates = [p for b in branches for p in b["predicates"]]
    return {
        "status": status,
        "skills": requirement.skills,
        "operator": requirement.operator,
        "requirement_evidence": requirement.evidence.model_dump(),
        "branches": branches,
        "candidate_sources": [s for p in predicates for s in p["candidate_sources"]],
        "explanation": f"{status}: {requirement.operator} branches; "
        + " ".join(p["explanation"] for p in predicates),
    }
