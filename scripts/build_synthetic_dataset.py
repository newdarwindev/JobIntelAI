"""Rebuild explicitly authored synthetic examples. Never use this for live gold labels.

Fixture replay and gold share these authored examples, so their agreement only tests
the pipeline. Deliberately bad predictions belong in unit tests, not claimed results.
"""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"
TAXONOMY = [
    ("Python", ["python"], "backend"),
    ("PostgreSQL", ["Postgres", "postgresql"], "data"),
    ("Kubernetes", ["K8s", "kubernetes"], "infrastructure"),
    ("Generative AI", ["GenAI", "generative ai"], "AI/LLM"),
    ("AWS", ["aws"], "cloud"),
    ("AWS Bedrock", ["Amazon Bedrock"], "AI/LLM"),
    ("Azure", ["azure"], "cloud"),
    ("FastAPI", ["fastapi"], "backend"),
    ("Docker", ["docker"], "infrastructure"),
    ("SQL", ["sql"], "data"),
    ("Java", ["java"], "backend"),
    ("Go", ["Golang"], "backend"),
    ("LLM evaluation", [], "AI/LLM"),
    ("communication", [], "domain"),
]
# Each row is an explicit human-authored annotation: quote, type, skills, category,
# operator, production predicate, years range. Unknown is represented by None.
CASES = [
    [
        ("Python is required.", "MUST", ["Python"], "backend", "SINGLE", None, None),
        ("Postgres is nice to have.", "PREFERRED", ["Postgres"], "data", "SINGLE", None, None),
    ],
    [
        (
            "Experience with AWS or Azure is required.",
            "MUST",
            ["AWS", "Azure"],
            "cloud",
            "ANY",
            None,
            None,
        )
    ],
    [("You must know Python and SQL.", "MUST", ["Python", "SQL"], "backend", "ALL", None, None)],
    [
        (
            "Production experience with K8s is required.",
            "EXPERIENCE",
            ["K8s"],
            "infrastructure",
            "SINGLE",
            True,
            None,
        )
    ],
    [
        (
            "Three or more years of Python experience is required.",
            "EXPERIENCE",
            ["Python"],
            "backend",
            "SINGLE",
            None,
            {"minimum": 3, "maximum": None},
        )
    ],
    [
        (
            "Two to four years of Java experience is required.",
            "EXPERIENCE",
            ["Java"],
            "backend",
            "SINGLE",
            None,
            {"minimum": 2, "maximum": 4},
        )
    ],
    [("FastAPI is preferred.", "PREFERRED", ["FastAPI"], "backend", "SINGLE", None, None)],
    [
        ("AWS Bedrock is required.", "MUST", ["AWS Bedrock"], "AI/LLM", "SINGLE", None, None),
        ("AWS is preferred.", "PREFERRED", ["AWS"], "cloud", "SINGLE", None, None),
    ],
    [("GenAI is a bonus.", "PREFERRED", ["GenAI"], "AI/LLM", "SINGLE", None, None)],
    [
        (
            "Remote work within Georgia only.",
            "OTHER",
            ["Georgia residency"],
            "geography",
            "SINGLE",
            None,
            None,
        )
    ],
    [
        (
            "Onsite in Berlin three days weekly.",
            "OTHER",
            ["Berlin attendance"],
            "geography",
            "SINGLE",
            None,
            None,
        )
    ],
    [
        (
            "Existing EU work authorization is required.",
            "OTHER",
            ["EU work authorization"],
            "geography",
            "SINGLE",
            None,
            None,
        )
    ],
    [
        (
            "Travel up to 20 percent is required.",
            "OTHER",
            ["travel up to 20%"],
            "geography",
            "SINGLE",
            None,
            None,
        )
    ],
    [
        ("Docker is required.", "MUST", ["Docker"], "infrastructure", "SINGLE", None, None),
        (
            "Production experience with Docker is preferred.",
            "PREFERRED",
            ["Docker"],
            "infrastructure",
            "SINGLE",
            True,
            None,
        ),
    ],
    [("Golang is required.", "MUST", ["Golang"], "backend", "SINGLE", None, None)],
    [("LLM evaluation is required.", "MUST", ["LLM evaluation"], "AI/LLM", "SINGLE", None, None)],
    [
        (
            "Python is preferred, not mandatory.",
            "PREFERRED",
            ["Python"],
            "backend",
            "SINGLE",
            None,
            None,
        )
    ],
    [],  # Deliberate abstention: a product mentioning technology is not a requirement.
    [
        (
            "Clear communication is required.",
            "MUST",
            ["communication"],
            "domain",
            "SINGLE",
            None,
            None,
        )
    ],
    [
        (
            "Python is required — café systems experience is not required.",
            "MUST",
            ["Python"],
            "backend",
            "SINGLE",
            None,
            None,
        )
    ],
]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main(root=ROOT):
    (root / "sample_jobs").mkdir(parents=True, exist_ok=True)
    taxonomy = [
        {"canonical": name, "aliases": aliases, "category": category}
        for name, aliases, category in TAXONOMY
    ]
    write_json(root / "taxonomy.json", taxonomy)
    aliases = {s.casefold(): name for name, names, _ in TAXONOMY for s in [name, *names]}
    golden, responses, registry = [], {}, []
    for number, annotations in enumerate(CASES, 1):
        job_id = f"SYN-{number:02d}"
        heading = f"Synthetic company {number:02d} — Backend / AI Engineer"
        context = (
            "Our product uses Java. Tools here are context, not candidate requirements."
            if number == 18
            else "This fictional posting is authored for a public engineering demo."
        )
        text = "\n".join([heading, context, *[a[0] for a in annotations]])
        (root / "sample_jobs" / f"{job_id}.txt").write_text(text)
        requirements, labels = [], []
        for quote, kind, skills, category, operator, production, years in annotations:
            start = text.index(quote)
            requirement = {
                "raw_text": quote,
                "normalized_skill_or_requirement": " OR ".join(skills)
                if operator == "ANY"
                else " AND ".join(skills),
                "skills": skills,
                "operator": operator,
                "requirement_type": kind,
                "category": category,
                "evidence": {"start": start, "end": start + len(quote), "quote": quote},
                "explicit_production_required": production,
                "years_required": years,
                "confidence": 1.0,
                "notes": "Synthetic fixture confidence; not model calibrated.",
            }
            requirements.append(requirement)
            canonical = [aliases.get(s.casefold(), s) for s in skills]
            labels.append(
                {
                    **requirement,
                    "skills": canonical,
                    "normalized_skill_or_requirement": (
                        " OR " if operator == "ANY" else " AND "
                    ).join(canonical),
                }
            )
        filters = {
            "geography": "Georgia" if number == 10 else "Berlin" if number == 11 else None,
            "work_mode": "remote" if number == 10 else "onsite" if number == 11 else None,
        }
        responses[hashlib.sha256(text.encode()).hexdigest()] = {
            "requirements": requirements,
            "responsibilities": [],
            **filters,
        }
        golden.append(
            {
                "job_id": job_id,
                "fixture": f"sample_jobs/{job_id}.txt",
                "extraction": {"requirements": labels, "responsibilities": [], **filters},
            }
        )
        registry.append(
            {
                "job_id": job_id,
                "company": f"Synthetic Company {number:02d}",
                "role": "Backend / AI Engineer",
                "official_url": "",
                "status": "",
                "applied": "",
            }
        )
    write_json(root / "provider_responses.json", responses)
    write_json(root / "golden_dataset.json", golden)
    with (root / "sample_registry.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(registry[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(registry)
    write_json(
        root / "sample_candidate.json",
        {
            "profile_id": "synthetic-candidate",
            "complete": False,
            "evidence": [
                {
                    "skill": "Python",
                    "current_capability": "strong",
                    "production_evidence": "confirmed",
                    "source": "synthetic://portfolio",
                    "quote": "Authored and operated a Python service.",
                },
                {
                    "skill": "Kubernetes",
                    "current_capability": "strong",
                    "production_evidence": "limited",
                    "source": "synthetic://lab",
                    "quote": "Operated a local Kubernetes lab; no production deployment claimed.",
                },
                {
                    "skill": "AWS",
                    "current_capability": "basic",
                    "production_evidence": "confirmed",
                    "source": "synthetic://history",
                    "quote": "Historical AWS operations; current capability needs refreshing.",
                },
            ],
        },
    )


if __name__ == "__main__":
    main()
