"""Сравнить legacy bulk и bounded v2 reads на временных синтетических БД."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url

from jobintel.api import create_app
from jobintel.experiments import code_provenance
from jobintel.schemas import JobInput, SnapshotInput
from jobintel.service import Service

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def disposable_url(kind, directory):
    if kind == "sqlite":
        yield f"sqlite:///{directory}/benchmark.db"
        return
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        raise ValueError("PostgreSQL benchmark requires a disposable TEST_DATABASE_URL")
    schema = "catalogue_" + uuid4().hex
    engine = create_engine(url, hide_parameters=True)
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        yield (
            make_url(url)
            .update_query_dict({"options": f"-csearch_path={schema}"})
            .render_as_string(hide_password=False)
        )
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        engine.dispose()


def populate(client, start, stop):
    source = (ROOT / "data/sample_jobs/SYN-01.txt").read_text()
    with client.app.state.session_factory.begin() as session:
        service = Service(session, client.app.state.provider)
        for index in range(start, stop):
            job_id = f"MEASURE-{index:05}"
            service.import_jobs(
                [JobInput(job_id=job_id, company=f"Authored measurement {index}", role="Engineer")]
            )
            service.snapshot(job_id, SnapshotInput(text=source))
            service.extract(job_id, "fixture_normalized")


def measure(client, endpoint):
    engine = client.app.state.session_factory.kw["bind"]
    statements = []

    def count(_connection, _cursor, statement, *_rest):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    started = perf_counter()
    try:
        response = client.get(endpoint)
        elapsed = perf_counter() - started
    finally:
        event.remove(engine, "before_cursor_execute", count)
    response.raise_for_status()
    return {
        "endpoint": endpoint,
        "http_status": response.status_code,
        "sql_statements": len(statements),
        "select_statements": sum(s.lstrip().upper().startswith("SELECT") for s in statements),
        "response_bytes": len(response.content),
        "returned_jobs": len(response.json()["jobs"]),
        "elapsed_seconds": elapsed,
        "selected_source_body_columns": any(
            "clean_text" in s or "raw_text" in s for s in statements
        ),
    }


def benchmark(kind, sizes):
    rows = []
    with TemporaryDirectory(prefix="jobintel-catalogue-") as directory:
        with disposable_url(kind, directory) as url:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                env={**os.environ, "JOBINTEL_DATABASE_URL": url},
                check=True,
                capture_output=True,
            )
            with TestClient(
                create_app(
                    url,
                    ROOT / "data",
                    provider_name="fixture",
                    configuration="fixture_normalized",
                )
            ) as client:
                previous = 0
                for size in sizes:
                    populate(client, previous, size)
                    previous = size
                    legacy, bounded = measure(client, "/jobs"), measure(client, "/v2/jobs?limit=20")
                    if (
                        bounded["select_statements"] != 2
                        or bounded["returned_jobs"] != min(size, 20)
                        or bounded["selected_source_body_columns"]
                    ):
                        raise ValueError("bounded catalogue query or payload contract failed")
                    rows.append(
                        {
                            "database": kind,
                            "registered_extracted_jobs": size,
                            "legacy": legacy,
                            "bounded": bounded,
                        }
                    )
    return rows


def publish(output, rows):
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "code_provenance": code_provenance(),
        "input_provenance": {
            "provider": "fixture",
            "configuration": "fixture_normalized",
            "sha256": {
                name: sha256((ROOT / name).read_bytes()).hexdigest()
                for name in [
                    "data/sample_jobs/SYN-01.txt",
                    "data/provider_responses.json",
                    "data/taxonomy.json",
                    "scripts/catalogue_benchmark.py",
                ]
            },
        },
        "execution": "actual migrated SQLite/PostgreSQL, authored fixture replay, no paid calls",
        "comparison": "legacy compatible v1 bulk algorithm and v2 bounded summaries on identical records",
        "rows": rows,
    }
    (output / "catalogue-performance.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "catalogue-performance.md").write_text(catalogue_markdown(report))


def catalogue_markdown(report):
    rows = report["rows"]
    table = [
        "| База | Вакансий | Legacy SQL / bytes | Bounded SQL / bytes | Возвращено вакансий |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        before, after = row["legacy"], row["bounded"]
        table.append(
            f"| {row['database']} | {row['registered_extracted_jobs']} | {before['sql_statements']} / {before['response_bytes']:,} | {after['sql_statements']} / {after['response_bytes']:,} | {after['returned_jobs']} |"
        )
    lines = [
        "# Измеренное сравнение запросов и размера ответов реестра",
        "",
        report["execution"],
        "",
        "[Полные измерения и provenance](catalogue-performance.json). Legacy endpoint сохранён для совместимости, навигация использует v2. Для каждого размера алгоритмы читают одинаковые frozen synthetic records. V2 выполняет два SELECT, SQLite дополнительно BEGIN. Bounded SQL/payload не содержит source/extraction bodies. Локальное время сохранено в JSON; это не throughput или production-scale benchmark.",
        "",
        *table,
        "",
        "Воспроизведение: `make catalogue-check`. Команда создаёт собственную временную PostgreSQL, если disposable TEST_DATABASE_URL не задан. Отдельная PostgreSQL schema и временная SQLite изолируют каждый запуск и удаляются после него. Ввод — авторский SYN-01 fixture replay. Empty success, latest source и history отдельно проверяют integration tests и UI15.",
        "",
        "[Запись UI15 desktop](../../ui-recordings/UI15-desktop-chromium.webm) · [Запись UI15 mobile](../../ui-recordings/UI15-mobile-chromium.webm)",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/issue-evidence/47"))
    parser.add_argument("--sizes", type=int, nargs="+", default=[1, 10, 20, 100, 500])
    args = parser.parse_args()
    if (
        sorted(set(args.sizes)) != args.sizes
        or not args.sizes
        or args.sizes[0] < 1
        or args.sizes[-1] > 1000
    ):
        parser.error("sizes должны быть различными возрастающими целыми в 1..1000")
    rows = [row for kind in ["sqlite", "postgres"] for row in benchmark(kind, args.sizes)]
    publish(args.output, rows)
    print(f"Опубликовано реальных сравнений реестра: {len(rows)}.")


if __name__ == "__main__":
    main()
