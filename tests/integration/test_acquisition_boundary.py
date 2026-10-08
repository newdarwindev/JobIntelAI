"""V02-V11: failed attempts commit, usable history survives, and writes are atomic."""

import json
import logging
import subprocess
import sys
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from jobintel import db
from jobintel.api import create_app
from jobintel.fetch_types import FetchError
from tests.acquisition_fakes import URL, Response, acquirer
from tests.integration.test_candidate_revisions import PROFILE
from tests.integration.test_extraction_boundary_v2 import DATA, ROOT, migrate
from tests.integration.test_extraction_boundary_v2 import isolated_database as isolated_database

SOURCE = (DATA / "sample_jobs/SYN-01.txt").read_text()
HTML = f"<nav>Authored navigation</nav><main>{SOURCE}</main>"


def register(client, job_id="fetched", url=URL):
    response = client.post(
        "/jobs/import",
        json={
            "jobs": [
                {
                    "job_id": job_id,
                    "company": f"Authored {job_id}",
                    "role": "Acquisition",
                    "official_url": url,
                }
            ]
        },
    )
    assert response.status_code == 200


def fetch(client, *responses):
    client.app.state.acquirer = acquirer(*responses)[0]
    return client.post("/jobs/fetched/fetch")


def html_response(html=HTML):
    return Response(body=html.encode(), headers={"content-type": "text/html; charset=utf-8"})


def row_counts(client):
    with client.app.state.session_factory() as session:
        return [
            session.scalar(select(func.count()).select_from(table))
            for table in [
                db.Snapshot,
                db.ExtractionRun,
                db.AcquisitionAttempt,
            ]
        ]


