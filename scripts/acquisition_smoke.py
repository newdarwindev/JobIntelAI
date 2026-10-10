"""Run real PostgreSQL/API/origin/TLS/proxy container checks without Internet fetches."""

import argparse
import http.client
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from scripts.acquisition_environment import diagnostics
from scripts.acquisition_fixtures.certificates import certificates

ROOT = Path(__file__).resolve().parents[1]


def request(port, path, payload=None, status=200):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        connection.request(
            "GET" if payload is None else "POST",
            path,
            body=json.dumps(payload) if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == status, (path, response.status, status)
        return json.loads(response.read())
    finally:
        connection.close()


def fetch_case(port, job, url, status=201):
    request(
        port,
        "/jobs/import",
        {
            "jobs": [
                {
                    "job_id": job,
                    "company": f"Authored {job}",
                    "role": "Wire fixture",
                    "official_url": url,
                }
            ]
        },
    )
    return request(port, f"/jobs/{job}/fetch", {}, status)


def success_cases(port, results):
    for scheme, path in [
        ("http", "text"),
        ("https", "authored-job"),
        ("https", "gzip"),
        ("https", "deflate"),
        ("https", "chunked"),
        ("https", "retry-success"),
        ("https", "server-success"),
    ]:
        job = path
        report = fetch_case(port, job, f"{scheme}://example.com/{path}")
        assert report["snapshot_id"] and report["attempts"][-1]["status"] == "success"
        snapshot = request(port, f"/jobs/{job}")["snapshot"]
        assert snapshot["clean_text"] == (ROOT / "data/sample_jobs/SYN-01.txt").read_text().strip()
        assert request(port, f"/jobs/{job}/fetch", {}, 201)["snapshot_id"] == snapshot["id"]
        if path in {"retry-success", "server-success"}:
            assert len(report["attempts"]) == 3
        request(port, f"/jobs/{job}/extract", {})
        results.append({"case": f"{scheme}/{path}", "status": "passed"})


def failure_cases(port, results):
    cases = [
        ("authored-denied", 403, "access_denied"),
        ("authored-js", 422, "js_only"),
        ("captcha", 403, "captcha"),
        ("oversized", 413, "body_too_large"),
        ("oversized-chunked", 413, "body_too_large"),
        ("gzip-bomb", 413, "body_too_large"),
        ("rate-limit", 503, "rate_limit"),
        ("server-error", 502, "server_error"),
        ("loop", 422, "redirect_loop"),
        ("redirect/4", 422, "redirect_limit"),
    ]
    for index, (path, status, code) in enumerate(cases):
        report = fetch_case(port, f"failure-{index}", f"https://example.com/{path}", status)
        assert report["detail"]["code"] == code and report["snapshot_id"] is None
        assert report["detail"]["manual_fallback"]
        if path in {"rate-limit", "server-error"}:
            assert len(report["attempts"]) == 3
        results.append({"case": path, "status": "passed"})


def negative_cases(port, project, trust, results):
    for index, url in enumerate(
        [
            "http://localhost/",
            "http://127.0.0.1/",
            "https://10.0.0.1/",
            "https://mixed.example.test/authored-final",
        ]
    ):
        before = diagnostics(project, trust)
        report = fetch_case(port, f"negative-{index}", url, 422)
        assert report["detail"]["code"] == "blocked_destination"
        assert diagnostics(project, trust) == before
        results.append({"case": f"blocked-{index}", "status": "passed"})
    for host, code in [
        ("wrong.example.test", "tls_error"),
        ("denied.example.test", "proxy_denied"),
    ]:
        before = diagnostics(project, trust)["origin"]["counts"].copy()
        report = fetch_case(port, host.split(".")[0], f"https://{host}/authored-final", 502)
        assert report["detail"]["code"] == code
        after = diagnostics(project, trust)["origin"]["counts"]
        assert {k: v for k, v in before.items() if k != "tls"} == {
            k: v for k, v in after.items() if k != "tls"
        }
        results.append({"case": code, "status": "passed"})


def recovery(port, results):
    source = (ROOT / "data/sample_jobs/SYN-01.txt").read_text()
    job = "failure-0"
    prior = request(port, f"/jobs/{job}/snapshots", {"text": source}, 201)
    run = request(port, f"/jobs/{job}/extract", {})["run_id"]
    request(port, f"/jobs/{job}/fetch", {}, 403)
    assert request(port, f"/jobs/{job}")["extraction"]["run_id"] == run
    new = request(port, f"/jobs/{job}/snapshots", {"text": source + "\n"}, 201)
    assert (
        new["snapshot_id"] != prior["snapshot_id"] and new["content_hash"] == prior["content_hash"]
    )
    request(port, f"/jobs/{job}/extract", {})
    history = request(port, f"/jobs/{job}/history")
    assert len(history["snapshots"]) == 2 and history["acquisition_attempts"]
    results.append({"case": "immutable-history-manual-recovery", "status": "passed"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18085)
    parser.add_argument("--ca-bundle", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "work/acquisition-service.json")
    args = parser.parse_args()
    project = "jobintel-acquisition-" + uuid4().hex[:12]
    results = []
    failure = None
    with TemporaryDirectory(prefix="jobintel-acquisition-") as directory:
        trust = certificates(Path(directory) / "trust")
        environment = {
            **os.environ,
            "JOBINTEL_ACQUISITION_TRUST_DIR": str(trust),
            "JOBINTEL_API_PORT": str(args.port),
        }
        command = [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.acquisition.yml",
            "-f",
            "docker-compose.acquisition-api.yml",
        ]
        if args.offline:
            command += ["-f", "docker-compose.offline.yml"]
        if args.ca_bundle:
            command += ["-f", "docker-compose.proxy.yml"]
            environment["JOBINTEL_CA_BUNDLE"] = str(args.ca_bundle.resolve())
        try:
            subprocess.run(
                [*command, "up", "-d", "--build", "--wait", "--wait-timeout", "120"],
                env=environment,
                check=True,
            )
            assert request(args.port, "/ui/config")["acquisition_mode"] == "fixture-policy-proxy"
            success_cases(args.port, results)
            failure_cases(args.port, results)
            negative_cases(args.port, project, trust, results)
            recovery(args.port, results)
        except BaseException as error:
            failure = type(error).__name__
            raise
        finally:
            try:
                try:
                    observed = diagnostics(project, trust)
                except (OSError, subprocess.CalledProcessError, ValueError):
                    observed = {"unavailable": True}
                evidence = {
                    "cases": results,
                    "passed": len(results),
                    "failed": int(failure == "AssertionError"),
                    "errors": int(failure is not None and failure != "AssertionError"),
                    "skipped": 0,
                    "completed": failure is None,
                    "failure_kind": failure,
                    "database": "PostgreSQL",
                    "transport": "production policy-proxy; gateway DNS/pinning leases; verified scoped CA",
                    "commit": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], text=True
                    ).strip(),
                    "diagnostics": observed,
                }
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(evidence, indent=2) + "\n")
            finally:
                subprocess.run([*command, "down", "--volumes"], env=environment, check=True)
    print(f"Acquisition container checks: {len(results)} passed; 0 failed/skipped.")


if __name__ == "__main__":
    main()
