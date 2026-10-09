"""Exercise named dev/demo/OpenAI configuration and persistence without paid calls."""

import argparse
import http.client
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def require_fresh_projects(project):
    for name in [project, project + "-demo", project + "-openai"]:
        selector = f"label=com.docker.compose.project={name}"
        commands = [
            ["docker", "ps", "--all", "--filter", selector, "--quiet"],
            ["docker", "volume", "ls", "--filter", selector, "--quiet"],
        ]
        for command in commands:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            if result.stdout.strip():
                raise SystemExit("Runtime smoke requires unused projects; choose a fresh --project")


def control(args, action, project, mode="dev", *, no_build=False, environment=None):
    command = [sys.executable, "scripts/runtime.py", action, "--project", project]
    if action == "up":
        command += ["--mode", mode, "--port", str(args.port)]
        if args.offline:
            command += ["--offline"]
        if args.ca_bundle:
            command += ["--ca-bundle", args.ca_bundle]
        if no_build:
            command += ["--no-build"]
    subprocess.run(command, env=environment, check=True)


def request(args, path, payload=None, *, status=200):
    connection = http.client.HTTPConnection("127.0.0.1", args.port, timeout=15)
    body = None if payload is None else json.dumps(payload)
    try:
        connection.request(
            "GET" if payload is None else "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == status, (path, response.status)
        return json.loads(response.read()) if status < 400 else None
    finally:
        connection.close()


def private_routes_absent(args):
    assert request(args, "/ui/config")["demo"] is False
    request(args, "/ui/fixtures", status=404)
    request(args, "/ui/reset", {}, status=405)


def seed(args):
    job_id = "runtime-persistence"
    request(
        args,
        "/jobs/import",
        {"jobs": [{"job_id": job_id, "company": "Authored runtime", "role": "Engineer"}]},
    )
    source = (ROOT / "data/sample_jobs/SYN-01.txt").read_text()
    request(args, f"/jobs/{job_id}/snapshots", {"text": source}, status=201)
    extraction = request(args, f"/jobs/{job_id}/extract", {})
    profile = json.loads((ROOT / "data/sample_candidate.json").read_text())
    revision = request(args, "/candidates/import", profile, status=201)
    match = request(args, f"/jobs/{job_id}/match", profile)
    assert request(args, "/analytics/skills")["N"] == 1
    return job_id, extraction, revision, match


def export_command(project):
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        "docker-compose.yml",
        "exec",
        "-T",
        "api",
    ]


def dev(args):
    control(args, "up", args.project)
    private_routes_absent(args)
    baseline = seed(args)
    command = export_command(args.project)
    subprocess.run(
        [*command, "jobintel", "export", "--output", "/app/results/generated/runtime-check"],
        check=True,
    )
    control(args, "status", args.project)
    control(args, "stop", args.project)
    control(args, "up", args.project, no_build=True)
    private_routes_absent(args)
    job_id, extraction, revision, match = baseline
    current = request(args, f"/jobs/{job_id}")
    assert current["extraction"]["run_id"] == extraction["run_id"]
    assert request(args, f"/match-runs/{match['match_run_id']}")["matches"] == match["matches"]
    saved = request(
        args, f"/candidates/{revision['profile_id']}/revisions/{revision['profile_revision_id']}"
    )
    assert saved["profile_revision_id"] == revision["profile_revision_id"]
    subprocess.run(
        [
            *command,
            "python",
            "-c",
            "from pathlib import Path; assert Path('/app/results/generated/runtime-check/skill_counts.json').is_file()",
        ],
        check=True,
    )
    control(args, "reset", args.project)
    subprocess.run(
        ["docker", "volume", "inspect", args.scope_volume], check=True, capture_output=True
    )
    control(args, "up", args.project, no_build=True)
    assert request(args, "/jobs")["jobs"] == []
    print(
        "Dev persistence passed: source/extraction/profile/matches/outputs survive stop; reset is scoped."
    )


def demo(args):
    project = args.project + "-demo"
    try:
        control(args, "up", project, "demo")
        assert request(args, "/ui/config")["acquisition_mode"] == "synthetic"
        assert len(request(args, "/ui/fixtures")["jobs"]) == 20
        assert request(args, "/ui/reset", {}) == {"reset": True}
        print("Demo isolation passed: explicit synthetic acquisition/fixtures/reset only in demo.")
    finally:
        control(args, "reset", project)


def openai_configuration(args):
    project = args.project + "-openai"
    with TemporaryDirectory(prefix="jobintel-runtime-secret-") as directory:
        key = Path(directory) / "key"
        key.write_text("synthetic-configuration-probe-not-a-real-key")
        key.chmod(0o600)
        environment = {
            **os.environ,
            "JOBINTEL_OPENAI_MODEL": "synthetic-configuration-probe",
            "JOBINTEL_OPENAI_KEY_FILE": str(key),
            "JOBINTEL_CONFIGURATION": "openai_normalized_v1",
        }
        try:
            control(args, "up", project, "openai", environment=environment)
            health = request(args, "/health")
            assert health["provider"] == "openai"
            assert health["configuration"] == "openai_normalized_v1"
            private_routes_absent(args)
            # No extraction/evaluation endpoint is called; readiness is configuration only.
            print("OpenAI configuration passed: mounted synthetic secret; zero upstream requests.")
        finally:
            control(args, "reset", project)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="jobintel-runtime-check")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--ca-bundle")
    args = parser.parse_args()
    if Path.cwd() != ROOT:
        parser.error("Run from the repository root")
    require_fresh_projects(args.project)
    args.scope_volume = args.project + "-scope-" + uuid4().hex[:8]
    subprocess.run(
        [
            "docker",
            "volume",
            "create",
            "--label",
            f"com.docker.compose.project={args.project}-neighbor",
            args.scope_volume,
        ],
        check=True,
        capture_output=True,
    )
    try:
        dev(args)
        # Stop the recreated empty dev app before reusing its loopback port.
        control(args, "stop", args.project)
        demo(args)
        openai_configuration(args)
    finally:
        try:
            control(args, "reset", args.project)
        finally:
            subprocess.run(["docker", "volume", "rm", args.scope_volume], check=True)
    print("Runtime smoke passed; all synthetic projects cleaned up.")


if __name__ == "__main__":
    main()
