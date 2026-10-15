"""Реальная закреплённая CPU inference через PostgreSQL API, без платных вызовов/replay."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from jobintel.experiments import code_provenance
from jobintel.local_model import MODEL, MODEL_FILE, model_identity
from jobintel.snapshots import content_hash
from scripts import runtime
from scripts.environment import Environment
from scripts.responses_environment import write_evidence

SOURCE = "Python is required."


def call(args, path, payload=None, *, status=200):
    with httpx.Client(timeout=245, trust_env=False) as client:
        result = client.request(
            "GET" if payload is None else "POST",
            f"http://127.0.0.1:{args.port}" + path,
            json=payload,
        )
    assert result.status_code == status, (path, result.status_code, status)
    return result.json()


def compose(args, *arguments, capture=False, check=True):
    return args.stack.command(*arguments, capture=capture, check=check)


def verify_pipeline(args, evidence):
    health = call(args, "/health")
    assert health["provider"] == "local" and health["execution_mode"] == "local-inference"
    assert health["provider_ready"] and health["live_llm"]
    with httpx.Client(trust_env=False) as client:
        assert client.get(f"http://127.0.0.1:{args.port}/ui/fixtures").status_code == 404
        assert client.post(f"http://127.0.0.1:{args.port}/ui/reset").status_code in {404, 405}
    assert content_hash(SOURCE) not in json.loads(Path("data/provider_responses.json").read_text())
    call(
        args,
        "/jobs/import",
        {"jobs": [{"job_id": "cpu-unseen", "company": "Authored CPU proof", "role": "Engineer"}]},
    )
    call(args, "/jobs/cpu-unseen/snapshots", {"text": SOURCE}, status=201)
    saved = call(args, "/jobs/cpu-unseen/extract", {})
    requirements = saved["requirements"]
    assert requirements and any(r["skills"] == ["Python"] for r in requirements)
    assert any(r["skills"] == ["Python"] and r["requirement_type"] == "MUST" for r in requirements)
    for requirement in requirements:
        quote = requirement["evidence"]
        assert SOURCE[quote["start"] : quote["end"]] == quote["quote"]
    provenance = saved["provenance"]
    assert provenance["model"] == MODEL and provenance["execution_mode"] == "local-inference"
    assert provenance["request_parameters"]["api"] == "chat_completions"
    assert provenance["model_weights_sha256"] == model_identity()["model_weights_sha256"]
    profile = {
        "profile_id": "authored-cpu",
        "evidence": [
            {
                "skill": "Python",
                "current_capability": "strong",
                "production_evidence": "none",
                "source": "synthetic://cpu-profile",
                "quote": "I can independently implement Python programs.",
            }
        ],
    }
    call(args, "/jobs/cpu-unseen/match", profile)
    assert call(args, "/analytics/skills")["N"] == 1
    exported = call(args, "/exports", {"kind": "evidence", "job_ids": ["cpu-unseen"]})
    assert exported["extraction"]["run_id"] == saved["run_id"]
    assert exported["extraction"]["provenance"] == provenance
    evidence["cases"].append(
        {
            "case": "unseen_persist_match_analytics_export",
            "status": "passed",
            "source_sha256": content_hash(SOURCE),
            "provenance": provenance,
            "prediction": requirements,
        }
    )
    return saved


def verify_evaluation(args, evidence):
    result = compose(
        args, "exec", "-T", "api", "python", "-m", "scripts.local_evaluation", capture=True
    )
    report = json.loads(result.stdout)
    report["code_provenance"] = code_provenance()
    assert report["dataset_size"] == 3 and len(report["results"][0]["per_case"]) == 3
    reloaded = call(args, "/evaluation-runs/" + report["evaluation_run_id"])
    assert reloaded["results"] == report["results"]
    evidence["evaluation"] = report
    evidence["cases"].append(
        {
            "case": "reviewed_evaluation_and_reload",
            "status": "passed",
            "model_succeeded": report["results"][0]["succeeded"],
            "model_failed": report["results"][0]["failed"],
        }
    )


def verify_experiments(args, evidence):
    result = compose(
        args,
        "exec",
        "-T",
        "api",
        "python",
        "-m",
        "scripts.network_experiments",
        "--provider",
        "local",
        capture=True,
        check=False,
    )
    evidence["experiments"] = (
        json.loads(result.stdout)
        if result.stdout.strip()
        else {"status": "unavailable", "observed_http_attempts": None}
    )
    evidence["experiments"]["host_code_provenance"] = code_provenance()
    result.check_returncode()
    evidence["cases"].append(
        {
            "case": "frozen_reviewed_B_C_network_experiments_and_saved_rescore",
            "status": "passed",
            "actual_http_attempts": evidence["experiments"]["observed_http_attempts"],
        }
    )


def verify_lifecycle(args, evidence, saved):
    compose(args, "stop", "llama-cpp")
    assert call(args, "/health", status=503)["provider_ready"] is False
    assert (
        call(args, "/jobs/cpu-unseen/extract", {}, status=502)["detail"]["code"]
        == "provider_failure"
    )
    assert call(args, "/jobs/cpu-unseen")["extraction"]["run_id"] == saved["run_id"]
    evidence["cases"].append({"case": "engine_unavailable_preserves_history", "status": "passed"})
    args.stack.suspend()
    started = perf_counter()
    args.stack.start(no_build=True)
    args.port = urlsplit(args.stack.info["base"]).port
    evidence["warm_stack_start_seconds"] = perf_counter() - started
    assert call(args, "/jobs/cpu-unseen")["extraction"]["run_id"] == saved["run_id"]
    assert call(args, "/health")["provider_ready"]
    evidence["cases"].append(
        {"case": "stop_recreation_persistence_and_readiness", "status": "passed"}
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-bundle")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--port", type=int, default=18085)
    parser.add_argument("--project", default="jobintel-local-" + uuid4().hex[:12])
    parser.add_argument("--output", type=Path, default=Path("work/local-inference-service.json"))
    args = parser.parse_args()
    args.mode = "local-inference"
    evidence = {
        "code_provenance": code_provenance(),
        "execution_mode": "local-inference",
        "inference": True,
        **model_identity(),
        "cases": [],
        "status": "failed",
    }
    started = perf_counter()
    failure = None
    try:
        with Environment(
            "local", project=args.project, ca_bundle=args.ca_bundle, offline=args.offline
        ) as session:
            args.stack = session
            args.port = urlsplit(session.info["base"]).port
            evidence["first_stack_start_seconds"] = perf_counter() - started
            saved = verify_pipeline(args, evidence)
            verify_evaluation(args, evidence)
            verify_experiments(args, evidence)
            memory = compose(
                args,
                "exec",
                "-T",
                "llama-cpp",
                "cat",
                "/sys/fs/cgroup/memory.peak",
                capture=True,
                check=False,
            )
            evidence["engine_cgroup_peak_bytes"] = (
                int(memory.stdout)
                if memory.returncode == 0 and memory.stdout.strip().isdigit()
                else None
            )
            verify_lifecycle(args, evidence, saved)
            evidence.update(status="passed", passed=len(evidence["cases"]), failed=0, skipped=0)
    except BaseException as error:
        failure = type(error).__name__
        raise
    finally:
        evidence.update(
            passed=len(evidence["cases"]),
            failed=int(failure == "AssertionError"),
            errors=int(failure is not None and failure != "AssertionError"),
            skipped=0,
            failure_kind=failure,
        )
        try:
            cache = Path(runtime.compose_environment(args)["JOBINTEL_LOCAL_MODEL_CACHE"])
            evidence["cache_preserved"] = (cache / MODEL_FILE).is_file()
            if evidence["status"] == "passed":
                assert evidence["cache_preserved"]
        finally:
            write_evidence(args.output, evidence)
    print(
        f"Local CPU service: {evidence['passed']} checks passed; model evaluation failures retained separately."
    )


if __name__ == "__main__":
    main()
