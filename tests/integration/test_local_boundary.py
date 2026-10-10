"""Migrated API/PostgreSQL local-provider persistence; fake inference is plumbing only."""

import copy

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from jobintel import db
from jobintel.api import create_app
from tests.integration.test_extraction_boundary_v2 import DATA, migrate
from tests.integration.test_extraction_boundary_v2 import isolated_database as isolated_database
from tests.unit.test_local_provider import SOURCE, authored_payload, envelope, local_http


def test_local_unseen_run_and_failures_preserve_saved_history(isolated_database, monkeypatch):
    migrate(isolated_database, "head", monkeypatch)
    transport = local_http(envelope().body)
    with TestClient(
        create_app(isolated_database, DATA, provider_name="local", transport=transport)
    ) as client:
        assert client.get("/ui/config").json()["execution_mode"] == "local-inference"
        assert client.get("/ui/reset").status_code == 404
        assert (
            client.post(
                "/jobs/import",
                json={
                    "jobs": [{"job_id": "unseen", "company": "Authored local", "role": "Engineer"}]
                },
            ).status_code
            == 200
        )
        assert client.post("/jobs/unseen/snapshots", json={"text": SOURCE}).status_code == 201
        saved = client.post("/jobs/unseen/extract", json={}).json()
        assert saved["requirements"][0]["skills"] == ["PostgreSQL"]
        assert client.get("/analytics/skills").json()["N"] == 1
        assert (
            client.post("/jobs/unseen/extract", json={"configuration": "fixture_raw"}).status_code
            == 422
        )
        payload = copy.deepcopy(authored_payload())
        payload["requirements"][0]["evidence"]["start"] = 0
        client.app.state.provider.transport = local_http(envelope(payload).body)
        failed = client.post("/jobs/unseen/extract", json={})
        assert failed.status_code == 422 and failed.json()["detail"]["code"] == "invalid_evidence"
        client.app.state.provider.transport = local_http(envelope("{").body)
        assert client.post("/jobs/unseen/extract", json={}).status_code == 502
        assert client.get("/jobs/unseen").json()["extraction"]["run_id"] == saved["run_id"]
        with client.app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(db.ExtractionRun)) == 1
            assert session.scalar(select(func.count()).select_from(db.RequirementRow)) == 1
            assert session.scalar(select(func.count()).select_from(db.ExtractionAttempt)) == 4
