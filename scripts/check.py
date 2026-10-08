"""Run the Python CI checks locally; fail immediately on an underlying command failure."""

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str, environment=None):
    print(f"+ {shlex.join(arguments)}", flush=True)
    subprocess.run(arguments, cwd=ROOT, env=environment, check=True)


def smoke(environment, output):
    run(sys.executable, "-m", "alembic", "upgrade", "head", environment=environment)
    run(sys.executable, "-m", "alembic", "check", environment=environment)
    for _ in range(2):
        run(
            sys.executable,
            "-m",
            "jobintel.cli",
            "demo",
            "--output",
            str(output),
            environment=environment,
        )
    run(
        sys.executable,
        "-m",
        "jobintel.cli",
        "evaluate",
        "--output",
        str(output),
        environment=environment,
    )
    run(
        sys.executable,
        "-m",
        "jobintel.cli",
        "export",
        "--output",
        str(output),
        environment=environment,
    )
    counts = json.loads((output / "skill_counts.json").read_text())
    evaluation = json.loads((output / "evaluation.json").read_text())
    if counts["N"] != 20 or evaluation["dataset_size"] != 20 or len(evaluation["results"]) != 2:
        raise SystemExit("Offline smoke result does not match the bundled corpus/configuration.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-postgres", action="store_true")
    parser.add_argument("--junitxml", type=Path)
    args = parser.parse_args()
    if args.require_postgres and not os.getenv("TEST_DATABASE_URL", "").startswith("postgresql"):
        raise SystemExit(
            "--require-postgres needs TEST_DATABASE_URL for a disposable PostgreSQL DB."
        )
    run(sys.executable, "-m", "ruff", "check", ".")
    run(sys.executable, "-m", "ruff", "format", "--check", ".")
    run(sys.executable, "-m", "pip", "check")
    run(sys.executable, "scripts/check_fixtures.py")
    pytest_args = ["--junitxml", str(args.junitxml)] if args.junitxml else []
    run(sys.executable, "-m", "pytest", "-q", "--tb=short", *pytest_args)
    if args.require_postgres:
        postgres_environment = {
            **os.environ,
            "JOBINTEL_DATABASE_URL": os.environ["TEST_DATABASE_URL"],
        }
        run(sys.executable, "-m", "alembic", "check", environment=postgres_environment)
    with TemporaryDirectory(prefix="jobintel-check-") as directory:
        temporary = Path(directory)
        environment = {
            **os.environ,
            "JOBINTEL_DATABASE_URL": f"sqlite:///{temporary / 'smoke.db'}",
            "JOBINTEL_FIXTURE_ROOT": str(ROOT / "data"),
            "JOBINTEL_PROVIDER": "fixture",
        }
        smoke(environment, temporary / "results")
        experiment_smoke(environment, temporary)
        run(sys.executable, "-m", "build", "--outdir", str(temporary / "dist"))
        packaging_smoke(temporary)
    print("Python quality gates passed.")


def packaging_smoke(temporary):
    target = temporary / "installed-wheel"
    wheel = next((temporary / "dist").glob("*.whl"))
    run(sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel))
    code = (
        "import pathlib, sys; sys.path.insert(0, sys.argv[1]); import jobintel; "
        "from jobintel.openai_provider import OpenAIProvider; "
        "from jobintel.openai_transport import HttpOpenAITransport; "
        "from jobintel.provider_config import strict_schema; "
        "assert pathlib.Path(jobintel.__file__).is_relative_to(sys.argv[1]); "
        "assert strict_schema()['additionalProperties'] is False; "
        "print('Installed wheel adapter/policy imports passed')"
    )
    run(sys.executable, "-I", "-c", code, str(target))


def experiment_smoke(environment, temporary):
    corpus = temporary / "corpus.json"
    report = temporary / "experiment"
    reproduced = temporary / "reproduced.json"
    common = [sys.executable, "-m", "jobintel.cli", "experiment"]
    run(*common, "freeze", "--output", str(corpus), environment=environment)
    run(*common, "run", "--corpus", str(corpus), "--output", str(report), environment=environment)
    run(
        *common,
        "rescore",
        "--report",
        str(report / "report.json"),
        "--output",
        str(reproduced),
        environment=environment,
    )
    if reproduced.read_bytes() != (report / "scores.json").read_bytes():
        raise SystemExit("Saved experiment scores are not reproducible.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None
