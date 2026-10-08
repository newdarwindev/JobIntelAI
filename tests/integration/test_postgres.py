"""Opt-in only: TEST_DATABASE_URL must be a disposable database, never private data."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from jobintel.api import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.postgres
def test_postgres_migrations_and_api(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not provided")
    if not url.startswith("postgresql"):
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    monkeypatch.setenv("JOBINTEL_DATABASE_URL", url)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True)
    engine = create_engine(url)
    assert {"jobs", "posting_snapshots", "requirements", "matches", "evaluation_runs"}.issubset(
        inspect(engine).get_table_names()
    )
    with TestClient(create_app(url, ROOT / "data")) as client:
        assert client.get("/health").status_code == 200
        assert (
            client.post(
                "/jobs/import",
                json={
                    "jobs": [{"job_id": "pg-test", "company": "Synthetic PG", "role": "Engineer"}]
                },
            ).status_code
            == 200
        )
        text = (ROOT / "data/sample_jobs/SYN-01.txt").read_text()
        assert client.post("/jobs/pg-test/snapshots", json={"text": text}).status_code == 201
        assert client.post("/jobs/pg-test/extract", json={}).status_code == 200
        assert client.get("/jobs").json()["jobs"][0]["job_id"] == "pg-test"
        assert client.get("/jobs/pg-test/history").json()["snapshots"][0]["runs"]
        assert client.get("/analytics/skills").json()["N"] >= 1
        assert client.get("/analytics/skills?applied=true").json()["N"] == 0
    engine.dispose()
