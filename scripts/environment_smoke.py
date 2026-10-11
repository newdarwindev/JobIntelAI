"""Complete real-wire/API/CLI pipeline and simultaneous lease isolation; zero paid calls."""

import argparse
import json
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from jobintel.experiments import code_provenance
from scripts.environment import Environment, stop_session
from scripts.environment_lifecycle import interruption_guard, read_record, resources
from scripts.responses_environment import write_evidence
from scripts.responses_smoke import call


def passed(evidence, case, **details):
    evidence["cases"].append({"case": case, "status": "passed", **details})


def pipeline(session, evidence):
    base = session.info["base"]
    health = call(base, "/health")
    assert health["execution_mode"] == "emulator" and not health["live_llm"]
    call(
        base,
        "/jobs/import",
        {
            "jobs": [
                {
                    "job_id": "lease-job",
                    "company": "Authored lease",
                    "role": "Engineer",
                    "official_url": "https://example.com/unseen",
                }
            ]
        },
    )
    fetched = call(base, "/jobs/lease-job/fetch", {}, status=201)
    assert fetched["attempts"][-1]["status"] == "success"
    saved = call(base, "/jobs/lease-job/extract", {})
    job = call(base, "/jobs/lease-job")
    assert job["snapshot"]["clean_text"] == "Python is required."
    for row in saved["requirements"]:
        quote = row["evidence"]
        assert job["snapshot"]["clean_text"][quote["start"] : quote["end"]] == quote["quote"]
    assert saved["provenance"]["execution_mode"] == "emulator"
    assert saved["provenance"]["usage"] is saved["provenance"]["estimated_cost"] is None
    passed(
        evidence,
        "import_verified_https_schema_grounding_persistence",
        run_id=saved["run_id"],
        source_sha256=saved["provenance"]["source_sha256"],
    )
    profile = json.loads(Path("data/sample_candidate.json").read_text())
    revision = call(base, "/candidates/import", profile, status=201)
    match = call(
        base,
        "/jobs/lease-job/match",
        {
            "profile_id": revision["profile_id"],
            "profile_revision_id": revision["profile_revision_id"],
            "expected_run_id": saved["run_id"],
        },
    )
    assert match["matches"]
    assert call(base, "/analytics/skills")["N"] == 1
    exported = call(base, "/exports", {"kind": "evidence", "job_ids": ["lease-job"]})
    assert exported["extraction"]["run_id"] == saved["run_id"]
    passed(
        evidence,
        "saved_revision_match_analytics_and_api_export",
        match_run_id=match["match_run_id"],
    )
    session.command(
        "exec", "-T", "api", "jobintel", "export", "--output", "/app/results/generated/lease-check"
    )
    checked = session.command(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "import json; from pathlib import Path; x=json.loads(Path('/app/results/generated/lease-check/skill_counts.json').read_text()); assert x['N']==1; print(x['N'])",
        capture=True,
    )
    assert checked.stdout.strip() == "1"
    passed(evidence, "cli_export_reads_the_same_postgresql_state")
    report = call(base, "/evaluate", {})
    assert report["dataset_size"] == 20 and report["results"][0]["succeeded"] == 20
    assert "not model quality" in report["mode"]
    reloaded = call(base, "/evaluation-runs/" + report["evaluation_run_id"])
    assert reloaded["results"] == report["results"]
    cli = session.command(
        "exec",
        "-T",
        "api",
        "jobintel",
        "evaluate",
        "--run-id",
        report["evaluation_run_id"],
        "--output",
        "/app/results/generated/lease-evaluation",
        capture=True,
    )
    assert "20 cases" in cli.stdout
    stored = session.command(
        "exec",
        "-T",
        "api",
        "cat",
        "/app/results/generated/lease-evaluation/evaluation.json",
        capture=True,
    )
    assert json.loads(stored.stdout) == report
    observed = session.fixtures["diagnostics"]()
    assert observed["origin"]["counts"].get("tls", 0) > 0
    passed(
        evidence,
        "authored_twenty_case_evaluation_api_cli_reload",
        evaluation_run_id=report["evaluation_run_id"],
        authored_cases=20,
    )
    return saved["run_id"]


def concurrent_runs(first, evidence, options):
    first_resources = resources(first.project, first.lease.record["owner"])
    with Environment("emulator", acquisition=True, **options) as second:
        assert second.info["base"] != first.info["base"]
        assert second.info["control_base"] != first.info["control_base"]
        assert second.fixtures["proxy"] != first.fixtures["proxy"]
        assert call(second.info["base"], "/jobs")["jobs"] == []
        assert call(second.info["base"], "/analytics/skills")["N"] == 0
        second_resources = resources(second.project, second.lease.record["owner"])
        assert not set(first_resources["volumes"]) & set(second_resources["volumes"])
        call(
            second.info["base"],
            "/jobs/import",
            {"jobs": [{"job_id": "second-only", "company": "Lease isolation", "role": "Engineer"}]},
        )
        assert [j["job_id"] for j in call(first.info["base"], "/jobs")["jobs"]] == ["lease-job"]
        evidence["runs"].append(second.info)
    assert not any(resources(second.project).values())
    assert resources(first.project, first.lease.record["owner"]) == first_resources
    assert call(first.info["base"], "/health")["provider_ready"]
    passed(evidence, "simultaneous_unique_ports_volumes_and_state_scoped_success_cleanup")


