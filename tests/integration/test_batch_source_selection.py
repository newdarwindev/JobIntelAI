"""Captured batch inputs reject stale sources before provider calls or source writes."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from jobintel.api import create_app
from tests.integration.test_candidate_revisions import prepare
from tests.integration.test_extraction_boundary_v2 import DATA, migrate
from tests.integration.test_extraction_boundary_v2 import (
    isolated_database as isolated_database,
)


@pytest.mark.parametrize("stage", ["snapshot", "extract"])
def test_stale_batch_source_rejects_without_replacing_source_or_calling_provider(
    isolated_database, monkeypatch, stage
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        previous = prepare(client)
        source_id = previous["snapshot_id"]
        current = client.post(
            "/jobs/synthetic/snapshots", json={"text": "Authored newer source"}
        ).json()
        calls = []

        class NeverCalled:
            def extract(self, *_):
                calls.append(True)
                raise AssertionError("stale extraction must not reach the provider")

        client.app.state.provider = NeverCalled()
        key = uuid4().hex
        body = {"expected_snapshot_id": source_id}
        if stage == "snapshot":
            body["text"] = "Authored stale batch replacement"
        path = f"/jobs/synthetic/{'snapshots' if stage == 'snapshot' else 'extract'}"
        response = client.post(path, json=body, headers={"Idempotency-Key": key})
        assert response.status_code == 409
        operation = client.get(f"/operations/{key}").json()
        assert operation["state"] == "rejected"
        assert operation["result"] == response.json()
        assert calls == []
        job = client.get("/jobs/synthetic").json()
        assert job["snapshot"]["id"] == current["snapshot_id"]
        assert job["extraction"] is None
        history = client.get("/jobs/synthetic/history").json()
        assert len(history["snapshots"]) == 2
        assert any(
            run["run_id"] == previous["run_id"]
            for snapshot in history["snapshots"]
            for run in snapshot["runs"]
        )
        assert (
            client.post(path, json=body, headers={"Idempotency-Key": key}).json() == response.json()
        )
        assert calls == []


def test_explicit_empty_source_guard_and_current_selection_remain_compatible(client):
    client.post("/jobs/import", json={"jobs": [{"job_id": "new", "company": "New", "role": "E"}]})
    saved = client.post(
        "/jobs/new/snapshots", json={"text": "Authored initial", "expected_snapshot_id": None}
    ).json()
    rejected = client.post(
        "/jobs/new/snapshots", json={"text": "Must not replace", "expected_snapshot_id": None}
    )
    assert rejected.status_code == 409
    accepted = client.post(
        "/jobs/new/snapshots",
        json={
            "text": "Authored selected replacement",
            "expected_snapshot_id": saved["snapshot_id"],
        },
    )
    assert accepted.status_code == 201
    assert len(client.get("/jobs/new/history").json()["snapshots"]) == 2
