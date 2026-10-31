import json
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from jobintel import app
from jobintel.import_legacy import import_database
from jobintel.store import Store

JOB = "We require Python and PostgreSQL production operations."
CANDIDATE = "I built Python services. I have no evidence of PostgreSQL work."


def test_compare_save_reopen_restart_and_idempotency(tmp_path, monkeypatch):
    db = tmp_path / "app.sqlite"
    monkeypatch.setattr(app, "store", Store(str(db)))
    calls = []

    def fake(job, candidate):
        calls.append((job, candidate))
        return [
            {
                "requirement": "Python",
                "job_quote": "Python",
                "candidate_quote": "Python services",
                "status": "SUPPORTED",
                "reason": "Explicit",
            },
            {
                "requirement": "PostgreSQL production",
                "job_quote": "PostgreSQL production",
                "candidate_quote": "",
                "status": "UNKNOWN",
                "reason": "No positive evidence",
            },
        ]

    monkeypatch.setattr(app.provider, "compare", fake)
    client = TestClient(app.app)
    body = {"job": JOB, "candidate": CANDIDATE}
    key = str(uuid4())
    first = client.post("/api/compare", json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 200
    assert first.json()["result"][1]["status"] == "UNKNOWN"
    assert first.json()["result"][0]["candidate"]["quote"] == "Python services"
    second = client.post("/api/compare", json=body, headers={"Idempotency-Key": key})
    assert second.json()["id"] == first.json()["id"]
    assert len(calls) == 1
    monkeypatch.setattr(app, "store", Store(str(db)))
    record_id = first.json()["id"]
    assert client.get(f"/api/records/{record_id}").json() == first.json()
    exported = client.get(f"/api/records/{record_id}/export")
    assert exported.status_code == 200
    assert json.loads(exported.content)["job"] == JOB
    assert (
        client.post(
            "/api/compare", json={**body, "job": JOB + "x"}, headers={"Idempotency-Key": key}
        ).status_code
        == 409
    )


def test_invalid_evidence_and_uncertain_reservation(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "app.sqlite"))
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(
        app.provider,
        "compare",
        lambda *_: [
            {
                "requirement": "Invented",
                "job_quote": "not present",
                "candidate_quote": "",
                "status": "UNKNOWN",
                "reason": "bad",
            }
        ],
    )
    client = TestClient(app.app)
    key = str(uuid4())
    headers = {"Idempotency-Key": key}
    assert (
        client.post(
            "/api/compare", json={"job": JOB, "candidate": CANDIDATE}, headers=headers
        ).status_code
        == 502
    )
    assert client.get("/api/records").json() == []
    assert (
        client.post(
            "/api/compare", json={"job": JOB, "candidate": CANDIDATE}, headers=headers
        ).status_code
        == 409
    )
    store.reserve("pending", "hash")
    import pytest

    with pytest.raises(ValueError, match="uncertain"):
        Store(str(tmp_path / "app.sqlite")).reserve("pending", "hash")


def test_legacy_copy_preserves_source(tmp_path):
    source = tmp_path / "old.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE posting_snapshots(id TEXT, clean_text TEXT, source_url TEXT)")
        db.execute("CREATE TABLE candidate_evidence(id TEXT, payload TEXT)")
        db.execute("CREATE TABLE extraction_runs(id TEXT, payload TEXT)")
        db.execute("CREATE TABLE match_runs(snapshot_id TEXT, profile_revision_id TEXT)")
        db.execute("INSERT INTO posting_snapshots VALUES ('s1', ?, NULL)", (JOB,))
        db.execute(
            "INSERT INTO candidate_evidence VALUES ('c1', ?)", (json.dumps({"text": CANDIDATE}),)
        )
        db.execute("INSERT INTO extraction_runs VALUES ('r1', ?)", ('{"old":true}',))
        db.execute("INSERT INTO match_runs VALUES ('s1', 'c1')")
    before = source.read_bytes()
    target = tmp_path / "new.sqlite"
    assert import_database(str(source), str(target)) == 1
    assert import_database(str(source), str(target)) == 0
    assert source.read_bytes() == before
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT count(*) FROM legacy_archive").fetchone()[0] == 4
        assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 1


def test_unicode_offsets_and_html_inert():
    job = "Build 🐍 Python systems for users."
    candidate = "Built 🐍 Python APIs for teams."
    result = app.grounded(
        [
            {
                "requirement": "Python",
                "job_quote": "🐍 Python",
                "candidate_quote": "🐍 Python",
                "status": "SUPPORTED",
                "reason": "quote",
            }
        ],
        job,
        candidate,
    )[0]
    assert job[result["job"]["start"] : result["job"]["end"]] == "🐍 Python"
    assert candidate[result["candidate"]["start"] : result["candidate"]["end"]] == "🐍 Python"
    html = (app.WEB / "index.html").read_text()
    js = (app.WEB / "app.js").read_text()
    assert "innerHTML" not in js
    assert "viewport" in html


