"""V01, V39-V44: migrated atomicity, readiness, provenance and private-log boundaries."""

import json
import logging
import socket
import subprocess
import sys
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError

from jobintel import db
from jobintel.api import create_app
from jobintel.openai_transport import ProviderError
from jobintel.schemas import CandidateProfile, JobInput
from jobintel.service import Service
from tests.integration.test_candidate_revisions import PROFILE, prepare
from tests.integration.test_extraction_boundary_v2 import DATA, ROOT, migrate
from tests.integration.test_extraction_boundary_v2 import (
    isolated_database as isolated_database,
)

TABLES = [
    db.Job,
    db.Snapshot,
    db.ExtractionRun,
    db.RequirementRow,
    db.CandidateEvidenceRow,
    db.MatchRun,
    db.MatchRow,
]


def stored_rows(engine):
    with engine.connect() as connection:
        return {
            model.__tablename__: [
                dict(row)
                for row in connection.execute(
                    select(model.__table__).order_by(*model.__table__.primary_key)
                ).mappings()
            ]
            for model in TABLES
        }


@contextmanager
def fail_after_insert(engine, table):
    writes = []

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith(f"insert into {table} "):
            writes.append(table)
            raise OperationalError(statement, parameters, RuntimeError("authored SQL failure"))

    event.listen(engine, "after_cursor_execute", fail)
    try:
        yield writes
    finally:
        event.remove(engine, "after_cursor_execute", fail)


