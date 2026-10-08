"""Explicit frozen-corpus experiment commands; no database writes or paid CI calls."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from jobintel.config import fixture_root
from jobintel.experiment_corpus import (
    freeze_bundled,
    load_corpus,
    read_json,
    verify_public,
    write_json,
)
from jobintel.experiments import (
    ExperimentSpec,
    FakeExperimentProvider,
    normalize,
    plan,
    rescore,
    run_experiment,
)
from jobintel.providers import ProviderUnavailable


def save_checkpoint(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".partial")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(args, corpus, spec):
    plan(corpus, spec, "live" if args.provider == "openai" else "fake")
    if args.provider == "openai":
        raise ProviderUnavailable(
            "Live execution requires the structured adapter (#4) and independent evaluator (#8); "
            "this command never substitutes fixture predictions for a live configuration."
        )
    if corpus.public:
        verify_public(corpus, freeze_bundled(fixture_root()))
    elif not args.output.resolve().is_relative_to(Path("local_data").resolve()):
        raise ValueError("private corpus output must stay under ignored local_data/")
    args.output.mkdir(parents=True, exist_ok=False)
    report_path = args.output / "report.json"
    report = run_experiment(
        FakeExperimentProvider(fixture_root()),
        corpus,
        spec,
        checkpoint=lambda current: save_checkpoint(report_path, current),
    )
    save_checkpoint(report_path, report)
    write_json(args.output / "scores.json", rescore(report))
    print(f"{report['mode']} experiment report: {report_path}")
    return 1 if any(r["summary"]["failed"] for r in report["results"]) else 0


def publish(args):
    report = read_json(args.report)
    corpus = load_corpus_from_report(report)
    verify_public(corpus, freeze_bundled(fixture_root()))
    # Automatic publication currently admits only reproducible authored fake outputs.
    # Live reports require the separate reviewer/privacy audit in issue #9.
    if report["mode"] != "fake":
        raise ValueError("live publication requires a separate reviewer/privacy audit (#9)")
    spec = ExperimentSpec.model_validate(report["spec"])
    if spec != ExperimentSpec():
        raise ValueError(
            "public fake publication requires the default credential-free configuration"
        )
    validate_public_records(report, corpus, spec)
    scores = rescore(report)
    provenance = public_provenance(report["provenance"])
    created_at = datetime.fromisoformat(report["created_at"]).isoformat()
    if any(r["summary"]["failed"] for r in scores["results"]):
        raise ValueError("failed experiments remain diagnostics, not public success reports")
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for result, scored in zip(report["results"], scores["results"], strict=True):
        results.append(
            {
                key: result[key]
                for key in ["configuration", "config", "config_sha256", "records", "records_sha256"]
            }
            | {"summary": scored["summary"]}
        )
    from jobintel.experiment_corpus import digest
    from jobintel.schemas import Extraction

    public = {
        "format_version": 1,
        "mode": "fake",
        "quality_claim": "fake provider plumbing only",
        "created_at": created_at,
        "provenance": provenance,
        "corpus": corpus.model_dump(mode="json"),
        "corpus_sha256": scores["corpus_sha256"],
        "schema_sha256": digest(Extraction.model_json_schema()),
        "spec": spec.model_dump(mode="json"),
        "spec_sha256": scores["spec_sha256"],
        "reservation": plan(corpus, spec, "fake"),
        "results": results,
        "complete": True,
    }
    write_json(args.output / "report.json", public)
    write_json(args.output / "scores.json", scores)
    print(f"Authored fake report published to {args.output}; no live quality claim.")
    return 0


def validate_public_records(report, corpus, spec):
    provider = FakeExperimentProvider(fixture_root())
    for result in report["results"]:
        for case, record in zip(corpus.cases, result["records"], strict=True):
            predicted = provider.predict(case.text, result["config"], spec).extraction
            if (
                record["raw_prediction"] != predicted.model_dump(mode="json")
                or record["usage"] is not None
            ):
                raise ValueError("public prediction differs from the authored fake provider")
            if record["request_id"] is not None or record["model"] is not None:
                raise ValueError("public fake output contains unexpected provider metadata")
            if result["config"]["normalize"]:
                predicted = normalize(predicted, corpus.taxonomy)
            if record["prediction"] != predicted.model_dump(mode="json"):
                raise ValueError("public scored prediction differs from the authored fake result")


def public_provenance(provenance):
    if not re.fullmatch(r"[a-f0-9]{64}", provenance["source_sha256"]):
        raise ValueError("invalid public source hash")
    commit = provenance["git_commit"]
    if commit is not None and not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("invalid public commit hash")
    if provenance["git_dirty"] not in {True, False, None}:
        raise ValueError("invalid public dirty flag")
    return {
        "source_sha256": provenance["source_sha256"],
        "git_commit": commit,
        "git_dirty": provenance["git_dirty"],
    }


def load_corpus_from_report(report):
    from jobintel.experiment_corpus import FrozenCorpus

    return FrozenCorpus.model_validate(report["corpus"])


def main(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "plan", "run", "rescore", "publish"])
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--provider", choices=["fake", "openai"], default="fake")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        return execute(args)
    except (ValueError, OSError, KeyError, TypeError, ProviderUnavailable) as error:
        # ValidationError details can echo private input; print only a safe class code.
        if isinstance(error, ProviderUnavailable):
            parser.exit(2, f"{error}\n")
        parser.exit(2, f"Experiment rejected ({type(error).__name__}); see docs/experiments.md.\n")


def execute(args):
    if args.action == "freeze":
        write_json(args.output, freeze_bundled(fixture_root()).model_dump(mode="json"))
        return 0
    if args.action in {"rescore", "publish"}:
        if not args.report:
            raise ValueError("--report is required")
        if args.action == "publish":
            return publish(args)
        write_json(args.output, rescore(read_json(args.report)))
        return 0
    if not args.corpus:
        raise ValueError("--corpus is required")
    corpus = load_corpus(args.corpus)
    spec = (
        ExperimentSpec.model_validate(read_json(args.config)) if args.config else ExperimentSpec()
    )
    if args.action == "run":
        return run(args, corpus, spec)
    reservation = plan(corpus, spec, "live" if args.provider == "openai" else "fake")
    write_json(args.output, {"reservation": reservation, "spec": spec.model_dump(mode="json")})
    return 0
