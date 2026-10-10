"""Local inference configuration and strict evidence failures, using authored fake HTTP."""

import copy
import json
from pathlib import Path

import httpx
import pytest

from jobintel.local_model import MODEL, MODEL_SHA256
from jobintel.local_provider import engine_seconds, source_message, source_schema
from jobintel.local_transport import LOCAL_TOKEN, HttpLocalTransport
from jobintel.openai_transport import HttpOpenAITransport, ProviderError, TransportResponse
from jobintel.provider_config import digest
from jobintel.provider_execution import execution_status
from jobintel.providers import selected_provider
from jobintel.schemas import Extraction, Requirement

SOURCE = "🧭 Postgres is required."
QUOTE = "Postgres is required."


def authored_payload():
    requirement = Requirement(
        raw_text=QUOTE,
        normalized_skill_or_requirement="Postgres",
        skills=["Postgres"],
        requirement_type="MUST",
        category="data",
        evidence={"quote": QUOTE, "start": 2, "end": len(SOURCE)},
        confidence=0.8,
    )
    return Extraction(requirements=[requirement]).model_dump(mode="json")


def envelope(payload=None, *, model=MODEL, usage=None):
    text = authored_payload() if payload is None else payload
    content = text if isinstance(text, str) else json.dumps(text)
    reported = (
        None
        if usage is None
        else {
            "prompt_tokens": usage["input_tokens"],
            "completion_tokens": usage["output_tokens"],
            "total_tokens": usage["total_tokens"],
        }
    )
    return TransportResponse(
        {
            "model": model,
            "id": "authored-chat",
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": reported,
        }
    )


def local_http(body, *, requests=None, health=None, models=None):
    def respond(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"} if health is None else health)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": MODEL}]} if models is None else models)
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=body)

    return HttpLocalTransport(
        "http://127.0.0.1:8080/v1/chat/completions",
        transport=httpx.MockTransport(respond),
    )


def test_unseen_unicode_is_grounded_and_normalized_with_actual_wire_usage(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "authored-secret-must-not-leave")
    usage = {"input_tokens": 40, "output_tokens": 80, "total_tokens": 120}
    requests = []
    provider = selected_provider(
        Path("data"), "local", transport=local_http(envelope(usage=usage).body, requests=requests)
    )
    result = provider.extract(SOURCE, "local_normalized_v1")
    assert result.extraction.requirements[0].skills == ["PostgreSQL"]
    evidence = result.extraction.requirements[0].evidence
    assert SOURCE[evidence.start : evidence.end] == QUOTE
    assert result.provenance["usage"] == usage
    assert result.provenance["execution_mode"] == "local-inference"
    assert result.provenance["model_weights_sha256"] == MODEL_SHA256
    assert result.provenance["estimated_cost"] is result.provenance["llm_elapsed_seconds"] is None
    assert requests[0].headers["authorization"] == f"Bearer {LOCAL_TOKEN}"
    assert "authored-secret" not in str(requests[0].headers)
    payload = json.loads(requests[0].content)
    assert json.loads(payload["messages"][1]["content"])["posting"] == SOURCE
    assert payload["stream"] is False
    assert payload["max_tokens"] == 2048
    assert result.provenance["generation_schema_sha256"] == digest(
        payload["response_format"]["json_schema"]["schema"]
    )
    assert execution_status(provider) == {
        "execution_mode": "local-inference",
        "live_llm": True,
        "provider_ready": True,
    }


@pytest.mark.parametrize(
    "payload,code,calls", [("{", "malformed_json", 2), ({"schema_version": 1}, "invalid_schema", 2)]
)
def test_schema_failures_have_one_bounded_retry(payload, code, calls):
    requests = []
    provider = selected_provider(
        Path("data"), "local", transport=local_http(envelope(payload).body, requests=requests)
    )
    with pytest.raises(ProviderError) as caught:
        provider.extract(SOURCE, "local_structured_v1")
    assert caught.value.code == code and not caught.value.retryable
    assert len(requests) == calls
    assert caught.value.provenance["attempt_count"] == calls


