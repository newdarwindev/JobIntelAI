"""V24-V26: immutable candidate selection and transactional migrated match runs."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, create_engine, func, select

from jobintel import db
from jobintel.api import create_app
from jobintel.cli import main
from jobintel.service import Service
from tests.integration.test_extraction_boundary_v2 import (
    DATA,
    migrate,
)
from tests.integration.test_extraction_boundary_v2 import (
    isolated_database as isolated_database,
)

PROFILE = {
    "profile_id": "synthetic-revisions",
    "complete": False,
    "evidence": [
        {
            "skill": "Python",
            "current_capability": "strong",
            "production_evidence": "confirmed",
            "source": "synthetic://revision",
            "quote": "Authored explicit capability.",
        }
    ],
}


def prepare(client):
    assert (
        client.post(
            "/jobs/import",
            json={"jobs": [{"job_id": "synthetic", "company": "Authored", "role": "Engineer"}]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/jobs/synthetic/snapshots",
            json={"text": (DATA / "sample_jobs/SYN-01.txt").read_text()},
        ).status_code
        == 201
    )
    return client.post("/jobs/synthetic/extract", json={}).json()


def selection(revision, run):
    return {
        "profile_id": revision["profile_id"],
        "profile_revision_id": revision["profile_revision_id"],
        "expected_run_id": run["run_id"],
        "as_of": "2025-01-01",
    }


def counts(engine):
    with engine.connect() as connection:
        return [
            connection.scalar(select(func.count()).select_from(table))
            for table in [db.CandidateEvidenceRow, db.MatchRun, db.MatchRow]
        ]


def test_v26_revisions_repeat_matches_stale_selection_and_history(isolated_database, monkeypatch):
    migrate(isolated_database, "head", monkeypatch)
    engine = create_engine(isolated_database)
    with TestClient(create_app(isolated_database, DATA)) as client:
        run = prepare(client)
        old = client.post("/candidates/import", json=PROFILE).json()
        assert client.post("/candidates/import", json=PROFILE).json() == old
        assert counts(engine) == [1, 0, 0]
        revised = client.post("/candidates/import", json={**PROFILE, "complete": True}).json()
        assert revised["profile_revision_id"] != old["profile_revision_id"]
        assert revised["content_hash"] != old["content_hash"]
        assert (
            client.get(
                f"/candidates/{old['profile_id']}/revisions/{old['profile_revision_id']}"
            ).json()
            == old
        )
        assert (
            len(client.get(f"/candidates/{old['profile_id']}/revisions").json()["revisions"]) == 2
        )
        first = client.post("/jobs/synthetic/match", json=selection(old, run)).json()
        again = client.post("/jobs/synthetic/match", json=selection(old, run)).json()
        assert (
            first["profile_revision_id"]
            == again["profile_revision_id"]
            == old["profile_revision_id"]
        )
        assert first["match_run_id"] != again["match_run_id"]
        assert first["matches"] == again["matches"]
        assert first["snapshot_id"] == run["snapshot_id"]
        assert first["profile_content_hash"] == old["content_hash"]
        assert client.get(f"/match-runs/{first['match_run_id']}").json() == first
        complete = client.post("/jobs/synthetic/match", json=selection(revised, run)).json()
        assert [m["status"] for m in complete["matches"]] == ["COVERED", "MISSING"]
        assert counts(engine) == [2, 3, 6]
        wrong = {**selection(old, run), "profile_id": "wrong-profile"}
        assert client.post("/jobs/synthetic/match", json=wrong).status_code == 404
        newer_run = client.post("/jobs/synthetic/extract", json={}).json()
        assert client.post("/jobs/synthetic/match", json=selection(old, run)).status_code == 409
        assert (
            client.post("/jobs/synthetic/match", json=selection(old, newer_run)).status_code == 200
        )
        client.post("/jobs/synthetic/snapshots", json={"text": "Authored changed source."})
        assert (
            client.post("/jobs/synthetic/match", json=selection(revised, newer_run)).status_code
            == 409
        )
        assert client.get(f"/match-runs/{first['match_run_id']}").json() == first
        assert (
            client.put(
                f"/candidates/{old['profile_id']}/revisions/{old['profile_revision_id']}",
                json=PROFILE,
            ).status_code
            == 405
        )
    engine.dispose()


def test_v26_atomic_failure_preserves_revision_and_run(isolated_database, monkeypatch):
    migrate(isolated_database, "head", monkeypatch)
    engine = create_engine(isolated_database)
    with TestClient(create_app(isolated_database, DATA)) as client:
        run = prepare(client)
        revision = client.post("/candidates/import", json=PROFILE).json()
        prior = client.post("/jobs/synthetic/match", json=selection(revision, run)).json()
        before = counts(engine)
        original = Service.match_rows

        def fail(self, *args):
            original(self, *args)
            self.session.flush()
            raise ValueError("authored failure after writes")

        monkeypatch.setattr(Service, "match_rows", fail)
        assert (
            client.post("/jobs/synthetic/match", json={**PROFILE, "complete": True}).status_code
            == 422
        )
        assert counts(engine) == before
        assert client.get(f"/match-runs/{prior['match_run_id']}").json() == prior
        assert (
            client.post(
                "/candidates/import",
                json={
                    **PROFILE,
                    "tenure": [{"skill": "Python", "source": "", "quote": "unsourced"}],
                },
            ).status_code
            == 422
        )
        assert counts(engine) == before
    engine.dispose()


def test_v26_migration_preserves_legacy_candidate_ids(isolated_database, monkeypatch):
    migrate(isolated_database, "a01c4e72b903", monkeypatch)
    engine = create_engine(isolated_database)
    table = Table("candidate_evidence", MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert().values(
                id="legacy-profile-revision",
                profile_id=PROFILE["profile_id"],
                created_at="2020-01-01T00:00:00Z",
                payload=PROFILE,
            )
        )
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        old = client.get(
            f"/candidates/{PROFILE['profile_id']}/revisions/legacy-profile-revision"
        ).json()
        assert old["profile_revision_id"] == "legacy-profile-revision"
        assert client.post("/candidates/import", json=PROFILE).json() == old
        with engine.connect() as connection:
            assert connection.scalar(select(table.c.payload)) == PROFILE
    engine.dispose()


def test_v26_candidate_cli_import_select_match_and_read(client, tmp_path, capsys):
    run = prepare(client)
    path = tmp_path / "synthetic-profile.json"
    path.write_text(json.dumps(PROFILE))
    main(["candidate-import", "--input", str(path)])
    revision = json.loads(capsys.readouterr().out)
    main(["candidate-revisions", "--profile-id", PROFILE["profile_id"]])
    assert json.loads(capsys.readouterr().out)["revisions"] == [revision]
    main(
        [
            "match",
            "--job-id",
            "synthetic",
            "--profile-id",
            PROFILE["profile_id"],
            "--revision-id",
            revision["profile_revision_id"],
            "--run-id",
            run["run_id"],
            "--as-of",
            "2025-01-01",
        ]
    )
    matched = json.loads(capsys.readouterr().out)
    main(["match-run", "--run-id", matched["match_run_id"]])
    assert json.loads(capsys.readouterr().out) == matched
    with pytest.raises(SystemExit) as failure:
        main(["match", "--job-id", "synthetic"])
    assert failure.value.code == 2


def test_v25_migrated_tenure_geography_and_filter_results(isolated_database, monkeypatch):
    from jobintel.schemas import Evidence, Extraction

    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        prepare(client)
        source = "US work authorization required. Travel up to 20% is required."
        authorization = "US work authorization required."
        travel = "Travel up to 20% is required."

        class SourcedProvider:
            def extract(self, text, configuration):
                return Extraction(
                    requirements=[],
                    filters=[
                        {
                            "kind": "work_authorization",
                            "value": "US work authorization",
                            "evidence": Evidence(
                                start=0, end=len(authorization), quote=authorization
                            ),
                        },
                        {
                            "kind": "travel",
                            "value": "up to 20%",
                            "evidence": Evidence(
                                start=len(authorization) + 1, end=len(source), quote=travel
                            ),
                        },
                    ],
                )

        client.app.state.provider = SourcedProvider()
        client.post("/jobs/synthetic/snapshots", json={"text": source})
        run = client.post("/jobs/synthetic/extract", json={}).json()
        revision = client.post(
            "/candidates/import",
            json={
                **PROFILE,
                "eligibility": [
                    {
                        "kind": "work_authorization",
                        "value": "US work authorization",
                        "status": "confirmed",
                        "observed_on": "2020-01-01",
                        "source": "synthetic://authorization",
                        "quote": "Authored authorization evidence.",
                    },
                    {
                        "kind": "travel",
                        "value": "up to 20%",
                        "status": "denied",
                        "observed_on": "2020-01-01",
                        "source": "synthetic://travel",
                        "quote": "Authored explicit travel limit.",
                    },
                ],
            },
        ).json()
        matched = client.post("/jobs/synthetic/match", json=selection(revision, run)).json()
        assert [p["status"] for p in matched["eligibility"]] == ["COVERED", "MISSING"]
        assert matched["matches"] == []
        assert client.get(f"/match-runs/{matched['match_run_id']}").json() == matched
        assert matched["eligibility"][0]["requirement_evidence"]["quote"] == authorization
        assert matched["eligibility"][1]["candidate_sources"][0]["source"] == "synthetic://travel"