def test_v10_v11_fetch_history_reuse_raw_provenance_staleness_and_manual_recovery(
    isolated_database, monkeypatch
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        register(client)
        first = fetch(client, Response(302, headers={"location": "/final"}), html_response())
        assert first.status_code == 201 and first.headers["cache-control"] == "no-store"
        saved = first.json()
        assert [a["status"] for a in saved["attempts"]] == ["redirect", "success"]
        assert saved["attempts"][-1]["snapshot_id"] == saved["snapshot_id"]
        assert saved["attempts"][-1]["body_sha256"] == sha256(HTML.encode()).hexdigest()
        extracted = client.post("/jobs/fetched/extract", json={}).json()
        assert client.post("/jobs/fetched/match", json=PROFILE).status_code == 200
        repeated = fetch(
            client, Response(302, headers={"location": "/final"}), html_response()
        ).json()
        assert repeated["snapshot_id"] == saved["snapshot_id"]
        assert client.get("/jobs/fetched").json()["extraction"]["run_id"] == extracted["run_id"]
        changed = fetch(
            client,
            Response(302, headers={"location": "/final"}),
            html_response("<!-- Authored distinct raw -->" + HTML),
        ).json()
        assert changed["snapshot_id"] != saved["snapshot_id"]
        assert changed["content_hash"] == saved["content_hash"]
        assert client.get("/jobs/fetched").json()["extraction"] is None
        current_run = client.post("/jobs/fetched/extract", json={}).json()["run_id"]
        failed = fetch(client, Response(403, body=b"Authored access gate"))
        assert failed.status_code == 403 and failed.json()["detail"]["manual_fallback"]
        assert failed.json()["attempts"][0]["error_code"] == "access_denied"
        assert failed.json()["snapshot_id"] is None
        current = client.get("/jobs/fetched").json()
        assert (
            current["snapshot"]["id"] == changed["snapshot_id"]
            and current["extraction"]["run_id"] == current_run
        )
        history = client.get("/jobs/fetched/history").json()
        assert len(history["snapshots"]) == 2 and len(history["acquisition_attempts"]) == 7
        assert any(s["runs"][0]["run_id"] == extracted["run_id"] for s in history["snapshots"])
        assert client.post("/jobs/fetched/snapshots", json={"text": SOURCE}).status_code == 201
        with client.app.state.session_factory() as session:
            assert session.get(db.Snapshot, saved["snapshot_id"]).raw_text == HTML
            assert session.get(db.Snapshot, changed["snapshot_id"]).raw_text.startswith("<!--")


@pytest.mark.parametrize("status", [429, 503])
def test_v05_failed_retries_persist_without_empty_success(isolated_database, monkeypatch, status):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        register(client)
        response = fetch(
            client, *[Response(status, headers={"retry-after": "999"}) for _ in range(3)]
        )
        report = response.json()
        assert response.status_code in {502, 503}
        assert report["detail"]["retryable"] and len(report["attempts"]) == 3
        assert [a["wait_seconds"] for a in report["attempts"]] == [2, 2, 0]
        assert row_counts(client) == [0, 0, 3]
        assert client.get("/jobs/fetched").json()["snapshot"] is None
        assert client.post("/jobs/fetched/extract", json={}).status_code == 409


def test_v02_blocked_fetch_is_stored_and_service_mutation_is_unsupported(client):
    register(client, url="http://169.254.169.254/latest/meta-data/")
    fetcher, transport, _ = acquirer()
    client.app.state.acquirer = fetcher
    result = client.post("/jobs/fetched/fetch")
    assert result.status_code == 422 and result.json()["detail"]["code"] == "blocked_destination"
    assert transport.calls == [] and row_counts(client) == [0, 0, 1]
    attempt = result.json()["attempts"][0]
    before = client.get("/jobs/fetched/history").json()
    assert (
        client.patch("/jobs/fetched/history", json={"acquisition_attempts": []}).status_code == 405
    )
    assert (
        client.delete(f"/jobs/fetched/acquisition-attempts/{attempt['attempt_id']}").status_code
        == 404
    )
    assert (
        client.put("/jobs/fetched/snapshots", json={"text": "Attempted rewrite"}).status_code == 405
    )
    assert client.get("/jobs/fetched/history").json() == before


def test_v11_snapshot_and_attempt_write_failure_roll_back_together(
    isolated_database, monkeypatch, caplog
):
    migrate(isolated_database, "head", monkeypatch)
    caplog.set_level(logging.INFO, logger="jobintel.outcomes")
    with TestClient(create_app(isolated_database, DATA)) as client:
        register(client)
        before = row_counts(client)
        original_flush = Session.flush

        def fail_attempt(session, *args, **kwargs):
            if any(isinstance(row, db.AcquisitionAttempt) for row in session.new):
                raise SQLAlchemyError("authored private source body diagnostic")
            return original_flush(session, *args, **kwargs)

        monkeypatch.setattr(Session, "flush", fail_attempt)
        response = fetch(client, html_response())
        assert response.status_code == 503
        assert row_counts(client) == before
        assert not any("private source body" in record.getMessage() for record in caplog.records)
        assert caplog.records[-1].jobintel_outcome["outcome"] == "rolled_back"


def test_v11_fetch_commit_failure_does_not_publish_success(isolated_database, monkeypatch, caplog):
    migrate(isolated_database, "head", monkeypatch)
    caplog.set_level(logging.INFO, logger="jobintel.outcomes")
    with TestClient(create_app(isolated_database, DATA)) as client:
        register(client)
        caplog.clear()

        def fail_commit(_):
            raise SQLAlchemyError("authored private commit diagnostic")

        monkeypatch.setattr(Session, "commit", fail_commit)
        response = fetch(client, html_response())
        assert response.status_code == 503 and row_counts(client) == [0, 0, 0]
        outcomes = [r.jobintel_outcome for r in caplog.records if hasattr(r, "jobintel_outcome")]
        assert outcomes and all(row["outcome"] == "rolled_back" for row in outcomes)
        assert all("private commit diagnostic" not in r.getMessage() for r in caplog.records)


def test_v10_http_reuse_preserves_original_manual_snapshot_provenance(client):
    register(client)
    manual = client.post("/jobs/fetched/snapshots", json={"text": SOURCE, "source_url": URL}).json()
    before = client.get("/jobs/fetched").json()["snapshot"]
    report = fetch(client, Response(body=SOURCE.encode())).json()
    assert report["snapshot_id"] == manual["snapshot_id"]
    assert client.get("/jobs/fetched").json()["snapshot"] == before
    assert before["fetch_status"] == "manual"
    assert report["attempts"][0]["snapshot_id"] == manual["snapshot_id"]


@pytest.mark.parametrize("constraint", ["job", "snapshot", "sequence"])
def test_v11_attempt_foreign_keys_and_fetch_sequence_are_enforced(
    isolated_database, monkeypatch, constraint
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        register(client)
        saved = fetch(client, html_response()).json()
        row = {
            "job_id": "missing" if constraint == "job" else "fetched",
            "snapshot_id": "missing" if constraint == "snapshot" else saved["snapshot_id"],
            "fetch_id": saved["fetch_id"] if constraint == "sequence" else db.new_id(),
            "sequence": 0,
            "original_url": URL,
            "requested_url": URL,
            "final_url": URL,
            "status": "success",
            "retryable": False,
            "payload": {},
        }
        with client.app.state.session_factory() as session:
            session.add(db.AcquisitionAttempt(**row))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
        assert row_counts(client) == [1, 0, 1]


def test_v11_new_migration_preserves_existing_source_and_foreign_keys(
    isolated_database, monkeypatch
):
    migrate(isolated_database, "b15d20a3c704", monkeypatch)
    engine = create_engine(isolated_database)
    with engine.begin() as connection:
        connection.execute(
            db.Job.__table__.insert().values(
                job_id="before", identity="authored|before", payload={"job_id": "before"}
            )
        )
        connection.execute(
            db.Snapshot.__table__.insert().values(
                id="oldsource",
                job_id="before",
                raw_text=SOURCE,
                clean_text=SOURCE.strip(),
                content_hash=sha256(SOURCE.strip().encode()).hexdigest(),
                fetch_status="manual",
            )
        )
    migrate(isolated_database, "head", monkeypatch)
    with engine.connect() as connection:
        assert (
            connection.scalar(select(db.Snapshot.raw_text).where(db.Snapshot.id == "oldsource"))
            == SOURCE
        )
    assert "acquisition_attempts" in inspect(engine).get_table_names()
    subprocess.run(
        [sys.executable, "-m", "alembic", "check"], cwd=ROOT, capture_output=True, check=True
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "b15d20a3c704"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    assert "acquisition_attempts" not in inspect(engine).get_table_names()
    migrate(isolated_database, "head", monkeypatch)
    engine.dispose()


def test_v11_no_body_evidence_credentials_or_exception_text_in_fetch_logs(client, caplog):
    caplog.set_level(logging.INFO, logger="jobintel.outcomes")
    register(client)
    sentinel = "Authored source logging sentinel."
    response = fetch(client, Response(body=sentinel.encode()))
    assert response.status_code == 201
    assert all(
        sentinel not in record.getMessage() and URL not in record.getMessage()
        for record in caplog.records
    )
    fetched_id = response.json()["fetch_id"]
    failure = fetch(client, FetchError("tls_error"))
    assert failure.status_code == 502 and failure.json()["fetch_id"] != fetched_id
    assert all("body" not in json.dumps(row) for row in failure.json()["attempts"])


def test_v06_unusable_response_never_replaces_usable_source(client):
    register(client)
    old = client.post("/jobs/fetched/snapshots", json={"text": SOURCE}).json()
    run = client.post("/jobs/fetched/extract", json={}).json()["run_id"]
    response = fetch(
        client, Response(body=b"%PDF authored", headers={"content-type": "application/pdf"})
    )
    assert response.status_code == 415
    current = client.get("/jobs/fetched").json()
    assert (
        current["snapshot"]["id"] == old["snapshot_id"] and current["extraction"]["run_id"] == run
    )
    assert row_counts(client) == [1, 1, 1]


def test_v02_missing_job_or_official_url_never_requests_transport(client):
    register(client, url=None)
    fetcher, transport, _ = acquirer()
    client.app.state.acquirer = fetcher
    assert client.post("/jobs/missing/fetch").status_code == 404
    assert client.post("/jobs/fetched/fetch").status_code == 422
    assert transport.calls == [] and row_counts(client) == [0, 0, 0]
