import argparse
import csv
import json
from pathlib import Path

from jobintel.config import database_url, fixture_root
from jobintel.db import session_factory
from jobintel.evaluation import run_evaluation
from jobintel.providers import FixtureProvider
from jobintel.registry import parse_csv
from jobintel.schemas import CandidateProfile, SnapshotInput
from jobintel.service import Service


def main():
    parser = argparse.ArgumentParser(
        description="Offline synthetic JobIntel demo; run migrations first"
    )
    parser.add_argument("command", choices=["demo", "evaluate", "export"])
    parser.add_argument("--output", type=Path, default=Path("results/generated"))
    args = parser.parse_args()
    root = fixture_root()
    provider = FixtureProvider(root)
    factory = session_factory(database_url())
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command == "evaluate":
        report = run_evaluation(provider, root, ["fixture_raw", "fixture_normalized"])
        (args.output / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return
    with factory.begin() as session:
        service = Service(session, provider)
        if args.command == "demo":
            jobs = parse_csv((root / "sample_registry.csv").read_text())
            service.import_jobs(jobs)
            service.seed_taxonomy()
            profile = CandidateProfile.model_validate_json(
                (root / "sample_candidate.json").read_text()
            )
            for job in jobs:
                service.snapshot(
                    job.job_id,
                    SnapshotInput(text=(root / "sample_jobs" / f"{job.job_id}.txt").read_text()),
                )
                service.extract(job.job_id, "fixture_normalized")
                service.match(job.job_id, profile)
            print(f"Imported and processed {len(jobs)} synthetic postings with fixture replay.")
        report = service.analytics()
        (args.output / "skill_counts.json").write_text(json.dumps(report, indent=2) + "\n")
        with (args.output / "skill_counts.csv").open("w", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=["skill", "N", "n", "must_n", "preferred_n", "experience_n", "other_n"],
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(report["skills"])
        print(f"N={report['N']}; exports written to {args.output}")


if __name__ == "__main__":
    main()
