"""Explicit frozen-corpus experiment commands; no database writes or paid CI calls."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from jobintel.config import fixture_root, openai_key
from jobintel.experiment_corpus import (
    freeze_bundled,
    load_corpus,
    parse_corpus,
    read_json,
    verify_public,
    write_json,
)
from jobintel.experiment_reviewed import freeze_reviewed, public_reference
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


def run(args, corpus, spec, transport=None):
    plan(corpus, spec, "live" if args.provider == "openai" else "fake")
    if corpus.public:
        verify_public(corpus, public_reference(corpus, fixture_root()))
    elif not args.output.resolve().is_relative_to(Path("local_data").resolve()):
        raise ValueError("private corpus output must stay under ignored local_data/")
    provider = selected_experiment_provider(args.provider, transport)
    args.output.mkdir(parents=True, exist_ok=False)
    report_path = args.output / "report.json"
    report = run_experiment(
        provider,
        corpus,
        spec,
        checkpoint=lambda current: save_checkpoint(report_path, current),
    )
    save_checkpoint(report_path, report)
    write_json(args.output / "scores.json", rescore(report))
    from jobintel.experiment_publication import comparison

    (args.output / "comparison.md").write_text(comparison(report), encoding="utf-8")
    print(f"{report['mode']} experiment report: {report_path}")
    return 1 if any(r["summary"]["failed"] for r in report["results"]) else 0


def selected_experiment_provider(name, transport):
    if name == "fake":
        return FakeExperimentProvider(fixture_root())
    from jobintel.experiment_provider import OpenAIExperimentProvider
    from jobintel.openai_transport import HttpOpenAITransport

    if transport is None:
        try:
            key = openai_key()
        except ValueError:
            raise ProviderUnavailable(
                "OpenAI credentials are missing or invalid; configure only OPENAI_API_KEY "
                "or OPENAI_API_KEY_FILE securely."
            ) from None
        transport = HttpOpenAITransport(key)
    return OpenAIExperimentProvider(transport)


def publish(args):
    report = read_json(args.report)
    corpus = load_corpus_from_report(report)
    verify_public(corpus, public_reference(corpus, fixture_root()))
    if report["mode"] == "live":
        from jobintel.experiment_publication import publish_live

        return publish_live(args, report, corpus)
    if report["mode"] != "fake":
        raise ValueError("live publication requires a separate reviewer/privacy audit (#9)")
    spec = ExperimentSpec.model_validate(report["spec"])
    if spec != default_spec(corpus):
        raise ValueError(
            "public fake publication requires the default credential-free configuration"
        )
    validate_public_records(report, corpus, spec)
    scores = rescore(report)
    provenance = public_provenance(report["provenance"])
    created_at = datetime.fromisoformat(report["created_at"]).isoformat()
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

    public = {
        "format_version": report.get("format_version", 1),
        "mode": "fake",
        "quality_claim": "fake provider plumbing only",
        "created_at": created_at,
        "provenance": provenance,
        "corpus": corpus.model_dump(mode="json"),
        "corpus_sha256": scores["corpus_sha256"],
        "schema_sha256": report["schema_sha256"],
        "spec": spec.model_dump(mode="json"),
        "spec_sha256": scores["spec_sha256"],
        "reservation": plan(corpus, spec, "fake"),
        "results": results,
        "complete": True,
    }
    write_json(args.output / "report.json", public)
    write_json(args.output / "scores.json", scores)
    from jobintel.experiment_publication import comparison

    (args.output / "comparison.md").write_text(comparison(public), encoding="utf-8")
    print(f"Authored fake report published to {args.output}; no live quality claim.")
    return 0


def validate_public_records(report, corpus, spec):
    provider = FakeExperimentProvider(fixture_root())
    for result in report["results"]:
        for case, record in zip(corpus.cases, result["records"], strict=True):
            validate_fake_metadata(record)
            validate_fake_prediction(provider, case, record, result["config"], spec, corpus)


def validate_fake_metadata(record):
    if any(
        record.get(key) is not None
        for key in ["usage", "request_id", "model", "provenance", "output_text"]
    ):
        raise ValueError("public fake output contains unexpected provider metadata")


def validate_fake_prediction(provider, case, record, configuration, spec, corpus):
    try:
        predicted = provider.predict(case.text, configuration, spec).extraction
    except ProviderUnavailable:
        if (
            record["status"] != "failed"
            or record["error_code"] != "provider_unavailable"
            or record["raw_prediction"] is not None
            or record["prediction"] is not None
        ):
            raise ValueError(
                "public fixture failure differs from the known unavailable input"
            ) from None
        return
    if record["raw_prediction"] != predicted.model_dump(mode="json"):
        raise ValueError("public prediction differs from the authored fake provider")
    if configuration["normalize"]:
        predicted = normalize(predicted, corpus.taxonomy)
    if record["prediction"] != predicted.model_dump(mode="json"):
        raise ValueError("public scored prediction differs from the authored fake result")


def default_spec(corpus):
    return ExperimentSpec(max_calls=len(corpus.cases) * 3)


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
    return parse_corpus(report["corpus"])


def main(arguments, *, transport=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "plan", "run", "rescore", "audit", "publish"])
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--provider", choices=["fake", "openai"], default="fake")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--readme", type=Path)
    parser.add_argument("--dataset", choices=["fixture", "reviewed"], default="fixture")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        return execute(args, transport)
    except (ValueError, OSError, KeyError, TypeError, ProviderUnavailable) as error:
        # ValidationError details can echo private input; print only a safe class code.
        if isinstance(error, ProviderUnavailable):
            parser.exit(2, f"{error}\n")
        parser.exit(2, f"Experiment rejected ({type(error).__name__}); see docs/experiments.md.\n")
    except KeyboardInterrupt:
        parser.exit(1, "Experiment interrupted; the last atomic checkpoint remains incomplete.\n")


def execute(args, transport=None):
    if args.action == "freeze":
        corpus = (
            freeze_reviewed(fixture_root())
            if args.dataset == "reviewed"
            else freeze_bundled(fixture_root())
        )
        write_json(args.output, corpus.model_dump(mode="json"))
        return 0
    if args.action in {"rescore", "audit", "publish"}:
        if not args.report:
            raise ValueError("--report is required")
        if args.action == "publish":
            return publish(args)
        if args.action == "audit":
            from jobintel.experiment_publication import audit_draft

            write_json(args.output, audit_draft(read_json(args.report), fixture_root()))
            return 0
        write_json(args.output, rescore(read_json(args.report)))
        return 0
    if not args.corpus:
        raise ValueError("--corpus is required")
    corpus = load_corpus(args.corpus)
    spec = (
        ExperimentSpec.model_validate(read_json(args.config))
        if args.config
        else default_spec(corpus)
    )
    if args.action == "run":
        return run(args, corpus, spec, transport)
    reservation = plan(corpus, spec, "live" if args.provider == "openai" else "fake")
    write_json(args.output, {"reservation": reservation, "spec": spec.model_dump(mode="json")})
    return 0
