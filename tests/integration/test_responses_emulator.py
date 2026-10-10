"""Real provider process/socket contracts on migrated SQLite and PostgreSQL."""

import json
import select
import subprocess
import sys
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy import select as sql_select

from jobintel import db
from jobintel.api import create_app
from jobintel.openai_transport import EMULATOR_MODEL, EMULATOR_TOKEN, HttpOpenAITransport
from jobintel.providers import selected_provider
from scripts.responses_environment import request
from tests.integration.test_extraction_boundary_v2 import DATA, ROOT, migrate
from tests.integration.test_extraction_boundary_v2 import isolated_database as isolated_database
from tests.integration.test_openai_boundary import import_source


class Emulator:
    def __init__(self):
        self.port = 0
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "scripts.responses_emulator.server", "--port", str(self.port)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        assert select.select([self.process.stdout], [], [], 15)[0], "emulator startup timed out"
        ready = json.loads(self.process.stdout.readline())
        self.port = ready["port"]
        self.base = f"http://127.0.0.1:{self.port}"

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process.stdout.close()
            self.process = None


@pytest.fixture
def emulator():
    service = Emulator()
    try:
        service.start()
        yield service
    finally:
        service.stop()


@pytest.mark.parametrize("invalid", ["auth", "model", "schema", "parameters"])
def test_emulator_rejects_contract_violations_without_echo(emulator, invalid):
    from tests.provider_fakes import FakeTransport

    provider = selected_provider(DATA, "openai", model=EMULATOR_MODEL, transport=FakeTransport())
    payload = provider.request((DATA / "sample_jobs/SYN-01.txt").read_text())
    token = EMULATOR_TOKEN
    if invalid == "auth":
        token = "synthetic-invalid-auth"
    elif invalid == "model":
        payload["model"] = "synthetic-wrong-model"
    elif invalid == "schema":
        payload["text"]["format"]["strict"] = False
    else:
        payload["store"] = True
    with httpx.Client(trust_env=False) as client:
        response = client.post(
            emulator.base + "/v1/responses",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == (401 if invalid == "auth" else 400)
    assert response.json() == {"error": {"code": "contract_violation"}}
    diagnostics = request(emulator.base, "/diagnostics")
    assert diagnostics["request_count"] == 1 and not diagnostics["requests"][0][invalid + "_valid"]
    assert token not in response.text + json.dumps(diagnostics)


@contextmanager
def api_client(url, monkeypatch, emulator):
    migrate(url, "head", monkeypatch)
    transport = HttpOpenAITransport(
        EMULATOR_TOKEN, 1, mode="emulator", endpoint=emulator.base + "/v1/responses"
    )
    with TestClient(
        create_app(
            url=url,
            root=DATA,
            provider_name="openai",
            transport=transport,
            model=EMULATOR_MODEL,
        )
    ) as client:
        source = (DATA / "sample_jobs/SYN-01.txt").read_text()
        import_source(client, source)
        yield client, source


@pytest.mark.parametrize(
    "scenario,status,code,retryable,count",
    [
        ("refusal", 422, "refusal", False, 1),
        ("invalid_evidence", 422, "invalid_evidence", False, 1),
        ("malformed_json", 502, "malformed_json", False, 2),
        ("malformed_http", 502, "malformed_json", False, 2),
        ("invalid_schema", 502, "invalid_schema", False, 2),
        ("truncated", 502, "truncated_json", False, 2),
        ("rate_limit", 502, "rate_limit", True, 1),
        ("quota", 502, "quota", False, 1),
        ("server_error", 502, "provider_failure", True, 1),
        ("delay", 504, "timeout", True, 1),
        ("connection_close", 502, "provider_failure", True, 1),
    ],
)
def test_wire_failures_preserve_success(
    isolated_database, monkeypatch, emulator, scenario, status, code, retryable, count
):
    with api_client(isolated_database, monkeypatch, emulator) as (client, source):
        saved = client.post("/jobs/live/extract", json={}).json()
        request(emulator.base, "/control", {"scenario": scenario})
        failed = client.post("/jobs/live/extract", json={})
        assert failed.status_code == status
        assert failed.json()["detail"] == {
            "code": code,
            "retryable": retryable,
            "message": f"extraction provider: {code}",
        }
        assert client.get("/jobs/live").json()["extraction"]["run_id"] == saved["run_id"]
        diagnostics = request(emulator.base, "/diagnostics")
        assert diagnostics["request_count"] == count
        assert all(
            all(
                r[k]
                for k in (
                    "auth_valid",
                    "model_valid",
                    "schema_valid",
                    "parameters_valid",
                    "input_valid",
                )
            )
            for r in diagnostics["requests"]
        )
        assert EMULATOR_TOKEN not in json.dumps(diagnostics) and source not in json.dumps(
            diagnostics
        )
        with client.app.state.session_factory() as session:
            assert session.scalar(sql_select(func.count()).select_from(db.ExtractionRun)) == 1
            assert session.scalar(sql_select(func.count()).select_from(db.ExtractionAttempt)) == 2
        request(emulator.base, "/control", {"scenario": "success"})
        recovered = client.post("/jobs/live/extract", json={})
        assert recovered.status_code == 200 and recovered.json()["run_id"] != saved["run_id"]


def test_wire_success_retry_report_and_process_recovery(isolated_database, monkeypatch, emulator):
    with api_client(isolated_database, monkeypatch, emulator) as (client, source):
        health = client.get("/health").json()
        assert health["execution_mode"] == "emulator" and not health["live_llm"]
        assert health["provider_ready"]
        request(emulator.base, "/control", {"scenario": "malformed_then_success"})
        saved = client.post("/jobs/live/extract", json={}).json()
        job = client.get("/jobs/live").json()
        provenance = job["extraction"]["provenance"]
        assert provenance["execution_mode"] == "emulator"
        assert provenance["model"] == EMULATOR_MODEL and provenance["attempt_count"] == 2
        assert (
            provenance["usage"]
            is provenance["estimated_cost"]
            is provenance["llm_elapsed_seconds"]
            is None
        )
        for row in job["extraction"]["requirements"]:
            evidence = row["evidence"]
            assert source[evidence["start"] : evidence["end"]] == evidence["quote"]
        emulator.stop()
        assert client.get("/health").status_code == 503
        assert client.get("/health").json()["provider_ready"] is False
        failed = client.post("/jobs/live/extract", json={})
        assert failed.status_code == 502 and failed.json()["detail"]["code"] == "provider_failure"
        assert client.get("/jobs/live").json()["extraction"]["run_id"] == saved["run_id"]
        emulator.start()
        assert client.get("/health").json()["provider_ready"]
        assert client.post("/jobs/live/extract", json={}).status_code == 200
        report = client.post("/evaluate", json={}).json()
        assert report["status"] == "completed" and report["dataset_size"] == 20
        assert "not model quality" in report["mode"]
        assert report["results"][0]["identity"]["execution_mode"] == "emulator"
        assert report["results"][0]["tokens"] is report["results"][0]["estimated_cost"] is None
        assert request(emulator.base, "/diagnostics")["request_count"] == 21
        assert client.get("/responses-fixture-diagnostics").status_code == 404
        assert client.post("/responses-fixture/success").status_code == 404
