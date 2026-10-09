import argparse
import json
import sys
from pathlib import Path

from jobintel.config import database_url, fixture_root
from jobintel.db import session_factory
from jobintel.normalization import Taxonomy
from jobintel.openai_transport import ProviderError
from jobintel.providers import ProviderUnavailable, selected_configuration, selected_provider
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
    except ProviderUnavailable as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except KeyError:
        print("job, candidate revision or match run not found", file=sys.stderr)
        raise SystemExit(2) from None
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None


def specialized_command(argv):
    if argv and argv[0] == "analytics":
        from jobintel.analytics_cli import execute as analytics_execute

        analytics_execute(argv)
        return True
    if argv and argv[0] == "export":
        from jobintel.export_cli import execute as export_execute

        export_execute(argv)
        return True
    if argv and argv[0] == "experiment":
        from jobintel.experiment_cli import main as experiment_main

        raise SystemExit(experiment_main(argv[1:]))
    if argv and argv[0] in {"candidate-import", "candidate-revisions", "match", "match-run"}:
        from jobintel.candidate_cli import execute as candidate_execute

        candidate_execute(argv)
        return True
    return False


def execute(argv, transport):
    if specialized_command(argv):
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
    parser.add_argument("--dataset", choices=["fixture", "reviewed"], default="fixture")
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    if args.run_id:
        load_evaluation_command(args)
        return
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
        evaluate_command(factory, provider, root, args, configuration)
        return
    if args.command == "extract":
        print(
            json.dumps(
                extract_command(factory, provider, root, args.job_id, configuration), indent=2
            )
        )
        return
    with factory.begin() as session:
        service = Service(session, provider, Taxonomy(root / "taxonomy.json"))
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
        from jobintel.export_cli import write_exports
        from jobintel.export_selection import ExportInput

        report = write_exports(
            service.session, ExportInput(legacy_skills_csv=True), args.output, "skill_counts"
        )
        print(f"N={report['N']}; exports written to {args.output}")


def extract_command(factory, provider, root, job_id, configuration):
    from jobintel.extraction_attempts import attempt_extract

    if not job_id:
        raise ValueError("extract requires --job-id")
    try:
        with factory.begin() as session:
            result, error = attempt_extract(
                Service(session, provider, Taxonomy(root / "taxonomy.json")), job_id, configuration
            )
        if error:
            raise error
        return result
    finally:
        factory.kw["bind"].dispose()


def evaluate_command(factory, provider, root, args, configuration):
    from jobintel.evaluation_runs import human_summary, run_report
    from jobintel.evaluation_store import get_report, save_report
    from jobintel.schemas import EvaluationPricing

    try:
        with factory.begin() as session:
            if args.run_id:
                report = get_report(session, args.run_id)
            else:
                from sqlalchemy import select

                from jobintel import db

                session.execute(select(db.EvaluationRun.id).limit(1))
                configurations = args.configurations or (
                    ["fixture_raw", "fixture_normalized"]
                    if provider.name == "fixture"
                    else [configuration]
                )
                pricing = (
                    EvaluationPricing.model_validate_json(args.pricing.read_text())
                    if args.pricing
                    else None
                )
                report = save_report(
                    session,
                    run_report(
                        provider, root, configurations, dataset=args.dataset, pricing=pricing
                    ),
                )
        (args.output / "evaluation.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )
        (args.output / "evaluation.txt").write_text(human_summary(report))
        print(human_summary(report), end="")
        if any(r.get("failed", 0) for r in report["results"]):
            raise SystemExit(1)
    finally:
        factory.kw["bind"].dispose()


def load_evaluation_command(args):
    if args.command != "evaluate":
        raise ValueError("--run-id is supported only for evaluate")
    args.output.mkdir(parents=True, exist_ok=True)
    evaluate_command(session_factory(database_url()), None, None, args, None)


if __name__ == "__main__":
    main()
