"""Повторяемый fixture freeze/plan/run/rescore; failures сохраняют ненулевой exit code."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts.tasks import run


def replay(output, dataset):
    output.mkdir(parents=True, exist_ok=False)
    common = [sys.executable, "-m", "jobintel.cli", "experiment"]
    corpus, report = output / "corpus.json", output / "run"
    run(*common, "freeze", "--dataset", dataset, "--output", str(corpus))
    run(*common, "plan", "--corpus", str(corpus), "--output", str(output / "plan.json"))
    result = subprocess.run(
        [*common, "run", "--provider", "fake", "--corpus", str(corpus), "--output", str(report)],
        check=False,
    )
    if result.returncode not in {0, 1} or not (report / "scores.json").is_file():
        return result.returncode or 1
    reproduced = output / "reproduced.json"
    run(*common, "rescore", "--report", str(report / "report.json"), "--output", str(reproduced))
    if json.loads(reproduced.read_text()) != json.loads((report / "scores.json").read_text()):
        raise ValueError("Повторный подсчёт не совпадает с сохранёнными scores")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="Новая папка в ignored local_data/"
    )
    parser.add_argument("--dataset", choices=["reviewed", "fixture"], default="reviewed")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(Path("local_data").resolve()):
        parser.error("Выходные файлы должны оставаться в local_data/")
    raise SystemExit(replay(args.output, args.dataset))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None
