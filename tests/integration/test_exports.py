"""V31-V32: persisted selection, all provenance links and API/CLI download equivalence."""

import csv
import io
import json
import logging
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from jobintel import db
from jobintel.api import create_app
from jobintel.cli import main
from jobintel.export_cli import private_output
from jobintel.exports import SKILL_COLUMNS
from jobintel.schemas import Extraction
from tests.integration.test_candidate_revisions import PROFILE, prepare, selection
from tests.integration.test_extraction_boundary_v2 import DATA, ROOT, migrate
from tests.integration.test_extraction_boundary_v2 import (
    isolated_database as isolated_database,
)


def export(client, **payload):
    response = client.post("/exports", json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json() if payload.get("format", "json") == "json" else response.text


def match_selection(client, profile, run):
    revision = client.post("/candidates/import", json=profile).json()
    matched = client.post("/jobs/synthetic/match", json=selection(revision, run)).json()
    return revision, matched


def verify_links(client, report):
    with client.app.state.session_factory() as session:
        for row in report["rows"]:
            source = session.get(db.Snapshot, row["snapshot_id"])
            run = session.get(db.ExtractionRun, row["run_id"])
            requirement = session.get(db.RequirementRow, row["requirement_id"])
            assert source.job_id == row["job_id"]
            assert source.content_hash == row["content_hash"]
            assert sha256(source.raw_text.encode()).hexdigest() == row["raw_source_sha256"]
            assert run.snapshot_id == source.id and requirement.run_id == run.id
            assert run.configuration == row["configuration"]
            assert (
                source.clean_text[row["evidence_start"] : row["evidence_end"]]
                == row["evidence_quote"]
            )
            assert row["raw_text"] == row["evidence_quote"]
            if row["match_run_id"] is not None:
                match_run = session.get(db.MatchRun, row["match_run_id"])
                matched = session.get(db.MatchRow, row["match_id"])
                profile = session.get(db.CandidateEvidenceRow, row["profile_revision_id"])
                assert match_run.extraction_run_id == run.id and match_run.snapshot_id == source.id
                assert (
                    matched.match_run_id == match_run.id
                    and matched.requirement_id == requirement.id
                )
                assert matched.candidate_evidence_id == match_run.profile_revision_id == profile.id
                assert row["profile_id"] == profile.profile_id
                assert row["match_status"] == matched.payload["status"]


def test_v31_current_and_historical_exports_preserve_source_profile_links(
    isolated_database, monkeypatch
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        run = prepare(client)
        old, prior = match_selection(client, PROFILE, run)
        complete, _ = match_selection(client, {**PROFILE, "complete": True}, run)
        selected = {
            "profile_id": old["profile_id"],
            "profile_revision_id": old["profile_revision_id"],
        }
        report = export(client, kind="matches", **selected)
        assert report["N"] == report["matched_jobs_N"] == 1
        assert {r["match_status"] for r in report["rows"]} == {"COVERED", "UNKNOWN"}
        assert {r["match_run_id"] for r in report["rows"]} == {prior["match_run_id"]}
        verify_links(client, report)
        parsed = list(
            csv.DictReader(io.StringIO(export(client, kind="matches", format="csv", **selected)))
        )
        for original, flat in zip(report["rows"], parsed, strict=True):
            for key in [
                "job_id",
                "snapshot_id",
                "run_id",
                "requirement_id",
                "match_run_id",
                "match_id",
                "profile_revision_id",
                "content_hash",
                "match_status",
            ]:
                assert flat[key] == original[key]
            assert json.loads(flat["candidate_sources"]) == original["candidate_sources"]
            assert int(flat["evidence_start"]) == original["evidence_start"]
            assert flat["denominator"] == report["denominator"]
        assert (
            client.post(
                "/exports",
                json={
                    "kind": "matches",
                    "historical": True,
                    "match_run_ids": [prior["match_run_id"]],
                    "profile_id": complete["profile_id"],
                    "profile_revision_id": complete["profile_revision_id"],
                },
            ).status_code
            == 422
        )
        other = export(
            client,
            kind="matches",
            profile_id=complete["profile_id"],
            profile_revision_id=complete["profile_revision_id"],
        )
        assert {r["match_status"] for r in other["rows"]} == {"COVERED", "MISSING"}
        repeat = client.post("/jobs/synthetic/match", json=selection(old, run)).json()
        assert {r["match_run_id"] for r in export(client, kind="matches", **selected)["rows"]} == {
            repeat["match_run_id"]
        }
        current_run = client.post("/jobs/synthetic/extract", json={}).json()
        assert export(client, kind="matches", **selected)["rows"] == []
        requirements = export(client, kind="requirements", **selected)
        assert len(requirements["rows"]) == 2
        assert all(r["match_status"] is None for r in requirements["rows"])
        assert {r["run_id"] for r in requirements["rows"]} == {current_run["run_id"]}
        client.post("/jobs/synthetic/snapshots", json={"text": "Authored changed source."})
        assert export(client, kind="requirements")["N"] == 0
        historical = export(
            client, kind="matches", historical=True, match_run_ids=[prior["match_run_id"]]
        )
        assert historical["match_run_id"] == prior["match_run_id"]
        assert len(historical["rows"]) == 2
        verify_links(client, historical)
        multiple = export(
            client, kind="skills", historical=True, run_ids=[run["run_id"], current_run["run_id"]]
        )
        assert multiple["N"] == 1
        assert multiple["skills"][0]["n"] == 1
        assert len(multiple["jobs"]) == 2
        assert (
            client.post(
                "/exports", json={"kind": "requirements", "run_ids": [run["run_id"]]}
            ).status_code
            == 422
        )


def test_v31_api_cli_equivalence_and_legacy_columns(client, tmp_path, capsys):
    run = prepare(client)
    revision, _ = match_selection(client, PROFILE, run)
    options = {
        "profile_id": revision["profile_id"],
        "profile_revision_id": revision["profile_revision_id"],
        "job_ids": ["synthetic"],
    }
    for kind in ["skills", "requirements", "matches", "evidence"]:
        main(
            [
                "export",
                "--kind",
                kind,
                "--job-id",
                "synthetic",
                "--profile-id",
                revision["profile_id"],
                "--revision-id",
                revision["profile_revision_id"],
                "--output",
                str(tmp_path),
            ]
        )
        assert json.loads((tmp_path / f"{kind}.json").read_text()) == export(
            client, kind=kind, **options
        )
        assert (tmp_path / f"{kind}.csv").read_bytes() == export(
            client, kind=kind, format="csv", **options
        ).encode()
    main(["export", "--output", str(tmp_path)])
    assert (
        next(csv.reader(io.StringIO((tmp_path / "skill_counts.csv").read_text()))) == SKILL_COLUMNS
    )
    assert json.loads((tmp_path / "skill_counts.json").read_text())["N"] == 1
    assert "Python is required" not in capsys.readouterr().out


def test_v31_empty_success_any_all_and_applied_denominators(client):
    jobs = [
        {"job_id": "any", "company": "Authored ANY", "role": "One", "applied": True},
        {"job_id": "all", "company": "Authored ALL", "role": "Two", "applied": False},
        {"job_id": "empty", "company": "Authored empty", "role": "Three"},
        {"job_id": "pending", "company": "Authored pending", "role": "Four"},
    ]
    client.post("/jobs/import", json={"jobs": jobs})
    for job_id, fixture in [("any", "SYN-02"), ("all", "SYN-03"), ("empty", "SYN-18")]:
        text = (DATA / f"sample_jobs/{fixture}.txt").read_text()
        client.post(f"/jobs/{job_id}/snapshots", json={"text": text})
        assert client.post(f"/jobs/{job_id}/extract", json={}).status_code == 200
    report = export(client, kind="requirements")
    assert report["N"] == 3 and report["registered_jobs_N"] == 4
    assert not any(r["job_id"] == "empty" for r in report["rows"])
    assert [r["operator"] for r in report["rows"] if r["job_id"] == "any"] == ["ANY"]
    assert [r["skills"] for r in report["rows"] if r["job_id"] == "any"] == [["AWS", "Azure"]]
    assert [r["operator"] for r in report["rows"] if r["job_id"] == "all"] == ["ALL"]
    assert export(client, kind="skills", applied=True)["N"] == 1
    assert export(client, kind="skills", applied=False)["N"] == 1
    assert all(r["match_status"] is None for r in report["rows"])


def test_v32_formula_fields_json_exact_csv_safe_and_no_body_logs(client, caplog):
    caplog.set_level(logging.INFO, logger="jobintel.outcomes")
    skill = '=AUTHORED("x,y")'
    source = f"😀 Authored introduction.\n{skill} is required."
    quote = f"{skill} is required."
    start = source.index(quote)

    class AuthoredProvider:
        def extract(self, text, configuration):
            return Extraction(
                requirements=[
                    {
                        "raw_text": quote,
                        "normalized_skill_or_requirement": skill,
                        "skills": [skill],
                        "operator": "SINGLE",
                        "requirement_type": "MUST",
                        "category": "@Category",
                        "confidence": 1,
                        "notes": "+Authored note",
                        "evidence": {"quote": quote, "start": start, "end": len(source)},
                    }
                ]
            )

    client.app.state.provider = AuthoredProvider()
    company, role = "\t=Authored company", '\ufeff-Authored "role", 😀'
    client.post(
        "/jobs/import", json={"jobs": [{"job_id": "formula", "company": company, "role": role}]}
    )
    assert (
        client.post(
            "/jobs/formula/snapshots", json={"text": source, "source_url": "\t+Authored source"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/jobs/formula/snapshots",
            json={"text": source, "source_url": "https://example.com/authored-source"},
        ).status_code
        == 201
    )
    assert client.post("/jobs/formula/extract", json={}).status_code == 200
    profile = {
        "profile_id": "@Authored profile",
        "evidence": [
            {
                "skill": skill,
                "current_capability": "strong",
                "production_evidence": "unknown",
                "source": "=Authored source",
                "quote": "@Authored candidate quote",
            }
        ],
    }
    matched = client.post("/jobs/formula/match", json=profile).json()
    options = {
        "profile_id": profile["profile_id"],
        "profile_revision_id": matched["profile_revision_id"],
    }
    report = export(client, kind="matches", **options)
    row = report["rows"][0]
    assert row["company"] == company and row["role"] == role and row["raw_text"] == quote
    assert row["skills"] == [skill] and row["profile_id"] == profile["profile_id"]
    parsed = next(
        csv.DictReader(io.StringIO(export(client, kind="matches", format="csv", **options)))
    )
    for key in [
        "company",
        "role",
        "raw_text",
        "normalized_skill_or_requirement",
        "category",
        "notes",
        "profile_id",
        "evidence_quote",
    ]:
        assert parsed[key] == "'" + row[key]
    assert parsed["source_url"] == row["source_url"]
    assert json.loads(parsed["candidate_sources"]) == row["candidate_sources"]
    assert json.loads(parsed["skills"]) == [skill]
    assert all(
        source not in record.getMessage() and company not in record.getMessage()
        for record in caplog.records
    )
    verify_links(client, report)


def test_v31_group_version_obligations_and_unknown_survive_csv(client):
    client.post("/jobs/import", json={"csv_text": (DATA / "sample_registry.csv").read_text()})
    for job_id in ["SYN-02", "SYN-03", "SYN-14", "SYN-15"]:
        client.post(
            f"/jobs/{job_id}/snapshots",
            json={"text": (DATA / f"sample_jobs/{job_id}.txt").read_text()},
        )
        client.post(f"/jobs/{job_id}/extract", json={})
    report = export(client, kind="requirements")
    parsed = list(csv.DictReader(io.StringIO(export(client, kind="requirements", format="csv"))))
    for row, flat in zip(report["rows"], parsed, strict=True):
        assert flat["operator"] == row["operator"]
        assert flat["requirement_type"] == row["requirement_type"]
        assert flat["production_obligation"] == row["production_obligation"]
        assert flat["experience_obligation"] == row["experience_obligation"]
        assert json.loads(flat["skills"]) == row["skills"]
        assert json.loads(flat["version_constraints"]) == row["version_constraints"]
        assert flat["match_status"] == "" and row["match_status"] is None
    assert {row["operator"] for row in report["rows"]} >= {"ANY", "ALL"}
    assert any(row["version_constraints"] for row in report["rows"])
    before = export(client, kind="skills")
    old_run = next(
        job["extraction"]["run_id"] for job in before["jobs"] if job["job_id"] == "SYN-02"
    )
    new_run = client.post("/jobs/SYN-02/extract", json={}).json()["run_id"]
    history = export(client, kind="skills", historical=True, run_ids=[old_run, new_run])
    assert history["N"] == 1 and len(history["alternatives"]) == 1


def test_v31_invalid_selection_unknown_rows_and_empty_exports(client):
    for kind in ["skills", "requirements"]:
        result = export(client, kind=kind)
        assert result["N"] == 0
        parsed = list(csv.DictReader(io.StringIO(export(client, kind=kind, format="csv"))))
        assert parsed == []
    assert client.post("/exports", json={"kind": "matches"}).status_code == 422
    assert client.post("/exports", json={"job_ids": ["absent"]}).status_code == 404
    assert (
        client.post("/exports", json={"historical": True, "run_ids": ["absent"]}).status_code == 404
    )
    assert (
        client.post(
            "/exports", json={"profile_id": "wrong", "profile_revision_id": "absent"}
        ).status_code
        == 404
    )
    assert (
        client.post("/exports", json={"kind": "evidence", "job_ids": ["absent"]}).status_code == 404
    )


def test_v31_export_queries_do_not_grow_per_job(client):
    client.post("/jobs/import", json={"csv_text": (DATA / "sample_registry.csv").read_text()})
    factory = client.app.state.session_factory
    queries = []

    def count(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(factory.kw["bind"], "before_cursor_execute", count)
    try:
        export(client, kind="requirements", job_ids=["SYN-01"])
        one = len(queries)
        queries.clear()
        export(client, kind="requirements")
        assert len(queries) == one
    finally:
        event.remove(factory.kw["bind"], "before_cursor_execute", count)


def test_v32_private_exports_require_ignored_checkout_paths(tmp_path):
    private_output(tmp_path)
    private_output(ROOT / "local_data/export-tests")
    with pytest.raises(ValueError, match="ignored path"):
        private_output(ROOT / "public-export-test")
