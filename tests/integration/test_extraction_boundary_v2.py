"""V19, V21-V23: exercise migrated SQLite and disposable PostgreSQL boundaries."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url

from jobintel import db
from jobintel.api import create_app
from jobintel.schemas import JobInput, SnapshotInput
from jobintel.service import Service

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


@pytest.fixture(params=["sqlite", "postgres"])
def isolated_database(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path / 'migrated.db'}"
        return
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not provided")
    if not url.startswith("postgresql"):
        pytest.fail("requires a disposable PostgreSQL database")
    schema = "issue2_" + uuid4().hex
    engine = create_engine(url)
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


def migrate(url, target, monkeypatch):
    monkeypatch.setenv("JOBINTEL_DATABASE_URL", url)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def malformed(provider, source, case):
    payload = provider.extract(source, "fixture_normalized").model_dump(mode="json")
    row = payload["requirements"][0]
    if case == "missing":
        del payload["geography"]["evidence"]
    elif case == "shifted":
        payload["work_mode"]["evidence"]["start"] = 0
    elif case == "irrelevant":
        phrase = "This fictional posting is authored for a public engineering demo."
        start = source.index(phrase)
        payload["geography"]["evidence"] = {
            "start": start,
            "end": start + len(phrase),
            "quote": phrase,
        }
    elif case == "filter":
        payload["filters"] = [{"kind": "travel", "value": "Georgia", "evidence": row["evidence"]}]
    elif case == "years":
        row["years_required"] = {"minimum": 99}
    elif case == "production":
        row["production_obligation"] = "MUST"
        row["explicit_production_required"] = True
    elif case == "schema":
        payload["schema_version"] = 1
    elif case == "version":
        row["skills"] = ["AWS 1.23+"]
        row["version_constraints"][0].update(product="AWS", skill="AWS 1.23+")
    return payload


@pytest.mark.parametrize(
    "case",
    ["missing", "shifted", "irrelevant", "filter", "years", "production", "schema", "version"],
)
def test_v19_malformed_provider_is_atomic_and_keeps_current_run(
    isolated_database, monkeypatch, case
):
    migrate(isolated_database, "head", monkeypatch)
    engine = create_engine(isolated_database)
    fixture = "SYN-15" if case == "version" else "SYN-10"
    source = (DATA / f"sample_jobs/{fixture}.txt").read_text()
    with TestClient(create_app(isolated_database, DATA)) as client:
        assert (
            client.post(
                "/jobs/import",
                json={"jobs": [{"job_id": "atomic", "company": "Synthetic", "role": "Engineer"}]},
            ).status_code
            == 200
        )
        assert client.post("/jobs/atomic/snapshots", json={"text": source}).status_code == 201
        saved = client.post("/jobs/atomic/extract", json={}).json()
        payload = malformed(client.app.state.provider, source, case)

        class FaultyProvider:
            def extract(self, text, configuration):
                return payload

        client.app.state.provider = FaultyProvider()
        assert client.post("/jobs/atomic/extract", json={}).status_code == 422
        current = client.get("/jobs/atomic").json()["extraction"]
        assert current["run_id"] == saved["run_id"]
        assert current["schema_version"] == current["stored_schema_version"] == 2
        with engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(db.ExtractionRun)) == 1
            assert connection.scalar(select(func.count()).select_from(db.RequirementRow)) == 1
    engine.dispose()


def test_v19_migration_preserves_legacy_payloads_and_api_reads(isolated_database, monkeypatch):
    migrate(isolated_database, "e44d9dbe9d1d", monkeypatch)
    factory = db.session_factory(isolated_database)
    with factory.begin() as session:
        svc = Service(session, None)
        svc.import_jobs([JobInput(job_id="legacy", company="Synthetic legacy", role="Engineer")])
        snapshot = svc.snapshot("legacy", SnapshotInput(text="Our company address is Berlin."))
        snapshot_id = snapshot.id
    legacy = {
        "requirements": [],
        "responsibilities": [],
        "geography": "Berlin",
        "work_mode": "remote",
    }
    table = Table("extraction_runs", MetaData(), autoload_with=factory.kw["bind"])
    with factory.kw["bind"].begin() as connection:
        connection.execute(
            table.insert().values(
                id="legacy-run",
                snapshot_id=snapshot_id,
                configuration="fixture_normalized",
                created_at="2026-10-08T00:00:00Z",
                payload=legacy,
            )
        )
    migrate(isolated_database, "head", monkeypatch)
    with factory() as session:
        record = session.get(db.ExtractionRun, "legacy-run")
        assert record.schema_version == 1
        assert record.payload == legacy
    assert "schema_version" in {
        c["name"] for c in inspect(factory.kw["bind"]).get_columns("extraction_runs")
    }
    with TestClient(create_app(isolated_database, DATA)) as client:
        result = client.get("/jobs/legacy").json()["extraction"]
        assert result["stored_schema_version"] == 1
        assert result["schema_version"] == 2
        assert result["geography"] is result["work_mode"] is result["filters"] is None
        assert (
            client.get("/jobs/legacy/history").json()["snapshots"][0]["runs"][0]["run_id"]
            == "legacy-run"
        )
    factory.kw["bind"].dispose()


def test_v21_v22_fixture_obligations_versions_and_unknown_matching(client):
    registry = (DATA / "sample_registry.csv").read_text()
    assert client.post("/jobs/import", json={"csv_text": registry}).status_code == 200
    for job_id in ["SYN-04", "SYN-05", "SYN-14", "SYN-15"]:
        source = (DATA / f"sample_jobs/{job_id}.txt").read_text()
        assert client.post(f"/jobs/{job_id}/snapshots", json={"text": source}).status_code == 201
        assert client.post(f"/jobs/{job_id}/extract", json={}).status_code == 200
    preferred = client.get("/jobs/SYN-14").json()["extraction"]["requirements"][1]
    assert preferred["experience_obligation"] == preferred["production_obligation"] == "PREFERRED"
    assert preferred["explicit_production_required"] is False
    version = client.get("/jobs/SYN-15").json()["extraction"]["requirements"][0]
    assert version["skills"] == ["Go 1.23+"]
    assert version["version_constraints"][0]["product"] == "Go"
    profile = {"profile_id": "synthetic", "complete": True, "evidence": []}
    matched = client.post("/jobs/SYN-15/match", json=profile).json()
    assert matched["matches"][0]["status"] == "UNKNOWN"
    assert json.dumps(version, ensure_ascii=False).find("Golang 1.23+") >= 0
