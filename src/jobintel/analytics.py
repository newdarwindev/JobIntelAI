from collections import defaultdict


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
        "scope": "Loaded corpus only; no market-wide conclusions. Gap counts and slices are planned.",
    }
