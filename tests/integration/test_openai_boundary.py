"""V12-V19: migrated persistence, explicit selection, and CLI/API parity."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from jobintel import db
from jobintel.api import create_app
from jobintel.cli import main
from jobintel.openai_transport import ProviderError
from jobintel.providers import selected_provider
from tests.integration.test_extraction_boundary_v2 import (
    DATA,
    migrate,
)
from tests.integration.test_extraction_boundary_v2 import (
    isolated_database as isolated_database,
)
from tests.provider_fakes import FakeTransport, response


def synthetic_payload(provider):
    source = (DATA / "sample_jobs/SYN-01.txt").read_text()
    return source, provider.extract(source, "fixture_raw").model_dump(mode="json")


def import_source(client, source):
    assert (
        client.post(
            "/jobs/import",
            json={"jobs": [{"job_id": "live", "company": "Synthetic OpenAI", "role": "Engineer"}]},
        ).status_code
        == 200
    )
    assert client.post("/jobs/live/snapshots", json={"text": source}).status_code == 201


@pytest.mark.parametrize(
    "code,status,retryable",
    [
        ("timeout", 504, True),
        ("quota", 502, False),
        ("rate_limit", 502, True),
        ("provider_failure", 502, True),
        ("refusal", 422, False),
        ("invalid_evidence", 422, False),
        ("malformed_json", 502, False),
    ],
)
def test_v19_failed_live_run_is_atomic_without_fixture_fallback(
    client, provider, code, status, retryable
):
    source, payload = synthetic_payload(provider)
    import_source(client, source)
    saved = client.post("/jobs/live/extract", json={}).json()
    if code == "malformed_json":
        failure = response("{")
    elif code == "invalid_evidence":
        payload["requirements"][0]["evidence"]["start"] = 0
        failure = response(payload)
    else:
        failure = ProviderError(code, status, retryable)
    transport = FakeTransport(failure, failure)
    client.app.state.provider = selected_provider(
        DATA, "openai", model="synthetic", transport=transport
    )
    client.app.state.configuration = "openai_normalized_v1"
    result = client.post("/jobs/live/extract", json={})
    assert result.status_code == status
    assert result.json()["detail"]["code"] == code
    assert result.json()["detail"]["retryable"] == retryable
    assert len(transport.requests) == (2 if code == "malformed_json" else 1)
    current = client.get("/jobs/live").json()["extraction"]
    assert current["run_id"] == saved["run_id"]
    assert client.get("/jobs/live/history").json()["snapshots"][0]["runs"] == [
        {
            "created_at": client.get("/jobs/live/history").json()["snapshots"][0]["runs"][0][
                "created_at"
            ],
            **current,
        }
    ]
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(db.ExtractionRun)) == 1
        assert session.scalar(select(func.count()).select_from(db.RequirementRow)) == 2


def test_v12_live_provenance_matching_and_cli_api_parity(
    isolated_database, monkeypatch, provider, capsys, tmp_path
):
    migrate(isolated_database, "head", monkeypatch)
    monkeypatch.setenv("JOBINTEL_OPENAI_MODEL", "synthetic")
    monkeypatch.setenv("JOBINTEL_FIXTURE_ROOT", str(DATA))
    source, payload = synthetic_payload(provider)
    usage = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    transport = FakeTransport(response(payload, usage=usage), response(payload, usage=usage))
    with TestClient(
        create_app(
            isolated_database, DATA, provider_name="openai", model="synthetic", transport=transport
        )
    ) as client:
        health = client.get("/health").json()
        assert health["provider"] == "openai" and health["live_llm"] and health["provider_ready"]
        assert client.get("/ui/config").json()["provider"] == "openai"
        import_source(client, source)
        api = client.post("/jobs/live/extract", json={}).json()
        assert api["provenance"]["provider"] == "openai"
        assert api["provenance"]["usage"] == usage
        assert (
            api["provenance"]["source_sha256"]
            == client.get("/jobs/live").json()["snapshot"]["content_hash"]
        )
        main(
            ["extract", "--provider", "openai", "--job-id", "live", "--output", str(tmp_path)],
            transport=transport,
        )
        cli = json.loads(capsys.readouterr().out)
        assert cli["requirements"] == api["requirements"]
        assert cli["configuration"] == api["configuration"]
        assert cli["provenance"]["schema_sha256"] == api["provenance"]["schema_sha256"]
        assert len(client.get("/jobs/live/history").json()["snapshots"][0]["runs"]) == 2
        # OpenAIProvider deliberately has no public taxonomy attribute.
        assert not hasattr(client.app.state.provider, "taxonomy")
        profile = json.loads((DATA / "sample_candidate.json").read_text())
        assert client.post("/jobs/live/match", json=profile).status_code == 200


def test_v18_explicit_configuration_and_evaluation_preflight(client, provider):
    source, payload = synthetic_payload(provider)
    import_source(client, source)
    transport = FakeTransport(response(payload))
    client.app.state.provider = selected_provider(
        DATA, "openai", model="synthetic", transport=transport
    )
    client.app.state.configuration = "openai_normalized_v1"
    assert (
        client.post("/jobs/live/extract", json={"configuration": "fixture_raw"}).status_code == 422
    )
    assert (
        client.post(
            "/evaluate", json={"configurations": ["openai_structured_v1", "fixture_raw"]}
        ).status_code
        == 422
    )
    assert client.post("/evaluate", json={"configurations": []}).status_code == 422
    assert transport.requests == []
    assert client.post("/jobs/live/extract", json={}).status_code == 200


def test_v17_cli_failure_preserves_prior_run(client, provider, monkeypatch, capsys, tmp_path):
    source, _ = synthetic_payload(provider)
    import_source(client, source)
    saved = client.post("/jobs/live/extract", json={}).json()
    monkeypatch.setenv("JOBINTEL_OPENAI_MODEL", "synthetic")
    transport = FakeTransport(ProviderError("timeout", 504, True))
    with pytest.raises(SystemExit) as caught:
        main(
            ["extract", "--provider", "openai", "--job-id", "live", "--output", str(tmp_path)],
            transport=transport,
        )
    assert caught.value.code == 1
    detail = json.loads(capsys.readouterr().err)
    assert detail["code"] == "timeout" and detail["retryable"]
    assert client.get("/jobs/live").json()["extraction"]["run_id"] == saved["run_id"]


def test_v18_app_missing_key_or_configuration_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
    monkeypatch.setenv("JOBINTEL_OPENAI_MODEL", "synthetic")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_app(f"sqlite:///{tmp_path / 'absent.db'}", DATA)
    transport = FakeTransport()
    with pytest.raises(ValueError, match="configuration"):
        create_app(
            f"sqlite:///{tmp_path / 'absent.db'}",
            DATA,
            model="synthetic",
            transport=transport,
            configuration="fixture_raw",
        )
    with pytest.raises(ValueError, match="synthetic demo"):
        create_app(
            f"sqlite:///{tmp_path / 'absent.db'}",
            DATA,
            demo=True,
            model="synthetic",
            transport=transport,
        )
    assert transport.requests == []


def test_v12_live_evaluation_captures_usage_without_fabricating_quality(client, provider):
    records = []
    for record in json.loads((DATA / "golden_dataset.json").read_text()):
        text = (DATA / record["fixture"]).read_text()
        records.append(
            response(
                provider.extract(text, "fixture_raw").model_dump(mode="json"),
                usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            )
        )
    transport = FakeTransport(*records)
    client.app.state.provider = selected_provider(
        DATA, "openai", model="synthetic", transport=transport
    )
    result = client.post("/evaluate", json={"configurations": ["openai_normalized_v1"]})
    assert result.status_code == 200
    report = result.json()
    assert report["mode"] == "live structured extraction — authored fixture labels"
    assert report["results"][0]["tokens"] == 60
    assert len(report["results"][0]["provenance"]) == 20
    assert report["results"][0]["estimated_cost"] is None
    transport.responses = [ProviderError("quota", 502, False)]
    failed = client.post("/evaluate", json={"configurations": ["openai_structured_v1"]})
    assert failed.status_code == 502
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(db.EvaluationRun)) == 1


def test_v19_migrated_live_failures_preserve_provenance_and_rows(
    isolated_database, monkeypatch, provider
):
    migrate(isolated_database, "head", monkeypatch)
    source, payload = synthetic_payload(provider)
    transport = FakeTransport(response(payload), ProviderError("timeout", 504, True))
    with TestClient(
        create_app(
            isolated_database, DATA, provider_name="openai", model="synthetic", transport=transport
        )
    ) as client:
        import_source(client, source)
        saved = client.post("/jobs/live/extract", json={}).json()
        assert client.post("/jobs/live/extract", json={}).status_code == 504
        assert client.get("/jobs/live").json()["extraction"]["provenance"] == saved["provenance"]
        with client.app.state.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(db.ExtractionRun)) == 1
            assert session.scalar(select(func.count()).select_from(db.RequirementRow)) == 2
