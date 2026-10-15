"""Actual migrated operation/record boundaries, including duplicate delivery and SQL failure."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from jobintel import db
from jobintel.api import create_app
from jobintel.mutation_operations import reserve
from tests.integration.test_candidate_revisions import PROFILE, prepare, selection
from tests.integration.test_extraction_boundary_v2 import DATA, migrate
from tests.integration.test_extraction_boundary_v2 import (
    isolated_database as isolated_database,
)
from tests.integration.test_persistence_privacy import fail_after_insert

MODELS = {
    "registry": db.Job,
    "snapshot": db.Snapshot,
    "candidate": db.CandidateEvidenceRow,
    "extract": db.ExtractionRun,
    "match": db.MatchRun,
    "evaluate": db.EvaluationRun,
}


def counts(client):
    with client.app.state.session_factory() as session:
        return {
            kind: session.scalar(select(func.count()).select_from(model))
            for kind, model in MODELS.items()
        }


def request_for(client, kind):
    run = prepare(client)
    revision = client.post("/candidates/import", json=PROFILE).json()
    prior_match = client.post("/jobs/synthetic/match", json=selection(revision, run)).json()
    prior_evaluation = client.post("/evaluate", json={"configurations": ["fixture_raw"]}).json()
    requests = {
        "registry": (
            "/jobs/import",
            {"jobs": [{"job_id": "new", "company": "Authored new", "role": "Engineer"}]},
        ),
        "snapshot": (
            "/jobs/synthetic/snapshots",
            {
                "text": "<main>" + (DATA / "sample_jobs/SYN-01.txt").read_text() + "</main>",
                "format": "html",
            },
        ),
        "candidate": ("/candidates/import", {**PROFILE, "complete": True}),
        "extract": ("/jobs/synthetic/extract", {}),
        "match": ("/jobs/synthetic/match", selection(revision, run)),
        "evaluate": ("/evaluate", {"configurations": ["fixture_normalized"]}),
    }
    return requests[kind], (run, revision, prior_match, prior_evaluation)


@pytest.mark.parametrize("kind", MODELS)
def test_replay_and_lookup_preserve_one_execution_and_all_prior_records(
    isolated_database, monkeypatch, kind
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        (path, body), prior = request_for(client, kind)
        before = counts(client)
        key = uuid4().hex
        headers = {"Idempotency-Key": key}
        # Receiving or losing this HTTP response cannot affect the committed records.
        first = client.post(path, json=body, headers=headers)
        assert first.status_code in {200, 201}
        after = counts(client)
        assert after[kind] == before[kind] + 1
        saved = client.get(f"/operations/{key}").json()
        assert saved["state"] == "committed"
        assert saved["execution_count"] == 1
        assert saved["result"] == first.json()
        assert saved["http_status"] == first.status_code
        # Canonical JSON, not key order or pretty-printing, binds the operation identity.
        duplicate = client.post(path, content=json.dumps(body, sort_keys=True), headers=headers)
        assert duplicate.json() == first.json()
        assert duplicate.status_code == first.status_code
        assert counts(client) == after
        assert client.get(f"/operations/{key}").json() == saved
        run, revision, matched, evaluated = prior
        history = client.get("/jobs/synthetic/history").json()
        assert any(r["run_id"] == run["run_id"] for s in history["snapshots"] for r in s["runs"])
        assert (
            client.get(
                f"/candidates/{revision['profile_id']}/revisions/{revision['profile_revision_id']}"
            ).json()
            == revision
        )
        assert client.get(f"/match-runs/{matched['match_run_id']}").json() == matched
        assert client.get(f"/evaluation-runs/{evaluated['evaluation_run_id']}").json() == evaluated


def test_identity_conflict_cannot_rebind_result_or_execute_a_different_request(client):
    prepare(client)
    key = uuid4().hex
    headers = {"Idempotency-Key": key}
    original = client.post("/jobs/synthetic/extract", json={}, headers=headers).json()
    before = counts(client)
    assert (
        client.post(
            "/jobs/synthetic/extract", json={"configuration": "fixture_raw"}, headers=headers
        ).status_code
        == 409
    )
    assert client.post("/candidates/import", json=PROFILE, headers=headers).status_code == 409
    assert counts(client) == before
    assert client.get(f"/operations/{key}").json()["result"] == original


@pytest.mark.parametrize("payload", [{"profile_id": "bad", "evidence": [{"skill": "Python"}]}, []])
def test_validation_rejection_is_durable_and_does_not_start_handler(client, payload):
    key = uuid4().hex
    before = counts(client)
    first = client.post("/candidates/import", json=payload, headers={"Idempotency-Key": key})
    assert first.status_code == 422
    saved = client.get(f"/operations/{key}").json()
    assert saved["state"] == "rejected"
    assert saved["execution_count"] == 0
    assert saved["result"] == first.json()
    assert (
        client.post("/candidates/import", json=payload, headers={"Idempotency-Key": key}).json()
        == first.json()
    )
    assert counts(client) == before


def test_before_delivery_retry_and_cancellation_keep_late_packets_safe(client):
    key = uuid4().hex
    path, body = "/candidates/import", PROFILE
    assert client.get(f"/operations/{key}").json()["state"] == "not_received"
    assert client.post(path, json=body, headers={"Idempotency-Key": key}).status_code == 201
    assert client.get(f"/operations/{key}").json()["state"] == "committed"
    cancelled = uuid4().hex
    assert client.post(f"/operations/{cancelled}/cancel-unsent").json()["state"] == "rejected"
    before = counts(client)
    # A late original request cannot execute after the unsent operation is cancelled.
    assert client.post(path, json=body, headers={"Idempotency-Key": cancelled}).status_code == 409
    assert client.get(f"/operations/{cancelled}").json()["execution_count"] == 0
    assert counts(client) == before


def test_reserved_or_interrupted_work_is_uncertain_and_never_restarted(client):
    key = uuid4().hex
    from jobintel.mutation_operations import request_hash

    path = "/jobs/synthetic/extract"
    digest = request_hash("POST", path, b"{}")
    reserve(client.app.state.session_factory, key, "POST", path, digest)
    before = counts(client)
    result = client.post(path, json={}, headers={"Idempotency-Key": key})
    assert result.status_code == 409
    assert result.headers["X-Operation-State"] == "uncertain"
    assert client.get(f"/operations/{key}").json()["execution_count"] is None
    assert client.post(f"/operations/{key}/cancel-unsent").json()["state"] == "uncertain"
    assert counts(client) == before


@pytest.mark.parametrize("table", ["requirements", "mutation_operations"])
def test_sql_failure_leaves_no_false_commit_or_repeat(isolated_database, monkeypatch, table):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        prepare(client)
        engine = client.app.state.session_factory.kw["bind"]
        before = counts(client)
        key = uuid4().hex
        with fail_after_insert(engine, table):
            failed = client.post(
                "/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key}
            )
        assert failed.status_code == 503
        assert counts(client) == before
        saved = client.get(f"/operations/{key}").json()
        if table == "requirements":
            assert saved["state"] == "uncertain"
            assert (
                client.post(
                    "/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key}
                ).status_code
                == 409
            )
        else:
            assert saved["state"] == "not_received"
        assert counts(client) == before


def test_domain_and_response_commit_atomically_when_ledger_update_fails(client, monkeypatch):
    import jobintel.api as api

    prepare(client)
    before = counts(client)
    original = api.finish

    def fail(*args):
        original(*args)
        raise RuntimeError("authored failure after response write before commit")

    monkeypatch.setattr(api, "finish", fail)
    key = uuid4().hex
    response = client.post("/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key})
    assert response.status_code == 409
    assert client.get(f"/operations/{key}").json()["state"] == "uncertain"
    assert counts(client) == before


def test_concurrent_duplicate_during_provider_call_cannot_execute_twice(
    isolated_database, monkeypatch, provider
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        prepare(client)
        entered, release = Event(), Event()
        calls = []

        class BlockingProvider:
            name = "fixture"

            def extract(self, text, configuration):
                calls.append(True)
                entered.set()
                assert release.wait(10)
                return provider.extract(text, configuration)

        client.app.state.provider = BlockingProvider()
        key = uuid4().hex
        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(
                client.post, "/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key}
            )
            try:
                assert entered.wait(10)
                duplicate = client.post(
                    "/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key}
                )
                assert duplicate.status_code == 409
                assert client.get(f"/operations/{key}").json()["state"] == "uncertain"
            finally:
                release.set()
            assert future.result().status_code == 200
        assert len(calls) == 1
        assert client.get(f"/operations/{key}").json()["execution_count"] == 1


def test_status_survives_api_recreation_and_legacy_requests_remain_new_work(client):
    prepare(client)
    key = uuid4().hex
    saved = client.post("/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key}).json()
    factory = client.app.state.session_factory
    with TestClient(create_app(str(factory.kw["bind"].url), DATA)) as recreated:
        assert recreated.get(f"/operations/{key}").json()["result"] == saved
        assert (
            recreated.post(
                "/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key}
            ).json()
            == saved
        )
        new = recreated.post("/jobs/synthetic/extract", json={}).json()
        assert new["run_id"] != saved["run_id"]


def test_failed_provider_outcome_is_replayed_without_another_call(client):
    from jobintel.openai_transport import ProviderError

    prepare(client)
    calls = []

    class RefusingProvider:
        def extract(self, *_):
            calls.append(True)
            raise ProviderError("refusal", 422, False)

    client.app.state.provider = RefusingProvider()
    key = uuid4().hex
    first = client.post("/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key})
    assert first.status_code == 422
    assert client.get(f"/operations/{key}").json()["state"] == "rejected"
    assert (
        client.post("/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key}).json()
        == first.json()
    )
    assert len(calls) == 1


def test_invalid_operation_identity_is_rejected_without_work(client):
    before = counts(client)
    assert (
        client.post(
            "/candidates/import", json=PROFILE, headers={"Idempotency-Key": "not-an-id"}
        ).status_code
        == 422
    )
    assert client.get("/operations/not-an-id").status_code == 422
    assert counts(client) == before


def test_known_server_rejection_rolls_back_and_does_not_remain_uncertain(client, monkeypatch):
    from jobintel.openai_transport import ProviderError
    from jobintel.service import Service

    (path, body), _ = request_for(client, "match")
    before = counts(client)
    calls = []

    def fail_after_match_row(*_):
        calls.append(True)
        raise ProviderError("authored known failure", 502, False)

    monkeypatch.setattr(Service, "match_rows", fail_after_match_row)
    key = uuid4().hex
    first = client.post(path, json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 502
    saved = client.get(f"/operations/{key}").json()
    assert saved["state"] == "rejected"
    assert saved["execution_count"] == 1
    assert counts(client) == before
    assert client.post(path, json=body, headers={"Idempotency-Key": key}).json() == first.json()
    assert len(calls) == 1


def test_lost_commit_acknowledgement_recovers_the_actual_atomic_result(
    isolated_database, monkeypatch
):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    import jobintel.api as api

    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        prepare(client)
        before = counts(client)
        original_finish, original_commit = api.finish, Session.commit

        def finish_then_mark(session, *args):
            original_finish(session, *args)
            session.info["authored_lost_acknowledgement"] = True

        def commit_then_disconnect(session):
            original_commit(session)
            if session.info.pop("authored_lost_acknowledgement", False):
                raise OperationalError("authored lost acknowledgement", {}, None)

        monkeypatch.setattr(api, "finish", finish_then_mark)
        monkeypatch.setattr(Session, "commit", commit_then_disconnect)
        key = uuid4().hex
        first = client.post("/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key})
        assert first.status_code == 200
        saved = client.get(f"/operations/{key}").json()
        assert saved["state"] == "committed"
        assert saved["result"] == first.json()
        assert counts(client)["extract"] == before["extract"] + 1
        assert (
            client.post("/jobs/synthetic/extract", json={}, headers={"Idempotency-Key": key}).json()
            == first.json()
        )
        assert counts(client)["extract"] == before["extract"] + 1
