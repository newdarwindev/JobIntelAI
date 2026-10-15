"""Пересоздать русские таблицы из сохранённых результатов без вызовов модели."""

import argparse
import json
from pathlib import Path

from jobintel.evaluation_runs import human_summary
from jobintel.experiment_publication import comparison

REPORTS = [
    Path("results/experiments/reviewed-fake"),
    Path("results/network-experiments/emulator"),
    Path("results/network-experiments/local"),
]


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    for directory in REPORTS:
        report = json.loads((directory / "report.json").read_text())
        (directory / "comparison.md").write_text(comparison(report))
    report = json.loads(Path("results/reviewed_fixture_evaluation.json").read_text())
    Path("results/reviewed_fixture_evaluation.txt").write_text(human_summary(report))


if __name__ == "__main__":
    main()