def test_bad_grounding_is_not_repaired_or_replayed():
    payload = copy.deepcopy(authored_payload())
    payload["requirements"][0]["evidence"]["start"] = 0
    requests = []
    provider = selected_provider(
        Path("data"), "local", transport=local_http(envelope(payload).body, requests=requests)
    )
    with pytest.raises(ProviderError) as caught:
        provider.extract(SOURCE, "local_normalized_v1")
    assert caught.value.code == "invalid_evidence"
    assert caught.value.status == 422 and not caught.value.retryable
    assert len(requests) == 1


def test_wrong_loaded_model_fails_explicitly_without_retry():
    provider = selected_provider(
        Path("data"), "local", transport=local_http(envelope(model="other").body)
    )
    with pytest.raises(ProviderError, match="model_mismatch"):
        provider.extract(SOURCE, "local_structured_v1")


@pytest.mark.parametrize("models", [{"data": None}, {"data": [{"id": "other"}]}, []])
def test_ready_requires_the_selected_model(models):
    provider = selected_provider(
        Path("data"), "local", transport=local_http(envelope().body, models=models)
    )
    assert not execution_status(provider)["provider_ready"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:8080/v1/responses",
        "http://evil.test:8080/v1/responses",
        "http://127.0.0.1:8080/v1/responses",
        "http://127.0.0.1:8080/v1/chat/completions?key=secret",
        "http://key@127.0.0.1:8080/v1/responses",
    ],
)
def test_local_endpoints_cannot_forward_a_hosted_secret_or_change_protocol(endpoint):
    with pytest.raises(ValueError):
        HttpLocalTransport(endpoint)
    with pytest.raises(ValueError):
        HttpOpenAITransport(
            "authored-secret", mode="local-inference", endpoint="http://localhost:8080/v1/responses"
        )


@pytest.mark.parametrize("timeout", ["nan", "0", "601", "invalid"])
def test_local_timeout_is_bounded_before_requests(monkeypatch, timeout):
    monkeypatch.setenv("JOBINTEL_LOCAL_TIMEOUT", timeout)
    with pytest.raises(ValueError, match="timeout"):
        selected_provider(Path("data"), "local")


@pytest.mark.parametrize(
    "timings",
    [
        None,
        {},
        {"prompt_ms": True, "predicted_ms": 1},
        {"prompt_ms": -1, "predicted_ms": 2},
        {"prompt_ms": float("nan"), "predicted_ms": 2},
    ],
)
def test_unavailable_engine_measurements_are_never_invented(timings):
    assert engine_seconds({"timings": timings}) is None
    assert engine_seconds({"timings": {"prompt_ms": 12, "predicted_ms": 25}}) == 0.037


def test_offset_context_preserves_non_bmp_positions_and_long_input_abstains():
    text = "🧭 Intro\r\nPostgres is required.\n"
    message = json.loads(source_message(text))
    assert message["posting"] == text
    for row in message["lines"]:
        assert text[row["start"] : row["end"]] == row["quote"]
    requests = []
    provider = selected_provider(
        Path("data"), "local", transport=local_http(envelope().body, requests=requests)
    )
    with pytest.raises(ProviderError, match="context_limit"):
        provider.extract("X" * 6001, "local_normalized_v1")
    assert requests == []


def test_generation_choices_preserve_exact_unicode_spans_without_semantic_labels():
    text = "🧭 Intro\r\nPostgres is required.\nJava is not required."
    schema = source_schema(text)
    variants = schema["$defs"]["Requirement"]["oneOf"]
    assert len(variants) == 3
    for variant in variants:
        props = variant["properties"]
        span = props["evidence"]["const"]
        assert text[span["start"] : span["end"]] == props["raw_text"]["const"] == span["quote"]
        assert "$ref" in props["requirement_type"]
    assert "const" not in schema["$defs"]["VersionConstraint"]["properties"]["evidence"]


def test_excessive_source_line_choices_fail_before_model_execution():
    with pytest.raises(ProviderError, match="context_limit"):
        source_schema("X\n" * 65)
