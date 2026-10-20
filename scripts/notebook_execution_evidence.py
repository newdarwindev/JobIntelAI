"""Сформировать публичные доказательства EXEC через общий notebook CLI."""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

from jobintel.experiment_corpus import write_json
from jobintel.experiments import code_provenance
from jobintel.notebook_artifacts import verify_manifest


def cli_request(config, temporary):
    path = temporary / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "jobintel.cli", "notebook", "run", "--config", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def counts(path):
    cases = ET.parse(path).getroot().findall(".//testcase")
    failed = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    return {
        "file": path.name,
        "tests": len(cases),
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "passed": len(cases) - failed - errors - skipped,
    }


def execute(output, temporary):
    fixture = cli_request({"output": str(output / "fixture")}, temporary)
    saved = cli_request(
        {
            "mode": "saved-report",
            "report": str(output / "fixture/report.json"),
            "output": str(output / "saved"),
        },
        temporary,
    )
    refused = cli_request({"output": str(output / "refused"), "corpus_sha256": "0" * 64}, temporary)
    if (fixture.returncode, saved.returncode, refused.returncode) != (0, 0, 2):
        raise SystemExit("Notebook run не дал требуемых фактических исходов.")
    if (output / "refused").exists() or "corpus_checksum" not in refused.stderr:
        raise SystemExit("Preflight refusal allocated output or lost its bounded error code.")
    for name in ["fixture", "saved"]:
        verify_manifest(output / name / "manifest.json")
    same = (output / "fixture/scores.json").read_bytes() == (
        output / "saved/scores.json"
    ).read_bytes()
    if not same:
        raise SystemExit("Saved scores did not reproduce byte-for-byte.")
    return {
        "fixture": json.loads(fixture.stdout),
        "saved": json.loads(saved.stdout),
        "refused": {"exit_code": 2, "error_code": "corpus_checksum", "output_created": False},
        "saved_scores_byte_identical": same,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/notebook-execution"))
    parser.add_argument("--junit", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(prefix="jobintel-exec-proof-") as directory:
        outcomes = execute(args.output, Path(directory))
    report = {
        "evidence": "authored fixture execution and saved rescore; no model inference",
        "python": sys.version.split()[0],
        "code": code_provenance(),
        "outcomes": outcomes,
        "tests": [counts(path) for path in args.junit],
    }
    write_json(args.output / "evidence.json", report)
    summary = "\n".join(
        f"| {r['file']} | {r['passed']} | {r['failed']} | {r['errors']} | {r['skipped']} |"
        for r in report["tests"]
    )
    text = f"""# Доказательства notebook execution

Кратко: реальный offline fixture run, точный пересчёт сохранённых scores и отказ
preflight без создания output. Эти результаты не измеряют качество LLM.

Исходный коммит: `{report["code"]["git_commit"]}`; dirty: `{report["code"]["git_dirty"]}`.
SHA-256 исходного Python-кода: `{report["code"]["source_sha256"]}`.

| Сценарий | Видимый результат | Доказательства |
| --- | --- | --- |
| Fixture | succeeded; fake evidence; tokens/cost не измерялись | [manifest](fixture/manifest.json), [report](fixture/report.json), [сравнение](fixture/comparison.md) |
| Сохранённый report | succeeded; без новой inference; scores совпадают побайтово | [manifest](saved/manifest.json), [scores](saved/scores.json) |
| Неверный corpus pin | exit 2, corpus_checksum; output не создан | [Структурированные исходы](evidence.json) |

| Результат тестов | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
{summary}

Полные [машинные данные](evidence.json) сохраняют фактические исходы и counts.
Skips не доказывают реализацию. Проверки новых kernels отдельно выполняются
в Actions под Python 3.11/3.12 и публикуют `notebook-kernel.json`.

Воспроизведение из корня репозитория в новый output directory:

```bash
python -m scripts.notebook_execution_evidence --output work/notebook-evidence
```

Training execution — отдельная реализация в issue #81. Этот интерфейс
отказывает при недоступном training runner до создания output.
"""
    (args.output / "README.md").write_text(text, encoding="utf-8")
    print(f"Доказательства notebook execution: {args.output / 'README.md'}")


if __name__ == "__main__":
    main()
