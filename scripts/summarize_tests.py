"""Publish synthetic-only JUnit counts and final-commit CI provenance."""

import argparse
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": os.getenv("PYTHON_VERSION"),
        "config": "fake providers / synthetic corpus / disposable PostgreSQL",
        "command": "python scripts/check.py --require-postgres --junitxml work/ci/junit.xml",
        "tests": None,
        "passed": None,
        "failed": None,
        "errors": None,
        "skipped": None,
    }
    if args.junit.is_file():
        suites = list(ET.parse(args.junit).getroot().iter("testsuite"))
        counts = {
            key: sum(int(s.attrib.get(key, 0)) for s in suites)
            for key in ["tests", "failures", "errors", "skipped"]
        }
        report.update(
            tests=counts["tests"],
            failed=counts["failures"],
            errors=counts["errors"],
            skipped=counts["skipped"],
            passed=counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"],
        )
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
