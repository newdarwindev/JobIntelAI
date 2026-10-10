"""Prove API/PostgreSQL/provider sockets and process recovery without model inference."""

import argparse
import subprocess
from pathlib import Path

import httpx

from jobintel.openai_transport import EMULATOR_MODEL
from scripts.responses_environment import compose, emulator_environment, request, write_evidence

CASES = [
    ("refusal", 422, "refusal", False, 1),
    ("invalid_evidence", 422, "invalid_evidence", False, 1),
    ("malformed_json", 502, "malformed_json", False, 2),
    ("invalid_schema", 502, "invalid_schema", False, 2),
    ("malformed_http", 502, "malformed_json", False, 2),
    ("truncated", 502, "truncated_json", False, 2),
    ("rate_limit", 502, "rate_limit", True, 1),
    ("quota", 502, "quota", False, 1),
    ("server_error", 502, "provider_failure", True, 1),
    ("delay", 504, "timeout", True, 1),
    ("connection_close", 502, "provider_failure", True, 1),
]


def call(base, path, payload=None, *, status=200):
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.request("GET" if payload is None else "POST", base + path, json=payload)
    assert response.status_code == status, (path, response.status_code, status)
    return response.json()


def verify_success(base, evidence):
    health = call(base, "/health")
    assert health["provider"] == "openai" and health["execution_mode"] == "emulator"
    assert not health["live_llm"] and health["provider_ready"]
    source = Path("data/sample_jobs/SYN-01.txt").read_text()
    call(
        base,
        "/jobs/import",
        {"jobs": [{"job_id": "contract", "company": "Authored contract", "role": "Engineer"}]},
    )
    call(base, "/jobs/contract/snapshots", {"text": source}, status=201)
    saved = call(base, "/jobs/contract/extract", {})
    extraction = call(base, "/jobs/contract")["extraction"]
    for row in extraction["requirements"]:
        quote = row["evidence"]
        assert source[quote["start"] : quote["end"]] == quote["quote"]
    provenance = extraction["provenance"]
    assert provenance["execution_mode"] == "emulator" and provenance["model"] == EMULATOR_MODEL
    assert (
        provenance["usage"]
        is provenance["llm_elapsed_seconds"]
        is provenance["estimated_cost"]
        is None
    )
    evidence["cases"].append(
        {
            "case": "persisted_success",
            "status": "passed",
            "source_sha256": provenance["source_sha256"],
        }
    )
    return saved["run_id"]


def verify_failures(base, emulator, saved, evidence):
    for scenario, status, code, retryable, count in CASES:
        request(emulator["base"], "/control", {"scenario": scenario})
        result = call(base, "/jobs/contract/extract", {}, status=status)
        assert result["detail"] == {
            "code": code,
            "retryable": retryable,
            "message": f"extraction provider: {code}",
        }
        assert call(base, "/jobs/contract")["extraction"]["run_id"] == saved
        diagnostics = emulator["diagnostics"]()
        assert diagnostics["request_count"] == count
        assert all(
            all(
                r[k]
                for k in (
                    "auth_valid",
                    "model_valid",
                    "schema_valid",
                    "parameters_valid",
                    "input_valid",
                )
            )
            for r in diagnostics["requests"]
        )
        evidence["cases"].append(
            {
                "case": scenario,
                "status": "passed",
                "http_status": status,
                "error_code": code,
                "retryable": retryable,
                "diagnostics": diagnostics,
            }
        )


def verify_recovery(base, emulator, saved, options, evidence):
    compose(emulator["project"], "stop", "responses-emulator", **options)
    assert call(base, "/health", status=503)["provider_ready"] is False
    result = call(base, "/jobs/contract/extract", {}, status=502)
    assert result["detail"]["code"] == "provider_failure"
    assert call(base, "/jobs/contract")["extraction"]["run_id"] == saved
    compose(emulator["project"], "start", "responses-emulator", **options)
    compose(
        emulator["project"], "up", "-d", "--no-build", "--wait", "responses-emulator", **options
    )
    request(emulator["base"], "/control", {"scenario": "success"})
    assert call(base, "/health")["provider_ready"]
    assert call(base, "/jobs/contract/extract", {})["run_id"] != saved
    compose(emulator["project"], "restart", "responses-emulator", **options)
    compose(
        emulator["project"], "up", "-d", "--no-build", "--wait", "responses-emulator", **options
    )
    assert call(base, "/health")["provider_ready"]
    history = call(base, "/jobs/contract/history")
    assert sum(len(s["runs"]) for s in history["snapshots"]) == 2
    evidence["cases"].append(
        {"case": "stop_start_restart_recovery", "status": "passed", "preserved_runs": 2}
    )


def verify_report(base, evidence):
    report = call(base, "/evaluate", {})
    assert report["status"] == "completed" and report["dataset_size"] == 20
    assert "not model quality" in report["mode"]
    result = report["results"][0]
    assert result["identity"]["execution_mode"] == "emulator" and result["succeeded"] == 20
    assert result["tokens"] is result["estimated_cost"] is result["llm_elapsed_seconds"] is None
    evidence["cases"].append(
        {"case": "evaluation_identity", "status": "passed", "authored_cases": 20}
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-bundle")
    parser.add_argument("--port", type=int, default=18083)
    args = parser.parse_args()
    evidence = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "mode": "emulator",
        "inference": False,
        "configuration": "openai_normalized_v1",
        "model": EMULATOR_MODEL,
        "cases": [],
        "status": "failed",
    }
    options = {"ca_bundle": args.ca_bundle, "api_port": args.port}
    try:
        with emulator_environment(api=True, **options) as emulator:
            base = f"http://127.0.0.1:{args.port}"
            saved = verify_success(base, evidence)
            verify_failures(base, emulator, saved, evidence)
            verify_recovery(base, emulator, saved, options, evidence)
            verify_report(base, evidence)
            evidence.update(status="passed", passed=len(evidence["cases"]), failed=0, skipped=0)
    finally:
        write_evidence("work/responses-service.json", evidence)
    print(
        f"Responses service: {evidence['passed']} passed, 0 failed, 0 skipped; authored contract only."
    )


if __name__ == "__main__":
    main()
