"""V33-V37: migrated evaluation persistence, retrieval, failures and CLI parity."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from jobintel import db
from jobintel.api import create_app
from jobintel.cli import main
from jobintel.evaluation_corpus import load_reviewed
from jobintel.evaluation_runs import human_summary
from jobintel.openai_transport import ProviderError
from jobintel.providers import selected_provider
from tests.integration.test_extraction_boundary_v2 import DATA, migrate
from tests.integration.test_extraction_boundary_v2 import isolated_database as isolated_database
from tests.provider_fakes import FakeTransport, response


def test_v37_append_only_reports_reload_and_export_on_sqlite_postgres(
    isolated_database, monkeypatch, tmp_path
):
    migrate(isolated_database, "head", monkeypatch)
    with TestClient(create_app(isolated_database, DATA)) as client:
        first = client.post("/evaluate", json={}).json()
        reviewed = client.post("/evaluate", json={"dataset": "reviewed"}).json()
        assert reviewed["results"][0]["failed"] == 5
        assert first["evaluation_run_id"] != reviewed["evaluation_run_id"]
        saved = client.get(f"/evaluation-runs/{first['evaluation_run_id']}")
        assert saved.json() == first and saved.headers["cache-control"] == "no-store"
        assert client.get("/evaluation-runs/unknown").status_code == 404
        assert len(client.get("/evaluation-runs").json()["evaluation_runs"]) == 2
        main(["evaluate", "--run-id", first["evaluation_run_id"], "--output", str(tmp_path)])
        assert json.loads((tmp_path / "evaluation.json").read_text()) == first
        assert "20 succeeded, 0 failed" in (tmp_path / "evaluation.txt").read_text()
        with client.app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(db.EvaluationRun)) == 2
            assert session.scalar(select(func.count()).select_from(db.ExtractionRun)) == 0


def test_v37_reviewed_live_fake_transport_usage_and_frozen_hashes(client):
    corpus = load_reviewed(DATA)
    # Returning gold is a scoring/persistence test, never evidence of model quality.
    transport = FakeTransport(
        *(
            response(
                case.gold.model_dump(mode="json"),
                usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            )
            for case in corpus.cases
        )
    )
    client.app.state.provider = selected_provider(
        DATA, "openai", model="synthetic", transport=transport
    )
    pricing = {
        "model": "synthetic",
        "source": "synthetic://test-pricing",
        "date": "2026-10-09",
        "input_usd_per_million": 2,
        "output_usd_per_million": 4,
    }
    result = client.post(
        "/evaluate",
        json={
            "dataset": "reviewed",
            "configurations": ["openai_normalized_v1"],
            "pricing": pricing,
        },
    )
    assert result.status_code == 200
    report = result.json()
    summary = report["results"][0]
    assert summary["tokens"] == 3750 and summary["estimated_cost"] == 0.01
    assert summary["metrics"]["reviewed_metrics"]["semantic_unsupported_claim_rate"]["value"] == 0
    assert summary["metrics"]["reviewed_metrics"]["responsibilities_recall"]["denominator"] == 2
    assert summary["identity"]["prompt_sha256"] and summary["identity"]["schema_sha256"]
    assert summary["model_sha256"] and report["dataset_sha256"] and report["candidate_sha256"]
    assert report["created_at"] <= report["completed_at"]
    assert client.get(f"/evaluation-runs/{report['evaluation_run_id']}").json() == report


def test_v37_partial_failure_is_saved_without_overwriting_prior_report(client, provider):
    previous = client.post("/evaluate", json={}).json()
    first_source = (DATA / "sample_jobs/SYN-01.txt").read_text()
    transport = FakeTransport(
        response(provider.extract(first_source, "fixture_raw").model_dump(mode="json")),
        ProviderError("timeout", 504, True),
    )
    client.app.state.provider = selected_provider(
        DATA, "openai", model="synthetic", transport=transport
    )
    response_result = client.post("/evaluate", json={"configurations": ["openai_structured_v1"]})
    assert response_result.status_code == 504
    report = response_result.json()
    result = report["results"][0]
    assert result["succeeded"] == 1 and result["failed"] == 19
    assert len(transport.requests) == 2
    assert result["per_case"][1]["provenance"]["attempt_count"] == 1
    assert result["per_case"][1]["prediction"] is None
    assert result["per_case"][2]["status"] == "not_attempted"
    stored = client.get(f"/evaluation-runs/{report['evaluation_run_id']}").json()
    assert stored["results"] == report["results"]
    assert client.get(f"/evaluation-runs/{previous['evaluation_run_id']}").json() == previous


def test_v37_pricing_and_config_preflight_make_no_requests(client):
    transport = FakeTransport()
    client.app.state.provider = selected_provider(
        DATA, "openai", model="synthetic", transport=transport
    )
    bad_pricing = {
        "model": "other",
        "source": "synthetic://price",
        "date": "2026-10-09",
        "input_usd_per_million": 1,
        "output_usd_per_million": 1,
    }
    assert (
        client.post(
            "/evaluate", json={"configurations": ["openai_structured_v1"], "pricing": bad_pricing}
        ).status_code
        == 422
    )
    assert client.post("/evaluate", json={"configurations": ["fixture_raw"]}).status_code == 422
    assert (
        client.post("/evaluate", json={"configurations": ["openai_structured_v1"] * 2}).status_code
        == 422
    )
    assert transport.requests == []


def test_v37_saved_reports_require_no_provider_credentials(client, monkeypatch, tmp_path):
    report = client.post("/evaluate", json={}).json()
    monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("JOBINTEL_OPENAI_MODEL", raising=False)
    main(["evaluate", "--run-id", report["evaluation_run_id"], "--output", str(tmp_path)])
    assert json.loads((tmp_path / "evaluation.json").read_text()) == report


def test_v37_unmigrated_database_rejects_evaluation_before_provider_calls(tmp_path):
    transport = FakeTransport()
    url = f"sqlite:///{tmp_path / 'unmigrated.db'}"
    with TestClient(
        create_app(url, DATA, provider_name="openai", model="synthetic", transport=transport)
    ) as client:
        assert (
            client.post("/evaluate", json={"configurations": ["openai_structured_v1"]}).status_code
            == 503
        )
    assert transport.requests == []


def test_v37_historical_reports_keep_unavailable_provenance(client):
    legacy = json.loads((DATA.parent / "results/fixture_evaluation.json").read_text())
    with client.app.state.session_factory.begin() as session:
        row = db.EvaluationRun(payload=legacy)
        session.add(row)
        session.flush()
        run_id = row.id
    stored = client.get(f"/evaluation-runs/{run_id}").json()
    assert stored == {"evaluation_run_id": run_id, **legacy}
    assert "unavailable succeeded" in human_summary(stored)
