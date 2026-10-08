"""Export saved data without invoking a provider or writing private files into Git."""

import argparse
import json
import subprocess
from pathlib import Path

from jobintel.config import database_url
from jobintel.db import session_factory
from jobintel.export_selection import ExportInput
from jobintel.exports import ExportService, render_csv


def private_output(path):
    path = path.resolve()
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if result.returncode != 0 or not path.is_relative_to(Path(result.stdout.strip())):
        return
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", str(path / "export.json")], capture_output=True
    )
    if ignored.returncode != 0:
        raise ValueError(
            "exports inside a checkout must use an ignored path such as results/generated/ or local_data/"
        )


def write_exports(session, request, output, stem):
    private_output(output)
    output.mkdir(parents=True, exist_ok=True)
    exporter = ExportService(session)
    report = exporter.export(request.model_copy(update={"format": "json"}))
    (output / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / f"{stem}.csv").write_text(render_csv(report, request), encoding="utf-8", newline="")
    return report


def execute(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export"])
    parser.add_argument("--kind", choices=["skills", "requirements", "matches", "evidence"])
    parser.add_argument("--output", type=Path, default=Path("results/generated"))
    parser.add_argument("--applied", choices=["true", "false"])
    parser.add_argument("--job-id", action="append", default=[])
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--match-run-id", action="append", default=[])
    parser.add_argument("--historical", action="store_true")
    parser.add_argument("--profile-id")
    parser.add_argument("--revision-id")
    args = parser.parse_args(argv)
    request = ExportInput(
        kind=args.kind or "skills",
        job_ids=args.job_id,
        run_ids=args.run_id,
        match_run_ids=args.match_run_id,
        historical=args.historical,
        profile_id=args.profile_id,
        profile_revision_id=args.revision_id,
        applied=None if args.applied is None else args.applied == "true",
        legacy_skills_csv=args.kind is None,
    )
    stem = args.kind or "skill_counts"
    factory = session_factory(database_url())
    try:
        with factory() as session:
            report = write_exports(session, request, args.output, stem)
        print(f"N={report['N']}; exports written to {args.output}")
    finally:
        factory.kw["bind"].dispose()
