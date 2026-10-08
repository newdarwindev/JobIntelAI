"""V43: retain actual passing/failing JUnit probes without masking command failure."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def probe(output, failing):
    label = "intentional-failure" if failing else "success"
    target = output / label
    target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="jobintel-evidence-") as directory:
        source = Path(directory) / "test_evidence.py"
        source.write_text(
            "import pytest\n"
            "def test_pass():\n    assert 2 + 2 == 4\n"
            "@pytest.mark.skip(reason='authored skip-count probe, not feature evidence')\n"
            "def test_skip():\n    pass\n"
            + (
                "def test_fail():\n    pytest.fail('deliberate evidence publication probe')\n"
                if failing
                else ""
            )
        )
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            "--confcutdir",
            directory,
            "--junitxml",
            str(target / "junit.xml"),
            str(source),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
    (target / "check.log").write_text(result.stdout + result.stderr)
    subprocess.run(
        [
            sys.executable,
            "scripts/summarize_tests.py",
            "--junit",
            str(target / "junit.xml"),
            "--output",
            str(target / "summary.json"),
            "--exit-code",
            str(result.returncode),
            "--command",
            f"authored pytest publication probe ({label})",
        ],
        check=True,
    )
    summary = json.loads((target / "summary.json").read_text())
    expected = {"passed": 1, "failed": int(failing), "errors": 0, "skipped": 1}
    if result.returncode != int(failing) or any(summary[k] != v for k, v in expected.items()):
        raise SystemExit("JUnit publication probe did not preserve its actual outcome/counts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    probe(args.output.resolve(), False)
    probe(args.output.resolve(), True)


if __name__ == "__main__":
    main()
