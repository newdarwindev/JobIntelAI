import argparse
import csv
import json
import sys
from pathlib import Path

from jobintel.config import database_url, fixture_root
from jobintel.db import session_factory
from jobintel.evaluation import run_evaluation
from jobintel.normalization import Taxonomy
from jobintel.openai_transport import ProviderError
from jobintel.providers import selected_configuration, selected_provider
from jobintel.registry import parse_csv
from jobintel.schemas import CandidateProfile, SnapshotInput
from jobintel.service import Service


def main(argv=None, *, transport=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        execute(argv, transport)
    except ProviderError as error:
        print(json.dumps(error.detail()), file=sys.stderr)
        raise SystemExit(1) from None
    except KeyError:
        print("job, candidate revision or match run not found", file=sys.stderr)
        raise SystemExit(2) from None
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None


def execute(argv, transport):
    if argv and argv[0] == "experiment":
        from jobintel.experiment_cli import main as experiment_main

        raise SystemExit(experiment_main(argv[1:]))
    if argv and argv[0] in {"candidate-import", "candidate-revisions", "match", "match-run"}:
        from jobintel.candidate_cli import execute as candidate_execute

        candidate_execute(argv)
        return
    parser = argparse.ArgumentParser(
        description="JobIntel extraction and offline demo; run migrations first"
    )
    parser.add_argument("command", choices=["demo", "evaluate", "export", "extract"])
    parser.add_argument("--output", type=Path, default=Path("results/generated"))
    parser.add_argument("--provider", choices=["fixture", "openai"])
    parser.add_argument("--configuration")
    parser.add_argument("--configurations", nargs="+")
    parser.add_argument("--job-id")
    args = parser.parse_args(argv)
    root = fixture_root()
    provider = selected_provider(root, args.provider, transport=transport)
    configuration = selected_configuration(provider, args.configuration)
    if args.command == "demo" and provider.name != "fixture":
        raise ValueError(
            "demo requires fixture replay; use extract for an explicitly selected live provider"
        )
    factory = session_factory(database_url())
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command == "evaluate":
        configurations = args.configurations or (
            ["fixture_raw", "fixture_normalized"] if provider.name == "fixture" else [configuration]
        )
        report = run_evaluation(provider, root, configurations)
        (args.output / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return
    with factory.begin() as session:
        service = Service(session, provider, Taxonomy(root / "taxonomy.json"))
        if args.command == "extract":
            if not args.job_id:
                raise ValueError("extract requires --job-id")
            print(json.dumps(service.extract(args.job_id, configuration), indent=2))
            return
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
                service.extract(job.job_id, configuration)
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