def test_http_validation_and_missing_records(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", Store(str(tmp_path / "app.sqlite")))
    client = TestClient(app.app)
    body = {"job": JOB, "candidate": CANDIDATE}
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.post("/api/compare", json=body).status_code == 422
    assert (
        client.post("/api/compare", json=body, headers={"Idempotency-Key": "bad"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/compare",
            json={"job": "short", "candidate": CANDIDATE},
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 422
    )
    assert client.get("/api/records/missing").status_code == 404
    assert client.get("/api/records/missing/export").status_code == 404


def test_provider_adapter_no_key_and_malformed_response(monkeypatch):
    import pytest

    from jobintel import provider

    monkeypatch.delenv("JOBINTEL_OPENAI_API_KEY", raising=False)
    with pytest.raises(provider.ProviderError, match="Set JOBINTEL"):
        provider.compare(JOB, CANDIDATE)

    monkeypatch.setenv("JOBINTEL_OPENAI_API_KEY", "synthetic-test-key")
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "not JSON"}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, headers, json):
            calls.append((url, headers, json))
            return FakeResponse()

    monkeypatch.setattr(provider.httpx, "Client", FakeClient)
    with pytest.raises(provider.ProviderError, match="response failed"):
        provider.compare(JOB, CANDIDATE)
    assert calls[1][0] == "https://api.openai.com/v1/chat/completions"
    assert calls[1][2]["messages"][1]["content"].find(JOB) >= 0


def test_uncertain_http_submission_never_calls_provider(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "app.sqlite"))
    monkeypatch.setattr(app, "store", store)
    body = {"job": JOB, "candidate": CANDIDATE}
    key = str(uuid4())
    from jobintel.store import digest

    store.reserve(key, digest(app.Input(**body).model_dump_json()))
    called = []
    monkeypatch.setattr(app.provider, "compare", lambda *_: called.append(True))
    result = TestClient(app.app).post("/api/compare", json=body, headers={"Idempotency-Key": key})
    assert result.status_code == 409
    assert called == []


def test_legacy_unrelated_revisions_are_not_paired(tmp_path):
    source = tmp_path / "old.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE posting_snapshots(id TEXT, clean_text TEXT, source_url TEXT)")
        db.execute("CREATE TABLE candidate_evidence(id TEXT, payload TEXT)")
        db.execute("INSERT INTO posting_snapshots VALUES ('s1', ?, NULL)", (JOB,))
        db.execute(
            "INSERT INTO candidate_evidence VALUES ('c1', ?)", (json.dumps({"text": CANDIDATE}),)
        )
    before = source.read_bytes()
    target = tmp_path / "new.sqlite"
    assert import_database(str(source), str(target)) == 0
    assert source.read_bytes() == before
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM legacy_archive").fetchone()[0] == 2


def test_corrupt_database_has_explicit_error(tmp_path):
    import pytest

    path = tmp_path / "broken.sqlite"
    path.write_bytes(b"not a sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        Store(str(path))


def test_provider_http_failure_becomes_explicit_error(monkeypatch):
    import httpx
    import pytest

    from jobintel import provider

    monkeypatch.setenv("JOBINTEL_OPENAI_API_KEY", "synthetic-test-key")

    class FailingClient:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("synthetic connection failure")

    monkeypatch.setattr(provider.httpx, "Client", FailingClient)
    with pytest.raises(provider.ProviderError, match="request or response failed"):
        provider.compare(JOB, CANDIDATE)


def test_missing_committed_result_does_not_repeat_provider(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "app.sqlite"))
    monkeypatch.setattr(app, "store", store)
    body = {"job": JOB, "candidate": CANDIDATE}
    from jobintel.store import digest

    key = str(uuid4())
    with sqlite3.connect(tmp_path / "app.sqlite") as db:
        db.execute(
            "INSERT INTO operations VALUES (?,?,?,?)",
            (key, digest(app.Input(**body).model_dump_json()), "gone", "committed"),
        )
    called = []
    monkeypatch.setattr(app.provider, "compare", lambda *_: called.append(True))
    result = TestClient(app.app).post("/api/compare", json=body, headers={"Idempotency-Key": key})
    assert result.status_code == 409
    assert called == []
