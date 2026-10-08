"""Sourced tenure and exact-scope eligibility; no employer or geographic inference."""

import calendar
from datetime import date

from jobintel.schemas import CandidateProfile


def aggregate(states, operator="ALL"):
    order = (
        ["COVERED", "PARTIAL", "UNKNOWN", "MISSING"]
        if operator == "ANY"
        else ["MISSING", "UNKNOWN", "PARTIAL", "COVERED"]
    )
    return next((s for s in order if s in states), "UNKNOWN")


def result(status, predicate, explanation, records, requirement_evidence, **details):
    return {
        "status": status,
        "predicate": predicate,
        "explanation": explanation,
        "requirement_evidence": requirement_evidence.model_dump(),
        "candidate_sources": [r.model_dump(mode="json") for r in records],
        **details,
    }


def anniversary(start, year):
    return start.replace(year=year, day=min(start.day, calendar.monthrange(year, start.month)[1]))


def calendar_years(start, end):
    years = end.year - start.year
    if anniversary(start, start.year + years) > end:
        years -= 1
    anchor = anniversary(start, start.year + years)
    if anchor == end:
        return float(years)
    if anchor.year == 9999:
        return years + (end - anchor).days / 365
    following = anniversary(start, anchor.year + 1)
    return years + (end - anchor).days / (following - anchor).days


def merged_years(records):
    intervals = sorted((r.start, r.end) for r in records)
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return sum(calendar_years(start, end) for start, end in merged)


def tenure_state(records, required, complete, as_of):
    statuses = {r.status for r in records}
    if "unknown" in statuses or {"confirmed", "none"} <= statuses:
        return "UNKNOWN", None, "Unknown or contradictory tenure statements."
    if any(not r.start or not r.end or r.end > as_of for r in records if r.status == "confirmed"):
        return "UNKNOWN", None, "Tenure dates are missing or extend beyond the assessment date."
    years = merged_years([r for r in records if r.status == "confirmed"])
    if required.maximum is not None and years > required.maximum:
        return "MISSING", years, "Documented tenure exceeds the inclusive maximum."
    if years >= required.minimum and (required.maximum is None or complete):
        return "COVERED", years, "Documented tenure satisfies the inclusive years predicate."
    if not complete:
        return "UNKNOWN", years, "Incomplete tenure cannot establish a deficit or upper bound."
    return ("PARTIAL" if years else "MISSING"), years, "Documented tenure is below the minimum."


def match_tenure(requirement, skill, profile, taxonomy, as_of):
    kind = "production" if requirement.explicit_production_required is True else "experience"
    records = [
        r
        for r in profile.tenure
        if taxonomy.canonical(r.skill) == taxonomy.canonical(skill) and r.kind == kind
    ]
    # Completeness can establish absence, never supply positive unsourced experience.
    if not records:
        state, years, explanation = (
            "MISSING" if profile.tenure_complete else "UNKNOWN",
            None,
            "No sourced tenure for this skill and experience kind.",
        )
    else:
        state, years, explanation = tenure_state(
            records, requirement.years_required, profile.tenure_complete, as_of
        )
    return result(
        state,
        "tenure",
        explanation,
        records,
        requirement.evidence,
        skill=skill,
        kind=kind,
        documented_years=years,
        years_required=requirement.years_required.model_dump(),
        contradictory={"confirmed", "none"} <= {r.status for r in records},
    )


def scope(value):
    return " ".join(value.split()).casefold()


def match_eligibility(kind, fact, profile: CandidateProfile, as_of: date):
    records = [
        r for r in profile.eligibility if r.kind == kind and scope(r.value) == scope(fact.value)
    ]
    states = {r.status for r in records}
    dated = all(
        r.observed_on <= as_of and (not r.valid_until or r.valid_until >= as_of) for r in records
    )
    if not records:
        state = "MISSING" if kind in profile.eligibility_complete else "UNKNOWN"
        explanation = "No sourced statement for this exact eligibility scope."
    elif not dated or "unknown" in states or len(states) > 1:
        state = "UNKNOWN"
        explanation = "Statements conflict, are unknown, or are not valid on the assessment date."
    else:
        state = "COVERED" if states == {"confirmed"} else "MISSING"
        explanation = (
            "Exact sourced eligibility scope is confirmed."
            if state == "COVERED"
            else "Exact sourced eligibility scope is denied."
        )
    return result(
        state,
        kind,
        explanation,
        records,
        fact.evidence,
        value=fact.value,
        contradictory=len(states) > 1,
    )


def match_filters(extraction, profile, as_of):
    facts = []
    if extraction.geography:
        facts.append(match_eligibility("location", extraction.geography, profile, as_of))
    facts.extend(match_eligibility(f.kind, f, profile, as_of) for f in extraction.filters or [])
    return facts
