"""Emulator selection cannot redirect hosted credentials or label replay as inference."""

import pytest

from jobintel.openai_transport import (
    EMULATOR_MODEL,
    EMULATOR_TOKEN,
    LIVE_ENDPOINT,
    HttpOpenAITransport,
)
from jobintel.providers import selected_provider
from scripts import runtime


@pytest.mark.parametrize(
    "mode,endpoint,key",
    [
        ("hosted", "http://127.0.0.1:8033/v1/responses", "synthetic-hosted-key"),
        ("emulator", "https://api.openai.com/v1/responses", EMULATOR_TOKEN),
        ("emulator", "http://example.com:8033/v1/responses", EMULATOR_TOKEN),
        ("emulator", "http://127.0.0.1:8033/v1/responses?secret=authored", EMULATOR_TOKEN),
        ("emulator", "http://user:password@127.0.0.1:8033/v1/responses", EMULATOR_TOKEN),
        ("emulator", "http://127.0.0.1:8033/v1/responses", "synthetic-hosted-key"),
        ("unknown", None, EMULATOR_TOKEN),
    ],
)
def test_transport_rejects_unsafe_selection_without_requests(mode, endpoint, key):
    with pytest.raises(ValueError) as error:
        HttpOpenAITransport(key, mode=mode, endpoint=endpoint)
    assert key not in str(error.value) and "password" not in str(error.value)


def test_explicit_emulator_ignores_hosted_secrets(monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-never-forward")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", "/nonexistent/must-not-read")
    monkeypatch.setenv("JOBINTEL_RESPONSES_MODE", "emulator")
    monkeypatch.setenv("JOBINTEL_RESPONSES_ENDPOINT", "http://127.0.0.1:8033/v1/responses")
    provider = selected_provider(Path("data"), "openai", model=EMULATOR_MODEL)
    assert provider.transport._api_key == EMULATOR_TOKEN
    assert provider.transport.mode == "emulator"
    assert HttpOpenAITransport("synthetic-hosted-key").endpoint == LIVE_ENDPOINT


def test_contract_runtime_overrides_inherited_live_identity():
    selected = runtime.provider_environment(
        "contract-test",
        {
            "JOBINTEL_CONFIGURATION": "fixture_raw",
            "JOBINTEL_OPENAI_MODEL": "synthetic-hosted-model",
            "OPENAI_API_KEY": "synthetic-never-forward",
        },
    )
    assert selected["JOBINTEL_OPENAI_MODEL"] == EMULATOR_MODEL
    assert selected["JOBINTEL_RESPONSES_MODE"] == "emulator"
    assert selected["JOBINTEL_CONFIGURATION"] == "openai_normalized_v1"