@pytest.mark.parametrize("boundary", ["api", "service"])
@pytest.mark.parametrize(
    "operation,table",
    [
        ("import", "jobs"),
        ("extract", "requirements"),
        ("match", "matches"),
        ("candidate", "candidate_evidence"),
    ],
)
def test_v39_midwrite_sql_failure_rolls_back_all_new_rows(
    isolated_database, monkeypatch, boundary, operation, table
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        prepare(client)
        prior = client.post("/jobs/synthetic/match", json=PROFILE).json()
        factory = client.app.state.session_factory
        engine = factory.kw["bind"]
        before = stored_rows(engine)
        profile = {**PROFILE, "complete": True}
        jobs = [{"job_id": "new", "company": "New authored", "role": "Engineer"}]
        with fail_after_insert(engine, table) as writes:
            if boundary == "api":
                path, payload = {
                    "import": ("/jobs/import", {"jobs": jobs}),
                    "extract": ("/jobs/synthetic/extract", {}),
                    "match": ("/jobs/synthetic/match", profile),
                    "candidate": ("/candidates/import", profile),
                }[operation]
                assert client.post(path, json=payload).status_code == 503
            else:
                with pytest.raises(OperationalError), factory.begin() as session:
                    svc = Service(session, client.app.state.provider)
                    invoke = {
                        "import": lambda: svc.import_jobs([JobInput(**jobs[0])]),
                        "extract": lambda: svc.extract("synthetic", "fixture_normalized"),
                        "match": lambda: svc.match("synthetic", CandidateProfile(**profile)),
                        "candidate": lambda: svc.import_candidate(CandidateProfile(**profile)),
                    }
                    invoke[operation]()
        assert writes == [table]  # Failure occurred after actual SQL, not at preflight.
        assert stored_rows(engine) == before
        assert client.get(f"/match-runs/{prior['match_run_id']}").json() == prior


def test_v39_matching_failure_after_first_row_preserves_history(isolated_database, monkeypatch):
    import jobintel.service as service_module

    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        prepare(client)
        prior = client.post("/jobs/synthetic/match", json=PROFILE).json()
        factory = client.app.state.session_factory
        before = stored_rows(factory.kw["bind"])
        original = service_module.match_requirement
        calls = []

        def fail(*args):
            calls.append(True)
            if len(calls) == 2:
                # The first match and new profile/run have reached the database.
                raise ProviderError("provider_failure", 502, False)
            return original(*args)

        # Flush each match immediately in this test to inject a genuinely partial write.
        from sqlalchemy.orm import Session

        add = Session.add

        def flush_match(session, instance, *args, **kwargs):
            add(session, instance, *args, **kwargs)
            if isinstance(instance, db.MatchRow):
                session.flush()

        monkeypatch.setattr(service_module, "match_requirement", fail)
        monkeypatch.setattr(Session, "add", flush_match)
        assert (
            client.post("/jobs/synthetic/match", json={**PROFILE, "complete": True}).status_code
            == 502
        )
        assert len(calls) == 2
        assert stored_rows(factory.kw["bind"]) == before
        assert client.get(f"/match-runs/{prior['match_run_id']}").json() == prior


def test_v39_provider_failure_rolls_back_pending_import(isolated_database, monkeypatch, provider):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        saved = prepare(client)
        factory = client.app.state.session_factory
        before = stored_rows(factory.kw["bind"])

        class FailedProvider:
            def extract(self, text, configuration):
                raise ProviderError("timeout", 504, True)

        with pytest.raises(ProviderError), factory.begin() as session:
            svc = Service(session, FailedProvider())
            svc.import_jobs([JobInput(job_id="partial", company="Authored partial", role="One")])
            svc.extract("synthetic", "fixture_normalized")
        assert stored_rows(factory.kw["bind"]) == before
        assert client.get("/jobs/synthetic").json()["extraction"]["run_id"] == saved["run_id"]


def test_v42_outcomes_follow_transaction_commit_and_rollback(client, caplog):
    caplog.set_level(logging.INFO, logger="jobintel.outcomes")
    factory = client.app.state.session_factory
    with factory() as session:
        Service(session, None).import_jobs(
            [JobInput(job_id="rollback", company="Authored rollback", role="One")]
        )
        assert not caplog.records
        session.rollback()
    assert caplog.records[-1].jobintel_outcome["outcome"] == "rolled_back"
    caplog.clear()
    with factory.begin() as session:
        Service(session, None).import_jobs(
            [JobInput(job_id="commit", company="Authored commit", role="One")]
        )
        assert not caplog.records
    assert caplog.records[-1].jobintel_outcome["outcome"] == "committed"


def test_v42_savepoint_outcomes_wait_for_outer_commit(client, caplog):
    caplog.set_level(logging.INFO, logger="jobintel.outcomes")
    factory = client.app.state.session_factory
    with factory.begin() as session:
        with session.begin_nested():
            Service(session, None).import_jobs(
                [JobInput(job_id="kept", company="Authored kept", role="One")]
            )
        assert not caplog.records
        with pytest.raises(ValueError), session.begin_nested():
            Service(session, None).import_jobs(
                [JobInput(job_id="lost", company="Authored lost", role="One")]
            )
            raise ValueError("authored savepoint failure")
        assert [r.jobintel_outcome["outcome"] for r in caplog.records] == ["rolled_back"]
    assert [r.jobintel_outcome["outcome"] for r in caplog.records] == ["rolled_back", "committed"]
    assert [job["job_id"] for job in client.get("/jobs").json()["jobs"]] == ["kept"]


def test_v01_canonical_url_conflict_under_new_id_is_atomic(isolated_database, monkeypatch):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        saved = {
            "job_id": "saved",
            "company": "Authored",
            "role": "One",
            "official_url": "https://example.com/jobs/1",
        }
        assert client.post("/jobs/import", json={"jobs": [saved]}).status_code == 200
        before = stored_rows(client.app.state.session_factory.kw["bind"])
        batch = [
            {"job_id": "partial", "company": "Other", "role": "Two"},
            {
                "job_id": "conflict",
                "company": "Different",
                "role": "Three",
                "official_url": "HTTPS://EXAMPLE.COM:443/jobs/1#fragment",
            },
        ]
        assert client.post("/jobs/import", json={"jobs": batch}).status_code == 409
        assert stored_rows(client.app.state.session_factory.kw["bind"]) == before


def test_v40_unreachable_database_returns_503_without_ddl():
    # Hold a local non-listening port so no unrelated service can claim it.
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
        url = f"postgresql+psycopg://synthetic:unused@127.0.0.1:{port}/absent?connect_timeout=1"
        with TestClient(create_app(url, DATA)) as client:
            result = client.get("/health")
            assert result.status_code == 503
            assert result.json() == {"detail": "database unavailable or migrations required"}


def test_v41_migration_roundtrip_and_model_provenance(isolated_database, monkeypatch):
    migrate(isolated_database, "head", monkeypatch)
    engine = create_engine(isolated_database)
    expected = set(inspect(engine).get_table_names())
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    migrate(isolated_database, "head", monkeypatch)
    assert set(inspect(engine).get_table_names()) == expected
    subprocess.run(
        [sys.executable, "-m", "alembic", "check"], cwd=ROOT, check=True, capture_output=True
    )
    with TestClient(create_app(isolated_database, DATA)) as client:
        extraction = prepare(client)
        matched = client.post("/jobs/synthetic/match", json=PROFILE).json()
        with client.app.state.session_factory() as session:
            run = session.get(db.ExtractionRun, extraction["run_id"])
            snapshot = session.get(db.Snapshot, run.snapshot_id)
            match_run = session.get(db.MatchRun, matched["match_run_id"])
            assert run.provenance["source_sha256"] == snapshot.content_hash
            assert run.schema_version == run.payload["schema_version"] == 2
            assert match_run.extraction_run_id == run.id
            assert match_run.snapshot_id == snapshot.id
            assert session.get(db.CandidateEvidenceRow, match_run.profile_revision_id).payload == (
                CandidateProfile(**PROFILE).model_dump(mode="json")
            )
            for row in session.scalars(select(db.MatchRow)):
                assert row.match_run_id == match_run.id
                assert row.candidate_evidence_id == match_run.profile_revision_id
                assert session.get(db.RequirementRow, row.requirement_id).run_id == run.id
    engine.dispose()


@pytest.mark.parametrize(
    "table,foreign_key",
    [
        (db.Snapshot, "job_id"),
        (db.ExtractionRun, "snapshot_id"),
        (db.RequirementRow, "run_id"),
        (db.MatchRun, "extraction_run_id"),
        (db.MatchRun, "snapshot_id"),
        (db.MatchRun, "profile_revision_id"),
        (db.MatchRow, "requirement_id"),
        (db.MatchRow, "candidate_evidence_id"),
        (db.MatchRow, "match_run_id"),
    ],
)
def test_v41_database_rejects_broken_provenance(isolated_database, monkeypatch, table, foreign_key):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        prepare(client)
        client.post("/jobs/synthetic/match", json=PROFILE)
        engine = client.app.state.session_factory.kw["bind"]
        before = stored_rows(engine)
        values = {**before[table.__tablename__][0], "id": uuid4().hex, foreign_key: "missing"}
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(table.__table__.insert().values(**values))
        assert stored_rows(engine) == before


def test_v42_logs_exclude_private_fields_and_exception_text(client, caplog):
    caplog.set_level(logging.INFO, logger="jobintel.outcomes")
    sentinel = "AUTHORED_PRIVATE_LOG_SENTINEL"
    assert (
        client.post(
            "/jobs/import",
            json={"jobs": [{"job_id": sentinel, "company": sentinel, "role": sentinel}]},
        ).status_code
        == 200
    )
    assert client.post(f"/jobs/{sentinel}/snapshots", json={"text": sentinel}).status_code == 201
    assert (
        client.post(
            "/candidates/import",
            json={
                **PROFILE,
                "profile_id": sentinel,
                "evidence": [{**PROFILE["evidence"][0], "quote": sentinel, "source": sentinel}],
            },
        ).status_code
        == 201
    )

    class PrivateFailure:
        def extract(self, text, configuration):
            raise ValueError(sentinel)

    client.app.state.provider = PrivateFailure()
    assert client.post(f"/jobs/{sentinel}/extract", json={}).status_code == 422
    records = [r for r in caplog.records if r.name == "jobintel.outcomes"]
    assert len(records) == 4
    assert sentinel not in json.dumps([r.__dict__ for r in records], default=str)
    assert all(r.exc_info is None for r in records)
    assert [r.jobintel_outcome["outcome"] for r in records] == [
        "committed",
        "committed",
        "committed",
        "rolled_back",
    ]
    assert records[-1].jobintel_outcome["error_code"] == "validation_error"
    assert all(r.jobintel_outcome["elapsed_ms"] >= 0 for r in records)


def test_v42_sql_errors_hide_private_parameters(client):
    engine = client.app.state.session_factory.kw["bind"]
    sentinel = "AUTHORED_SQL_PARAMETER_SENTINEL"
    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
        connection.execute(
            db.Snapshot.__table__.insert().values(
                id=uuid4().hex,
                job_id="missing",
                raw_text=sentinel,
                clean_text=sentinel,
                content_hash="0" * 64,
            )
        )
    assert sentinel not in str(caught.value)
    assert "parameters hidden" in str(caught.value)
