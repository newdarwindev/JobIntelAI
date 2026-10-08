"""Publish synthetic-only JUnit counts and final-commit CI provenance."""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def test_counts(path):
    if not path.is_file():
        return dict.fromkeys(["tests", "passed", "failed", "errors", "skipped"])
    # Count leaf testcases rather than suite attributes, which can be nested totals.
    cases = list(ET.parse(path).getroot().iter("testcase"))
    counts = {
        "tests": len(cases),
        "failed": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
    }
    counts["passed"] = counts["tests"] - sum(counts[k] for k in ["failed", "errors", "skipped"])
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--command",
        default="python scripts/check.py --require-postgres --junitxml work/ci/junit.xml",
    )
    parser.add_argument("--exit-code", type=int)
    args = parser.parse_args()
    report = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": os.getenv("PYTHON_VERSION", sys.version.split()[0]),
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        "run_url": (
            f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
            f"{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
        )
        if os.getenv("GITHUB_RUN_ID")
        else None,
        "config": "fake providers / synthetic corpus / disposable PostgreSQL",
        "command": args.command,
        "exit_code": args.exit_code,
        **test_counts(args.junit),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as output:
            output.write(
                f"Backend evidence for `{report['commit']}`: {report['passed']} passed, "
                f"{report['failed']} failed, {report['errors']} errors, {report['skipped']} skipped.\n\n"
                "Download backend-evidence for JUnit, command logs and configuration provenance.\n"
            )


if __name__ == "__main__":
    main()
