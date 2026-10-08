import json
from collections import defaultdict
from hashlib import sha256


def skill_counts(jobs: list[dict]) -> dict:
    # Denominator is distinct jobs with a successful extraction of their latest snapshot.
    counts = defaultdict(
        lambda: {"n": 0, "must_n": 0, "preferred_n": 0, "experience_n": 0, "other_n": 0}
    )
    alternatives = []
    for job in jobs:
        seen = set()
        typed = set()
        for requirement in job["requirements"]:
            if requirement["operator"] == "ANY":
                alternatives.append(
                    {
                        "job_id": job["job_id"],
                        "skills": requirement["skills"],
                        "requirement_type": requirement["requirement_type"],
                    }
                )
                # Mentions in an alternative are not independent hard requirements.
                continue
            for skill in requirement["skills"]:
                key = (skill, requirement["requirement_type"])
                if skill not in seen:
                    counts[skill]["n"] += 1
                    seen.add(skill)
                if key not in typed:
                    counts[skill][requirement["requirement_type"].lower() + "_n"] += 1
                    typed.add(key)
    return {
        "N": len(jobs),
        "denominator": "jobs with successful extraction of latest snapshot",
        "skills": [
            {"skill": skill, "N": len(jobs), **values} for skill, values in sorted(counts.items())
        ],
        "alternatives": alternatives,
        "scope": "Loaded corpus only; no market-wide conclusions.",
    }


STATES = ("COVERED", "PARTIAL", "MISSING", "UNKNOWN")


def remote_selected(view, remote):
    if remote is None:
        return True
    mode = (view["extraction"] or {}).get("work_mode")
    return bool(mode) and (
        mode["value"] == "remote" if remote else mode["value"] in {"hybrid", "onsite"}
    )


def requirement_group(row):
    group = {
        key: row.get(key)
        for key in (
            "normalized_skill_or_requirement",
            "operator",
            "requirement_type",
            "category",
            "experience_obligation",
            "production_obligation",
            "explicit_production_required",
            "years_required",
        )
    }
    group["requirement"] = group.pop("normalized_skill_or_requirement")
    group["skills"] = sorted(row["skills"])
    group["version_constraints"] = sorted(
        [
            {k: v[k] for k in ("skill", "product", "comparator", "version")}
            for v in row.get("version_constraints", [])
        ],
        key=lambda v: json.dumps(v, sort_keys=True),
    )
    group["group_id"] = sha256(json.dumps(group, sort_keys=True).encode()).hexdigest()
    return group


def corpus_summaries(jobs, rows, matched_N):
    categories, groups = {}, {}
    eligible_ids = {job["job_id"] for job in jobs}
    for job in jobs:
        for category in {r["category"] for r in job["extraction"]["requirements"]}:
            categories.setdefault(category, set()).add(job["job_id"])
    for row in rows:
        if row["match_status"] is None:
            continue
        descriptor = requirement_group(row)
        group = groups.setdefault(
            descriptor["group_id"], {"descriptor": descriptor, "states": {s: set() for s in STATES}}
        )
        group["states"][row["match_status"]].add(row["job_id"])
    return {
        "clusters": {
            "N": len(eligible_ids),
            "denominator": "jobs with successful selected-source extraction",
            "clusters": [
                {
                    "category": category,
                    "n": len(ids),
                    "N": len(eligible_ids),
                    "fraction": len(ids) / len(eligible_ids) if eligible_ids else None,
                    "job_ids": sorted(ids),
                }
                for category, ids in sorted(categories.items())
            ],
        },
        "gaps": {
            "N": matched_N,
            "denominator": "jobs with an eligible saved match run for the selected revision",
            "groups": [
                {
                    **group["descriptor"],
                    **{s: len(ids) for s, ids in group["states"].items()},
                    "N": matched_N,
                    "job_ids_by_state": {s: sorted(ids) for s, ids in group["states"].items()},
                }
                for group in sorted(
                    groups.values(),
                    key=lambda g: (g["descriptor"]["requirement"], g["descriptor"]["group_id"]),
                )
            ],
        },
    }
