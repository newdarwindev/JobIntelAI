"""V27-V30: mixed persisted corpus, revisions, failure accounting and API/CLI parity."""

import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from jobintel import db
from jobintel.api import create_app
from jobintel.cli import main
from jobintel.openai_transport import ProviderError
from jobintel.schemas import Extraction, JobInput, SnapshotInput
from jobintel.service import Service
from tests.acquisition_fakes import Response, acquirer
from tests.integration.test_candidate_revisions import PROFILE, selection
from tests.integration.test_extraction_boundary_v2 import DATA, ROOT, migrate
from tests.integration.test_extraction_boundary_v2 import isolated_database as isolated_database


def source(client, job_id, fixture, extract=True):
    text = (DATA / f"sample_jobs/{fixture}.txt").read_text()
    assert client.post(f"/jobs/{job_id}/snapshots", json={"text": text}).status_code == 201
    if extract:
        response = client.post(f"/jobs/{job_id}/extract", json={})
        assert response.status_code == 200
        return response.json()


def revision_options(revision):
    return {k: revision[k] for k in ("profile_id", "profile_revision_id")}


def analytics(client, revision=None, **query):
    response = client.get(
        "/analytics/skills", params={**(revision_options(revision) if revision else {}), **query}
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def seed(client):
    jobs = [
        {"job_id": key, "company": f"Authored {key}", "role": "Analytics", "applied": applied}
        for key, applied in [
            ("pending", None),
            ("denied", True),
            ("failed", False),
            ("waiting", True),
            ("stale", False),
            ("empty", None),
            ("duplicate", True),
            ("any", True),
            ("all", False),
        ]
    ]
    jobs[1]["official_url"] = "https://example.com/authored"
    assert client.post("/jobs/import", json={"jobs": jobs}).status_code == 200
    client.app.state.acquirer = acquirer(
        Response(302, headers={"location": "/last"}), Response(403)
    )[0]
    assert client.post("/jobs/denied/fetch").status_code == 403
    assert (
        client.post(
            "/jobs/failed/snapshots", json={"text": "Authored unsupported replay source."}
        ).status_code
        == 201
    )
    assert client.post("/jobs/failed/extract", json={}).status_code == 501
    source(client, "waiting", "SYN-01", False)
    source(client, "stale", "SYN-03")
    client.post("/jobs/stale/snapshots", json={"text": "Authored changed source."})
    runs = {
        key: source(client, key, fixture)
        for key, fixture in [("empty", "SYN-18"), ("any", "SYN-02"), ("all", "SYN-03")]
    }
    provider = client.app.state.provider

    class DuplicateProvider:
        def extract(self, text, configuration):
            result = provider.extract(text, configuration)
            return result.model_copy(
                update={"requirements": [result.requirements[0], *result.requirements]}
            )

    client.app.state.provider = DuplicateProvider()
    runs["duplicate"] = source(client, "duplicate", "SYN-01")
    client.app.state.provider = provider
    profile = {
        **PROFILE,
        "evidence": [
            *PROFILE["evidence"],
            {**PROFILE["evidence"][0], "skill": "SQL", "current_capability": "basic"},
        ],
    }
    first = client.post("/candidates/import", json=profile).json()
    second = client.post("/candidates/import", json={**profile, "complete": True}).json()
    for key in ["empty", "all", "duplicate"]:
        assert (
            client.post(f"/jobs/{key}/match", json=selection(first, runs[key])).status_code == 200
        )
    client.post("/jobs/duplicate/match", json=selection(second, runs["duplicate"]))
    client.post("/jobs/duplicate/match", json=selection(first, runs["duplicate"]))
    return first, second, runs


def test_v27_v29_mixed_corpus_denominators_groups_and_revision_isolation(
    isolated_database, monkeypatch
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        first, second, runs = seed(client)
        report = analytics(client, first)
        assert report["N"] == 4 and report["gaps"]["N"] == 3
        coverage = report["coverage"]
        assert coverage["buckets"] == {
            "successful": 3,
            "successfully_empty": 1,
            "pending_source": 1,
            "pending_extraction": 1,
            "acquisition_failed": 1,
            "extraction_failed": 1,
            "stale": 1,
        }
        assert coverage["registered_selected"] == coverage["registered_total"] == 9
        assert sum(coverage["buckets"].values()) == 9 and coverage["excluded"] == 0
        assert coverage["pending"] == coverage["failed"] == 2 and coverage["unmatched"] == 1
        assert coverage["latest_acquisition_failed"] == coverage["latest_extraction_failed"] == 1
        python = next(s for s in report["skills"] if s["skill"] == "Python")
        assert python["n"] == python["must_n"] == 2 and python["N"] == 4
        assert not any(s["skill"] in {"AWS", "Azure"} for s in report["skills"])
        assert len(report["alternatives"]) == 1
        assert all(c["n"] <= c["N"] == 4 for c in report["clusters"]["clusters"])
        assert next(g for g in report["gaps"]["groups"] if g["operator"] == "ALL")["PARTIAL"] == 1
        assert (
            next(g for g in report["gaps"]["groups"] if g["requirement"] == "PostgreSQL")["UNKNOWN"]
            == 1
        )
        other = analytics(client, second)
        assert other["gaps"]["N"] == 1 and other["coverage"]["unmatched"] == 3
        assert (
            next(g for g in other["gaps"]["groups"] if g["requirement"] == "PostgreSQL")["MISSING"]
            == 1
        )
        assert analytics(client, first) == report
        client.post("/jobs/any/match", json=selection(first, runs["any"]))
        matched = analytics(client, first)
        group = next(g for g in matched["gaps"]["groups"] if g["operator"] == "ANY")
        assert group["skills"] == ["AWS", "Azure"] and group["UNKNOWN"] == 1 and group["N"] == 4
        assert matched["coverage"]["unmatched"] == 0


def test_v28_v30_slices_and_exact_api_cli_results(isolated_database, monkeypatch, capsys):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        first, _, _ = seed(client)
        for applied, N, selected, excluded in [(None, 4, 9, 0), (True, 2, 4, 5), (False, 1, 3, 6)]:
            options = {} if applied is None else {"applied": str(applied).lower()}
            report = analytics(client, first, **options)
            assert report["N"] == N and report["coverage"]["registered_selected"] == selected
            assert report["coverage"]["excluded"] == excluded
            argv = [
                "analytics",
                "--profile-id",
                first["profile_id"],
                "--revision-id",
                first["profile_revision_id"],
            ]
            if applied is not None:
                argv += ["--applied", str(applied).lower()]
            capsys.readouterr()
            monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
            main(argv)
            assert json.loads(capsys.readouterr().out) == report
        unknown = analytics(client, first, remote="true")
        assert unknown["N"] == 0 and unknown["coverage"]["excluded"] == 9
        assert (
            unknown["coverage"]["success_fraction"]
            is unknown["coverage"]["matched_fraction"]
            is None
        )


def test_v28_failure_retry_preserves_current_runs_and_reextraction_invalidates_matches(client):
    first, _, runs = seed(client)
    original = client.app.state.provider

    class Failure:
        def extract(self, *_):
            raise ProviderError("timeout", 504, True)

    client.app.state.provider = Failure()
    assert client.post("/jobs/duplicate/extract", json={}).status_code == 504
    report = analytics(client, first)
    assert report["N"] == 4 and report["gaps"]["N"] == 3
    assert (
        report["coverage"]["latest_extraction_failed"] == 2
        and report["coverage"]["buckets"]["extraction_failed"] == 1
    )
    history = client.get("/jobs/duplicate/history").json()
    assert history["extraction_attempts"][0]["status"] == "failed"
    assert history["extraction_attempts"][0]["error_code"] == "timeout"
    client.app.state.provider = original
    assert client.post("/jobs/duplicate/extract", json={}).status_code == 200
    current = analytics(client, first)
    assert current["N"] == 4 and current["gaps"]["N"] == 2 and current["coverage"]["unmatched"] == 2
    assert current["coverage"]["latest_extraction_failed"] == 1
    assert (
        client.post("/jobs/duplicate/match", json=selection(first, runs["duplicate"])).status_code
        == 409
    )
    assert (
        client.patch("/jobs/duplicate/history", json={"extraction_attempts": []}).status_code == 405
    )


def test_v28_acquisition_recovery_orders_ingestion_not_transport_clock_or_redirect_sequence(
    isolated_database, monkeypatch
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        seed(client)
        assert analytics(client)["coverage"]["latest_acquisition_failed"] == 1
        client.app.state.acquirer = acquirer(
            Response(body=(DATA / "sample_jobs/SYN-01.txt").read_bytes())
        )[0]
        assert client.post("/jobs/denied/fetch").status_code == 201
        recovered = analytics(client)["coverage"]
        assert recovered["latest_acquisition_failed"] == 0
        assert recovered["buckets"]["acquisition_failed"] == 0
        assert recovered["buckets"]["pending_extraction"] == 2
        attempts = client.get("/jobs/denied/history").json()["acquisition_attempts"]
        assert len(attempts) == 3
        assert len({a["timestamp"] for a in attempts}) == 1
        assert any(a["status"] == "failed" and a["sequence"] == 1 for a in attempts)
        assert any(a["status"] == "success" and a["sequence"] == 0 for a in attempts)
        assert client.post("/jobs/denied/extract", json={}).status_code == 200
        assert analytics(client)["N"] == 5


@pytest.mark.parametrize("mode", ["hybrid", "onsite"])
def test_v30_grounded_remote_slices_and_exports_share_selection(client, mode):
    source_text = f"Authored {mode} role."

    class AuthoredModeProvider:
        def extract(self, *_):
            return Extraction(
                requirements=[],
                work_mode={
                    "value": mode,
                    "evidence": {"quote": source_text, "start": 0, "end": len(source_text)},
                },
            )

    client.app.state.provider = AuthoredModeProvider()
    client.post(
        "/jobs/import",
        json={
            "jobs": [
                {"job_id": "mode", "company": "Authored mode", "role": "Case", "applied": True}
            ]
        },
    )
    client.post("/jobs/mode/snapshots", json={"text": source_text})
    assert client.post("/jobs/mode/extract", json={}).status_code == 200
    assert analytics(client, remote="true")["N"] == 0
    report = analytics(client, remote="false", applied="true")
    assert report["N"] == 1 and report["coverage"]["buckets"]["successfully_empty"] == 1
    saved = client.post(
        "/exports", json={"kind": "skills", "remote": False, "applied": True}
    ).json()
    for key in ("skills", "clusters", "gaps", "jobs"):
        assert report[key] == saved[key]
    assert client.get("/analytics/skills?positive_response=true").status_code == 422


@pytest.mark.parametrize("boundary", ["flush", "commit"])
def test_v28_extraction_attempt_failure_rolls_back_even_after_savepoint_success(
    isolated_database, monkeypatch, boundary
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        client.post(
            "/jobs/import",
            json={
                "jobs": [{"job_id": "atomic", "company": "Authored atomic", "role": "Analytics"}]
            },
        )
        source(client, "atomic", "SYN-01")
        factory = client.app.state.session_factory
        tables = (db.ExtractionRun, db.RequirementRow, db.ExtractionAttempt)
        with factory() as session:
            before = [session.scalar(select(func.count()).select_from(t)) for t in tables]
        original = Session.flush

        def fail(session, *args, **kwargs):
            if boundary == "commit" or any(
                isinstance(r, db.ExtractionAttempt) for r in session.new
            ):
                raise SQLAlchemyError("authored private diagnostic")
            return original(session, *args, **kwargs)

        monkeypatch.setattr(Session, boundary, fail)
        assert client.post("/jobs/atomic/extract", json={}).status_code == 503
        with factory() as session:
            assert [session.scalar(select(func.count()).select_from(t)) for t in tables] == before


def test_v27_analytics_queries_are_bounded_on_sqlite_and_postgres(isolated_database, monkeypatch):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        client.post(
            "/jobs/import",
            json={
                "jobs": [
                    {
                        "job_id": f"query-{i}",
                        "company": f"Authored query {i}",
                        "role": "Analytics",
                        "applied": i == 0,
                    }
                    for i in range(24)
                ]
            },
        )
        for i in range(24):
            source(client, f"query-{i}", "SYN-01")
        engine = client.app.state.session_factory.kw["bind"]
        statements = []

        def count(_connection, _cursor, statement, *_args):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            assert analytics(client, applied="true")["N"] == 1
            one = len(statements)
            statements.clear()
            assert analytics(client)["N"] == 24
            assert len(statements) == one and one <= 16
        finally:
            event.remove(engine, "before_cursor_execute", count)


def test_v28_migration_preserves_legacy_extractions_without_inventing_failure_history(
    isolated_database, monkeypatch, provider
):
    migrate(isolated_database, "c33b81ed4a05", monkeypatch)
    factory = db.session_factory(isolated_database)
    with factory.begin() as session:
        svc = Service(session, provider)
        svc.import_jobs([JobInput(job_id="legacy", company="Authored legacy", role="Analytics")])
        snapshot = svc.snapshot(
            "legacy", SnapshotInput(text=(DATA / "sample_jobs/SYN-01.txt").read_text())
        )
        run = svc.extract("legacy", "fixture_normalized")
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        assert analytics(client)["N"] == 1
        assert client.get("/jobs/legacy/history").json()["extraction_attempts"] == []
        assert client.get("/jobs/legacy").json()["extraction"]["run_id"] == run["run_id"]
    subprocess.run(
        [sys.executable, "-m", "alembic", "check"], cwd=ROOT, check=True, capture_output=True
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "c33b81ed4a05"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert "extraction_attempts" not in inspect(factory.kw["bind"]).get_table_names()
    with factory() as session:
        assert (
            session.get(db.Snapshot, snapshot.id).raw_text
            == (DATA / "sample_jobs/SYN-01.txt").read_text()
        )
    migrate(isolated_database, "head", monkeypatch)
    factory.kw["bind"].dispose()


def test_v30_missing_revision_invalid_filters_and_zero_denominators_are_explicit(client):
    zero = analytics(client)
    assert zero["N"] == zero["gaps"]["N"] == zero["coverage"]["registered_total"] == 0
    assert zero["gaps"]["groups"] == zero["clusters"]["clusters"] == []
    assert zero["coverage"]["success_fraction"] is zero["coverage"]["matched_fraction"] is None
    for params in [{"remote": "maybe"}, {"applied": "maybe"}, {"profile_id": "alone"}]:
        assert client.get("/analytics/skills", params=params).status_code == 422
    assert (
        client.get(
            "/analytics/skills", params={"profile_id": "missing", "profile_revision_id": "missing"}
        ).status_code
        == 404
    )
