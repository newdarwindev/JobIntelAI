"""#25, V02-V11: real socket/TLS traffic through API and migrated SQLite/PostgreSQL."""

import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from jobintel import db
from jobintel.api import create_app
from jobintel.fetch_types import FetchPolicy
from scripts.acquisition_fixtures.local import local_acquirer, local_fixtures
from tests.integration.test_acquisition_boundary import SOURCE, register, row_counts
from tests.integration.test_extraction_boundary_v2 import DATA, migrate
from tests.integration.test_extraction_boundary_v2 import isolated_database as isolated_database


@pytest.fixture(scope="module")
def wire(tmp_path_factory):
    with local_fixtures(tmp_path_factory.mktemp("acquisition-trust"), SOURCE) as fixtures:
        yield fixtures


def http_requests(wire):
    return sum(
        count
        for name, count in wire["origin"].snapshot()["counts"].items()
        if name.startswith("/") or name == "refused"
    )


@pytest.fixture
def wire_client(isolated_database, monkeypatch, wire):
    migrate(isolated_database, "head", monkeypatch)
    policy = FetchPolicy(backoff=0.01, retry_after_cap=0.02)
    with TestClient(
        create_app(isolated_database, DATA, acquirer=local_acquirer(wire, policy=policy))
    ) as client:
        yield client


@pytest.mark.parametrize(
    "scheme,path",
    [
        ("http", "text"),
        ("https", "authored-job"),
        ("https", "gzip"),
        ("https", "deflate"),
        ("https", "chunked"),
        ("http", "chunked"),
    ],
)
def test_v02_v06_v10_real_api_snapshot_attempt_and_tls_identity(wire_client, wire, scheme, path):
    register(wire_client, url=f"{scheme}://example.com/{path}")
    before = http_requests(wire)
    response = wire_client.post("/jobs/fetched/fetch")
    assert response.status_code == 201
    saved = response.json()
    snapshot = wire_client.get("/jobs/fetched").json()["snapshot"]
    assert snapshot["id"] == saved["snapshot_id"] and snapshot["clean_text"] == SOURCE.strip()
    assert saved["attempts"][-1]["snapshot_id"] == saved["snapshot_id"]
    assert saved["attempts"][-1]["body_sha256"] and saved["attempts"][-1]["decompressed_bytes"] > 0
    assert http_requests(wire) - before == len(saved["attempts"])
    assert wire_client.post("/jobs/fetched/extract", json={}).status_code == 200
    assert wire_client.post("/jobs/fetched/fetch").json()["snapshot_id"] == snapshot["id"]
    if scheme == "https":
        events = wire["origin"].snapshot()["events"]
        assert any(
            event.get("kind") == "tls" and event["hostname"] == "example.com" for event in events
        )
        assert any(event.get("tls") and event["authority"] == "example.com" for event in events)
    if path == "authored-job":
        assert [event["status"] for event in saved["attempts"]] == ["redirect", "success"]
        assert saved["attempts"][-1]["final_url"] == "https://example.com/authored-final"
        with wire_client.app.state.session_factory() as session:
            assert "window.__fetched" in session.get(db.Snapshot, snapshot["id"]).raw_text
        assert "window.__fetched" not in snapshot["clean_text"]


@pytest.mark.parametrize(
    "path,code,status,count",
    [
        ("authored-denied", "access_denied", 403, 1),
        ("captcha", "captcha", 403, 1),
        ("authored-js", "js_only", 422, 1),
        ("oversized", "body_too_large", 413, 1),
        ("oversized-chunked", "body_too_large", 413, 1),
        ("gzip-bomb", "body_too_large", 413, 1),
        ("unsupported", "unsupported_type", 415, 1),
        ("rate-limit", "rate_limit", 503, 3),
        ("server-error", "server_error", 502, 3),
        ("loop", "redirect_loop", 422, 1),
        ("redirect/4", "redirect_limit", 422, 4),
        ("downgrade", "invalid_redirect", 422, 1),
    ],
)
def test_v04_v06_v07_real_failures_preserve_prior_run_and_recover(
    wire_client, wire, path, code, status, count
):
    register(wire_client, url=f"https://example.com/{path}")
    prior = wire_client.post("/jobs/fetched/snapshots", json={"text": SOURCE}).json()
    run = wire_client.post("/jobs/fetched/extract", json={}).json()["run_id"]
    before = http_requests(wire)
    response = wire_client.post("/jobs/fetched/fetch")
    assert response.status_code == status
    report = response.json()
    assert report["detail"]["code"] == code and report["detail"]["manual_fallback"]
    assert report["snapshot_id"] is None and len(report["attempts"]) == count
    assert http_requests(wire) - before == count
    assert wire_client.get("/jobs/fetched").json()["extraction"]["run_id"] == run
    assert row_counts(wire_client) == [1, 1, count]
    assert wire_client.get("/jobs/fetched/history").json()["acquisition_attempts"]
    if code == "rate_limit":
        assert report["attempts"][0]["retry_after_seconds"] == 0.02
        assert [event["wait_seconds"] for event in report["attempts"]] == [0.02, 0.02, 0]
    manual = wire_client.post(
        "/jobs/fetched/snapshots", json={"text": SOURCE + "\nAuthored recovery."}
    )
    assert manual.status_code == 201 and manual.json()["snapshot_id"] != prior["snapshot_id"]
    assert len(wire_client.get("/jobs/fetched/history").json()["snapshots"]) == 2


