"""Check the actual container API after the demo, without requiring app dependencies."""

import json
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"


def request(path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(BASE + path, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def main():
    health = request("/health")
    if health["database"] != "ok" or health["provider"] != "fixture":
        raise SystemExit("Container DB/provider readiness failed.")
    job = request("/jobs/SYN-01")
    text = job["snapshot"]["clean_text"]
    for requirement in job["extraction"]["requirements"]:
        evidence = requirement["evidence"]
        if text[evidence["start"] : evidence["end"]] != evidence["quote"]:
            raise SystemExit("Container extraction evidence does not match the stored snapshot.")
    if job["extraction"]["requirements"][1]["skills"] != ["PostgreSQL"]:
        raise SystemExit("Container normalization failed.")
    summary = request("/analytics/skills")
    if summary["N"] != 20:
        raise SystemExit("Container analytics denominator is wrong.")
    report = request("/evaluate", {})
    if report["dataset_size"] != 20 or len(report["results"]) != 2:
        raise SystemExit("Container fixture evaluation is incomplete.")
    print("Container API passed: readiness, evidence, normalization, N=20 and evaluation.")


if __name__ == "__main__":
    main()
