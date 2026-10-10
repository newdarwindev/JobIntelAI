"""Provider-aware UI wire capabilities; fake HTTP is contract coverage, never model quality."""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from jobintel.api import create_app
from jobintel.openai_transport import EMULATOR_MODEL, EMULATOR_TOKEN, HttpOpenAITransport
from jobintel.providers import selected_provider
from tests.provider_fakes import response
from tests.unit.test_local_provider import SOURCE, authored_payload, envelope, local_http

DATA = Path("data")


def responses_transport(mode):
    def reply(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"mode": "emulator", "inference": False})
        return httpx.Response(200, json=response(authored_payload()).body)

    return HttpOpenAITransport(
        EMULATOR_TOKEN if mode == "emulator" else "authored-secret",
        1 if mode == "emulator" else 30,
        mode=mode,
        endpoint="http://localhost:8033/v1/responses" if mode == "emulator" else None,
        transport=httpx.MockTransport(reply),
    )


@pytest.mark.parametrize("mode", ["fixture", "emulator", "hosted", "local-inference"])
def test_contract_options_submit_valid_configurations_without_exposing_secrets(client, mode):
    provider = (
        "local" if mode == "local-inference" else "fixture" if mode == "fixture" else "openai"
    )
    transport = (
        local_http(envelope().body)
        if provider == "local"
        else responses_transport(mode)
        if provider == "openai"
        else None
    )
    url = str(client.app.state.session_factory.kw["bind"].url)
    app = create_app(
        url,
        DATA,
        provider_name=provider,
        transport=transport,
        model=EMULATOR_MODEL if provider == "openai" else None,
    )
    with TestClient(app) as configured:
        config = configured.get("/ui/config").json()
        assert config["execution_mode"] == mode
        assert config["readiness"] == ("unverified" if mode == "hosted" else "ready")
        assert config["live_llm"] == (mode in {"hosted", "local-inference"})
        assert config["actions"] == {
            "samples": False,
            "reset": False,
            "extract": True,
            "evaluate": True,
        }
        assert "authored-secret" not in str(config)
        assert configured.get("/ui/fixtures").status_code == 404
        assert configured.post("/ui/reset").status_code == 405
        source = (DATA / "sample_jobs/SYN-01.txt").read_text() if mode == "fixture" else SOURCE
        configured.post(
            "/jobs/import",
            json={
                "jobs": [{"job_id": mode, "company": "Authored UI contract", "role": "Engineer"}]
            },
        )
        configured.post(f"/jobs/{mode}/snapshots", json={"text": source})
        for option in config["configurations"]:
            saved = configured.post(f"/jobs/{mode}/extract", json={"configuration": option["id"]})
            assert saved.status_code == 200
            assert saved.json()["configuration"] == option["id"]
        invalid = "local_normalized_v1" if provider != "local" else "fixture_raw"
        assert (
            configured.post(f"/jobs/{mode}/extract", json={"configuration": invalid}).status_code
            == 422
        )


def test_unavailable_provider_disables_only_model_actions_and_recovery_refreshes(client):
    client.app.state.provider = selected_provider(
        DATA, "local", transport=local_http(envelope().body, models={"data": []})
    )
    client.app.state.configuration = "local_normalized_v1"
    config = client.get("/ui/config").json()
    assert config["readiness"] == "unavailable"
    assert not config["actions"]["extract"] and not config["actions"]["evaluate"]
    assert (
        client.post(
            "/jobs/import",
            json={"jobs": [{"job_id": "ready", "company": "Authored", "role": "Engineer"}]},
        ).status_code
        == 200
    )
    client.app.state.provider.transport = local_http(envelope().body)
    assert client.get("/ui/config").json()["actions"]["extract"] is True