@pytest.mark.parametrize("path", ["retry-success", "server-success"])
def test_v05_bounded_real_retries_eventually_persist_success(wire_client, wire, path):
    register(wire_client, url=f"https://example.com/{path}")
    before = http_requests(wire)
    report = wire_client.post("/jobs/fetched/fetch").json()
    assert report["status"] == "success" and len(report["attempts"]) == 3
    assert [event["status"] for event in report["attempts"]] == ["failed", "failed", "success"]
    assert row_counts(wire_client) == [1, 0, 3] and http_requests(wire) - before == 3


@pytest.mark.parametrize(
    "url,count",
    [
        ("http://localhost/authored-final", 0),
        ("http://127.0.0.1/authored-final", 0),
        ("https://10.0.0.1/authored-final", 0),
        ("http://[::1]/authored-final", 0),
        ("https://private.example.test/authored-final", 0),
        ("https://mixed.example.test/authored-final", 0),
        ("http://example.com/private-redirect", 1),
        ("https://rebind.example.test/rebind", 1),
    ],
)
def test_v03_private_mixed_and_rebinding_fail_before_target_http(wire_client, wire, url, count):
    register(wire_client, url=url)
    origin_before = http_requests(wire)
    proxy_before = len(wire["proxy_diagnostics"].snapshot()["events"])
    report = wire_client.post("/jobs/fetched/fetch")
    assert report.status_code == 422 and report.json()["detail"]["code"] == "blocked_destination"
    assert http_requests(wire) - origin_before == count
    assert len(wire["proxy_diagnostics"].snapshot()["events"]) - proxy_before == count
    assert report.json()["snapshot_id"] is None


@pytest.mark.parametrize(
    "trusted,host,code",
    [
        (False, "example.com", "tls_error"),
        (True, "wrong.example.test", "tls_error"),
        (True, "denied.example.test", "proxy_denied"),
    ],
)
def test_v03_v07_untrusted_tls_wrong_hostname_and_proxy_denial_send_no_origin_http(
    wire_client, wire, trusted, host, code
):
    wire_client.app.state.acquirer = local_acquirer(wire, trusted=trusted)
    register(wire_client, url=f"https://{host}/authored-final")
    before = http_requests(wire)
    proxy_before = len(wire["proxy_diagnostics"].snapshot()["events"])
    response = wire_client.post("/jobs/fetched/fetch")
    assert response.status_code == 502 and response.json()["detail"]["code"] == code
    assert (
        http_requests(wire) == before
        and len(wire["proxy_diagnostics"].snapshot()["events"]) - proxy_before == 1
    )
    assert row_counts(wire_client) == [0, 0, 1]


@pytest.mark.parametrize(
    "policy,code",
    [
        (FetchPolicy(read_timeout=0.04, attempts=1), "read_timeout"),
        (FetchPolicy(read_timeout=1, total_timeout=0.08, attempts=1), "deadline"),
    ],
)
def test_v05_real_slow_chunk_stream_respects_read_and_total_budget(wire_client, wire, policy, code):
    wire_client.app.state.acquirer = local_acquirer(wire, policy=policy)
    register(wire_client, url="https://example.com/slow")
    started = time.monotonic()
    response = wire_client.post("/jobs/fetched/fetch")
    assert response.status_code == 504 and response.json()["detail"]["code"] == code
    assert time.monotonic() - started < 2 and row_counts(wire_client) == [0, 0, 1]


@pytest.mark.parametrize("stage", ["flush", "commit"])
def test_v11_real_wire_success_rolls_back_snapshot_and_attempt_on_database_failure(
    wire_client, wire, monkeypatch, stage
):
    register(wire_client, url="https://example.com/authored-final")
    before = http_requests(wire)
    original = Session.flush

    def fail_flush(session, *args, **kwargs):
        if any(isinstance(row, db.AcquisitionAttempt) for row in session.new):
            raise SQLAlchemyError("authored private diagnostic")
        return original(session, *args, **kwargs)

    def fail_commit(_session):
        raise SQLAlchemyError("authored private diagnostic")

    monkeypatch.setattr(Session, stage, fail_flush if stage == "flush" else fail_commit)
    response = wire_client.post("/jobs/fetched/fetch")
    assert response.status_code == 503 and "private diagnostic" not in response.text
    assert http_requests(wire) - before == 1 and row_counts(wire_client) == [0, 0, 0]
    assert "snapshot_id" not in response.json()


def test_diagnostics_do_not_retain_payloads_queries_or_credentials(wire):
    diagnostics = json.dumps(
        {"origin": wire["origin"].snapshot(), "proxy": wire["proxy_diagnostics"].snapshot()}
    )
    assert SOURCE not in diagnostics and "Python is required" not in diagnostics
    assert "Authorization" not in diagnostics and "Cookie" not in diagnostics


def test_v10_raw_change_creates_new_snapshot_and_retains_historical_extraction(wire_client):
    register(wire_client, url="https://example.com/mutable")
    first = wire_client.post("/jobs/fetched/fetch").json()
    run = wire_client.post("/jobs/fetched/extract", json={}).json()["run_id"]
    repeated = wire_client.post("/jobs/fetched/fetch").json()
    assert repeated["snapshot_id"] == first["snapshot_id"]
    changed = wire_client.post("/jobs/fetched/fetch").json()
    assert (
        changed["snapshot_id"] != first["snapshot_id"]
        and changed["content_hash"] == first["content_hash"]
    )
    assert wire_client.get("/jobs/fetched").json()["extraction"] is None
    history = wire_client.get("/jobs/fetched/history").json()
    original = next(row for row in history["snapshots"] if row["id"] == first["snapshot_id"])
    assert original["runs"][0]["run_id"] == run
