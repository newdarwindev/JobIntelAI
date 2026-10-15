"""S13: bounded, compatible catalogues on migrated SQLite and PostgreSQL."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from jobintel import db
from jobintel.api import create_app
from jobintel.schemas import JobInput, SnapshotInput
from jobintel.service import Service
from tests.integration.test_extraction_boundary_v2 import DATA, migrate
from tests.integration.test_extraction_boundary_v2 import isolated_database as isolated_database


@pytest.fixture
def catalogue_client(isolated_database, monkeypatch):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        yield client


def seed_jobs(client, count):
    with client.app.state.session_factory.begin() as session:
        service = Service(session, client.app.state.provider)
        for index in range(count):
            job_id = f"PAGE-{index:04}"
            service.import_jobs(
                [JobInput(job_id=job_id, company=f"Authored {index}", role="Engineer")]
            )
            service.snapshot(
                job_id, SnapshotInput(text=(DATA / "sample_jobs/SYN-01.txt").read_text())
            )
            service.extract(job_id, "fixture_normalized")


def collect(client, path, *, limit=7):
    result, cursor = [], None
    while True:
        response = client.get(
            path, params={"limit": limit, **({"cursor": cursor} if cursor else {})}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        result.extend(body.get("items", body.get("jobs")))
        assert len(body.get("items", body.get("jobs"))) <= limit
        cursor = body["page"]["next_cursor"]
        if not cursor:
            return result


def measured_get(client, path):
    engine = client.app.state.session_factory.kw["bind"]
    statements = []

    def record(_connection, _cursor, statement, *_rest):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get(path)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    return response, statements


def test_s13_registry_pages_constant_queries_no_source_bodies_and_legacy(catalogue_client):
    client = catalogue_client
    seed_jobs(client, 1)
    small, small_sql = measured_get(client, "/v2/jobs?limit=5")
    seed_more = 64
    with client.app.state.session_factory.begin() as session:
        service = Service(session, client.app.state.provider)
        for i in range(1, seed_more + 1):
            service.import_jobs(
                [JobInput(job_id=f"PAGE-{i:04}", company=f"Synthetic {i}", role="Engineer")]
            )
    large, large_sql = measured_get(client, "/v2/jobs?limit=5")
    assert len(small_sql) == len(large_sql) <= 3
    assert all(
        "clean_text" not in statement and "raw_text" not in statement for statement in large_sql
    )
    assert len(large.content) < 4000
    assert large.json()["totals"] == {
        "registered": 65,
        "snapshotted": 1,
        "extracted": 1,
        "requirements": 2,
    }
    jobs = collect(client, "/v2/jobs")
    assert [j["job_id"] for j in jobs] == [f"PAGE-{i:04}" for i in range(65)]
    assert "requirements" not in small.json()["jobs"][0]["extraction"]
    full = client.get("/jobs/PAGE-0000").json()
    assert full["snapshot"]["clean_text"] and len(full["extraction"]["requirements"]) == 2
    assert len(client.get("/jobs").json()["jobs"]) == 65


def test_s13_latest_source_empty_and_selection_bound_cursors(catalogue_client):
    client = catalogue_client
    seed_jobs(client, 3)
    old = client.get("/jobs/PAGE-0000").json()
    new = client.post("/jobs/PAGE-0000/snapshots", json={"text": "Authored changed source."}).json()
    empty = (DATA / "sample_jobs/SYN-18.txt").read_text()
    assert client.post("/jobs/PAGE-0001/snapshots", json={"text": empty}).status_code == 201
    assert client.post("/jobs/PAGE-0001/extract", json={}).status_code == 200
    jobs = client.get("/v2/jobs").json()["jobs"]
    assert jobs[0]["snapshot"]["id"] == new["snapshot_id"]
    assert jobs[0]["extraction"] is None
    # Successful empty results count as extracted, never as pending.
    assert jobs[1]["extraction"]["requirement_count"] == 0
    assert (
        client.get("/v2/jobs", params={"pipeline": "Extracted"}).json()["totals"]["extracted"] == 2
    )
    assert [
        j["job_id"]
        for j in client.get("/v2/jobs", params={"pipeline": "Source ready"}).json()["jobs"]
    ] == ["PAGE-0000"]
    assert (
        client.get("/v2/jobs", params={"q": "PAGE-0002"}).json()["jobs"][0]["job_id"] == "PAGE-0002"
    )
    assert client.get("/v2/jobs", params={"q": "%"}).json()["jobs"] == []
    cursor = client.get("/v2/jobs?limit=1").json()["page"]["next_cursor"]
    for params in [
        {"cursor": cursor, "q": "changed"},
        {"cursor": "bad"},
        {"limit": 0},
        {"limit": 101},
        {"pipeline": "invalid"},
    ]:
        assert client.get("/v2/jobs", params=params).status_code == 422
    exported = client.post(
        "/exports",
        json={
            "kind": "evidence",
            "historical": True,
            "job_ids": ["PAGE-0000"],
            "run_ids": [old["extraction"]["run_id"]],
        },
    )
    assert exported.status_code == 200
    assert old["extraction"]["run_id"] in exported.text


def seed_histories(client):
    seed_jobs(client, 1)
    with client.app.state.session_factory.begin() as session:
        snapshot = session.query(db.Snapshot).one()
        template = session.query(db.ExtractionRun).one()
        for i in range(25):
            session.add(
                db.Snapshot(
                    id=f"{i + 1:032x}",
                    job_id=snapshot.job_id,
                    raw_text="private raw body",
                    clean_text="private clean body",
                    content_hash="f" * 64,
                    fetched_at="2020-01-01",
                )
            )
            session.add(
                db.ExtractionRun(
                    id=f"{i + 101:032x}",
                    snapshot_id=snapshot.id,
                    configuration="fixture_normalized",
                    schema_version=2,
                    created_at="2020-01-01",
                    payload=template.payload,
                )
            )
            session.add(
                db.CandidateEvidenceRow(
                    id=f"{i + 201:032x}",
                    profile_id="paged",
                    created_at="2020-01-01",
                    payload={"private": "profile body"},
                )
            )
            session.add(
                db.EvaluationRun(
                    id=f"{i + 301:032x}",
                    created_at="2020-01-01",
                    payload={
                        "dataset": "reviewed",
                        "status": "partial",
                        "private": "predictions body",
                    },
                )
            )
        return snapshot.id


def test_s13_history_catalogues_ties_scope_and_explicit_detail(catalogue_client):
    client = catalogue_client
    snapshot_id = seed_histories(client)
    paths = [
        "/v2/jobs/PAGE-0000/snapshots",
        f"/v2/jobs/PAGE-0000/snapshots/{snapshot_id}/runs",
        "/v2/candidates/paged/revisions",
        "/v2/evaluation-runs",
    ]
    for path in paths:
        rows = collect(client, path)
        assert len(rows) >= 25 and len({r["id"] for r in rows}) == len(rows)
        assert [(r.get("fetched_at", r.get("created_at")), r["id"]) for r in rows] == sorted(
            [(r.get("fetched_at", r.get("created_at")), r["id"]) for r in rows], reverse=True
        )
        assert "private" not in json.dumps(rows)
        assert "requirements" not in json.dumps(rows)
        cursor = client.get(path, params={"limit": 1}).json()["page"]["next_cursor"]
        assert client.get("/v2/jobs", params={"cursor": cursor}).status_code == 422
    detail = client.get(f"/v2/jobs/PAGE-0000/snapshots/{snapshot_id}")
    assert detail.status_code == 200 and detail.json()["clean_text"]
    assert client.get(f"/v2/jobs/foreign/snapshots/{snapshot_id}/runs").status_code == 404
    assert client.get("/v2/jobs/missing/snapshots").status_code == 404
    assert client.get("/v2/candidates/missing/revisions").json()["items"] == []
    for kind in ["acquisition-attempts", "extraction-attempts"]:
        assert client.get(f"/v2/jobs/PAGE-0000/{kind}").json()["items"] == []


def test_s13_attempt_pages_insertions_and_exact_run_reads(catalogue_client):
    client = catalogue_client
    seed_jobs(client, 1)
    saved = client.get("/jobs/PAGE-0000").json()
    snapshot_id, run_id = saved["snapshot"]["id"], saved["extraction"]["run_id"]
    with client.app.state.session_factory.begin() as session:
        for i in range(25):
            session.add(
                db.ExtractionAttempt(
                    id=f"{i + 1:032x}",
                    job_id="PAGE-0000",
                    snapshot_id=snapshot_id,
                    run_id=run_id if i % 2 else None,
                    created_at="2020-01-01",
                    configuration="fixture_normalized",
                    status="success" if i % 2 else "failed",
                    error_code=None if i % 2 else "provider_unavailable",
                    retryable=False,
                )
            )
            session.add(
                db.AcquisitionAttempt(
                    id=f"{i + 101:032x}",
                    job_id="PAGE-0000",
                    fetch_id=f"{i + 201:032x}",
                    sequence=1,
                    created_at="2020-01-01",
                    original_url="https://example.com/authored",
                    requested_url="https://example.com/authored",
                    final_url="https://example.com/authored",
                    status="failed",
                    http_status=403,
                    error_code="access_denied",
                    retryable=False,
                    payload={"private": "unselected payload"},
                )
            )
    for kind in ["acquisition-attempts", "extraction-attempts"]:
        rows = collect(client, f"/v2/jobs/PAGE-0000/{kind}", limit=3)
        assert len(rows) == 25 and len({r["id"] for r in rows}) == 25
        assert "private" not in json.dumps(rows)
    path = "/v2/jobs/PAGE-0000/extraction-attempts"
    first = client.get(path, params={"limit": 5}).json()
    with client.app.state.session_factory.begin() as session:
        session.add(
            db.ExtractionAttempt(
                job_id="PAGE-0000",
                snapshot_id=snapshot_id,
                run_id=run_id,
                created_at="2030-01-01",
                configuration="fixture_normalized",
                status="success",
                retryable=False,
            )
        )
    second = client.get(path, params={"limit": 5, "cursor": first["page"]["next_cursor"]}).json()
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    assert second["items"][0]["id"] == f"{20:032x}"
    assert client.get(f"/v2/extraction-runs/{run_id}").json() == saved["extraction"]
    assert client.get("/v2/extraction-runs/missing").status_code == 404
    assert client.get("/v2/jobs?unknown=true").status_code == 422