def failure_cleanup(first, evidence, options):
    failed = Environment("fixture", **options)
    try:
        with failed:
            raise RuntimeError("authored lifecycle failure")
    except RuntimeError:
        pass
    assert not any(resources(failed.project).values())
    record = read_record(failed.project)
    assert record["outcome"] == "RuntimeError" and record["diagnostics"]["compose"]["containers"]
    assert call(first.info["base"], "/health")["provider_ready"]
    passed(evidence, "failure_cleanup_diagnostics_and_neighbor_preservation")


def persistent_session(first, evidence, options):
    project = "jobintel-session-" + uuid4().hex[:12]
    try:
        with Environment("fixture", project=project, persistent=True, **options) as session:
            call(
                session.info["base"],
                "/jobs/import",
                {
                    "jobs": [
                        {
                            "job_id": "persistent-only",
                            "company": "Developer session",
                            "role": "Engineer",
                        }
                    ]
                },
            )
        record = read_record(project)
        assert record["cleanup"]["volumes"] and not record["cleanup"]["containers"]
        volumes = resources(project)["volumes"]
        concurrent_runs(first, evidence, options)
        failure_cleanup(first, evidence, options)
        assert resources(project)["volumes"] == volumes
        with Environment(
            "fixture", project=project, persistent=True, resume=True, **options
        ) as resumed:
            assert [j["job_id"] for j in call(resumed.info["base"], "/jobs")["jobs"]] == [
                "persistent-only"
            ]
        stop_session(project)
        assert resources(project)["volumes"]
        passed(evidence, "explicit_persistent_stop_resume_and_idempotence")
    finally:
        stop_session(project, reset=True)
        stop_session(project, reset=True)
    assert not any(resources(project).values())
    passed(evidence, "explicit_persistent_reset_is_scoped")


def interrupted_runs(evidence):
    for interrupt in (signal.SIGTERM, signal.SIGINT):
        project = "jobintel-interrupt-" + uuid4().hex[:12]
        with tempfile.TemporaryFile(mode="w+") as log:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "scripts.environment",
                    "run",
                    "--mode",
                    "fixture",
                    "--project",
                    project,
                    "--",
                    sys.executable,
                    "-c",
                    "import time; time.sleep(600)",
                ],
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    lease = read_record(project)
                    if lease and lease["status"] == "ready":
                        break
                    assert child.poll() is None, "interruption fixture failed to start"
                    time.sleep(0.5)
                else:
                    raise TimeoutError("interruption fixture did not become ready")
                child.send_signal(interrupt)
                assert child.wait(timeout=30) != 0
                assert not any(resources(project).values())
                assert read_record(project)["outcome"] == "KeyboardInterrupt"
                passed(evidence, interrupt.name.lower() + "_cleans_owned_services_and_command")
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                stop_session(project)
    project = "jobintel-expiry-" + uuid4().hex[:12]
    code = (
        "import os,signal; from scripts.environment_lifecycle import Lease,docker,LABEL,PROJECT; "
        f"s=Lease({project!r},lifetime=30); "
        "docker('volume','create','--label',PROJECT+'='+s.record['project'],"
        "'--label',LABEL+'='+s.record['owner'],s.record['project']+'-owned'); "
        "os.kill(os.getpid(),signal.SIGKILL)"
    )
    child = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True)
    assert child.returncode == -signal.SIGKILL
    deadline = time.monotonic() + 40
    try:
        while time.monotonic() < deadline:
            if read_record(project)["status"] == "stopped":
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("orphan watchdog did not clean the expired lease")
        assert not any(resources(project).values())
        assert read_record(project)["outcome"] == "expired"
        passed(evidence, "sigkill_orphan_watchdog_enforces_bounded_lifetime")
    finally:
        stop_session(project)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-bundle")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("work/environment-service.json"))
    args = parser.parse_args()
    options = {"ca_bundle": args.ca_bundle, "offline": args.offline}
    evidence = {
        "code_provenance": code_provenance(),
        "mode": "emulator",
        "inference": False,
        "paid_calls": 0,
        "cases": [],
        "runs": [],
        "status": "failed",
    }
    failure = None
    try:
        with interruption_guard(), Environment("emulator", acquisition=True, **options) as first:
            evidence["runs"].append(first.info)
            saved = pipeline(first, evidence)
            persistent_session(first, evidence, options)
            interrupted_runs(evidence)
            assert call(first.info["base"], "/jobs/lease-job")["extraction"]["run_id"] == saved
        assert not any(resources(first.project).values())
        stop_session(first.project)
        stop_session(first.project)
        passed(evidence, "final_disposable_cleanup_and_idempotent_stop")
        evidence["status"] = "passed"
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
        write_evidence(args.output, evidence)
    print(
        f"Environment service: {evidence['passed']} passed; 0 failed/errors/skipped; zero paid calls."
    )


if __name__ == "__main__":
    main()
