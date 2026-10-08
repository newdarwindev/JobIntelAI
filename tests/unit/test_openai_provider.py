"""V12-V19: offline contract checks, not measured live extraction quality."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from jobintel.openai_provider import OpenAIProvider
from jobintel.openai_transport import HttpOpenAITransport, ProviderError, TransportResponse
from jobintel.provider_config import PROMPT, strict_schema
from jobintel.providers import selected_configuration, selected_provider
from jobintel.schemas import Extraction
from tests.provider_fakes import FakeTransport, response

DATA = Path(__file__).resolve().parents[2] / "data"


def test_v12_schema_constraints_and_request_provenance(provider, taxonomy):
    text = (DATA / "sample_jobs/SYN-01.txt").read_text()
    payload = provider.extract(text, "fixture_raw").model_dump(mode="json")
    usage = {"input_tokens": 17, "output_tokens": 23, "total_tokens": 40}
    transport = FakeTransport(response(payload, usage=usage))
    result = OpenAIProvider(transport, "synthetic-model", taxonomy).extract(
        text, "openai_normalized_v1"
    )
    request = transport.requests[0]
    assert request["text"]["format"]["strict"] is True
    assert request["store"] is False
    assert request["model"] == "synthetic-model"
    assert request["input"] == [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": text},
    ]
    assert result.extraction.requirements[1].skills == ["PostgreSQL"]
    provenance = result.provenance
    assert provenance["usage"] == usage
    assert provenance["model"] == "synthetic-model"
    assert provenance["response_model"] == "synthetic-snapshot"
    assert provenance["request_id"] == "req-synthetic"
    assert provenance["response_id"] == "resp-synthetic"
    assert provenance["elapsed_seconds"] >= 0
    assert provenance["estimated_cost"] is provenance["llm_elapsed_seconds"] is None
    assert {
        "configuration_version",
        "prompt_version",
        "schema_sha256",
        "taxonomy_sha256",
        "source_sha256",
        "request_sha256",
    }.issubset(provenance)
    schema = strict_schema()
    for node in [schema, *schema["$defs"].values()]:
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
    assert "default" not in json.dumps(schema)


@pytest.mark.parametrize("kind", ["malformed", "extra", "coercion", "truncated"])
def test_v15_one_schema_retry_and_exhaustion(kind, taxonomy):
    payload = Extraction(requirements=[]).model_dump(mode="json")
    if kind == "malformed":
        first = response('{"requirements":')
    elif kind == "extra":
        first = response({**payload, "unknown": "hostile output"})
    elif kind == "coercion":
        first = response({**payload, "schema_version": "2"})
    else:
        first = response(payload, status="incomplete")
    transport = FakeTransport(first, response(payload))
    result = OpenAIProvider(transport, "synthetic", taxonomy).extract(
        "source", "openai_structured_v1"
    )
    assert len(transport.requests) == result.provenance["attempt_count"] == 2
    assert transport.requests[0] == transport.requests[1]
    assert result.provenance["usage"] is None
    exhausted = FakeTransport(first, first)
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(exhausted, "synthetic", taxonomy).extract("source", "openai_structured_v1")
    assert caught.value.status == 502
    assert caught.value.retryable is False
    assert len(exhausted.requests) == 2


def test_v15_retry_usage_includes_both_paid_responses(taxonomy):
    usage = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}
    transport = FakeTransport(
        response("{", usage=usage),
        response(Extraction(requirements=[]).model_dump(mode="json"), usage=usage),
    )
    result = OpenAIProvider(transport, "synthetic", taxonomy).extract(
        "source", "openai_structured_v1"
    )
    assert result.provenance["usage"] == {"input_tokens": 6, "output_tokens": 4, "total_tokens": 10}
    assert len(result.provenance["attempts"]) == 2


def test_v16_refusal_never_becomes_empty_success(taxonomy):
    refusal = TransportResponse(
        {
            "status": "completed",
            "output": [{"content": [{"type": "refusal", "refusal": "untrusted private refusal"}]}],
        }
    )
    transport = FakeTransport(refusal)
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(transport, "synthetic", taxonomy).extract("source", "openai_structured_v1")
    assert (caught.value.code, caught.value.status, caught.value.retryable) == (
        "refusal",
        422,
        False,
    )
    assert "private" not in str(caught.value)
    assert len(transport.requests) == 1


def test_v19_unicode_invalid_evidence_is_not_repaired(provider, taxonomy):
    source = (DATA / "sample_jobs/SYN-01.txt").read_text()
    payload = provider.extract(source, "fixture_raw").model_dump(mode="json")
    text = "🧪" + source
    for requirement in payload["requirements"]:
        requirement["evidence"]["start"] += 2  # UTF-16 offset is invalid for a non-BMP prefix.
        requirement["evidence"]["end"] += 2
    transport = FakeTransport(response(payload))
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(transport, "synthetic", taxonomy).extract(text, "openai_structured_v1")
    assert (caught.value.code, caught.value.status) == ("invalid_evidence", 422)
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (429, "rate_limit", True),
        (429, "quota", False),
        (500, "provider_failure", True),
        (401, "provider_failure", False),
    ],
)
def test_v17_http_failure_contract_and_secret_redaction(status, code, retryable):
    def handler(request):
        assert request.url == "https://api.openai.com/v1/responses"
        assert request.headers["authorization"] == "Bearer synthetic-secret"
        assert json.loads(request.content) == {"model": "synthetic"}
        upstream_code = "insufficient_quota" if code == "quota" else "other"
        return httpx.Response(
            status,
            json={"error": {"code": upstream_code, "message": "synthetic-secret private posting"}},
        )

    transport = HttpOpenAITransport("synthetic-secret", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        transport.complete({"model": "synthetic"})
    assert (caught.value.code, caught.value.status, caught.value.retryable) == (
        code,
        502,
        retryable,
    )
    assert "synthetic-secret" not in json.dumps(caught.value.detail())
    assert "private posting" not in str(caught.value)


@pytest.mark.parametrize(
    "failure,code,status",
    [
        (httpx.ReadTimeout("private"), "timeout", 504),
        (httpx.ConnectError("private"), "provider_failure", 502),
    ],
)
def test_v17_http_network_failures(failure, code, status):
    def handler(request):
        raise failure

    transport = HttpOpenAITransport("fake", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        transport.complete({})
    assert (caught.value.code, caught.value.status, caught.value.retryable) == (code, status, True)


def test_v12_http_success_captures_request_id_and_invalid_envelope():
    def handler(request):
        return httpx.Response(
            200, json={"status": "completed"}, headers={"x-request-id": "req-one"}
        )

    transport = HttpOpenAITransport("fake", transport=httpx.MockTransport(handler))
    assert transport.complete({}).request_id == "req-one"
    for body, code in [(b"{", "malformed_json"), (b"[]", "invalid_schema")]:
        transport = HttpOpenAITransport(
            "fake",
            transport=httpx.MockTransport(
                lambda request, body=body: httpx.Response(200, content=body)
            ),
        )
        with pytest.raises(ProviderError) as caught:
            transport.complete({})
        assert caught.value.code == code


@pytest.mark.parametrize("setting", ["key", "model", "configuration", "provider", "timeout"])
def test_v18_missing_or_unknown_configuration_fails_before_request(monkeypatch, setting):
    monkeypatch.setenv("JOBINTEL_PROVIDER", "openai")
    monkeypatch.setenv("JOBINTEL_OPENAI_MODEL", "synthetic")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.delenv("JOBINTEL_CONFIGURATION", raising=False)
    if setting == "key":
        monkeypatch.delenv("OPENAI_API_KEY")
    elif setting == "model":
        monkeypatch.delenv("JOBINTEL_OPENAI_MODEL")
    elif setting == "provider":
        monkeypatch.setenv("JOBINTEL_PROVIDER", "unknown")
    elif setting == "timeout":
        monkeypatch.setenv("JOBINTEL_OPENAI_TIMEOUT", "nan")
    else:
        monkeypatch.setenv("JOBINTEL_CONFIGURATION", "fixture_raw")
    with pytest.raises(ValueError):
        provider = selected_provider(DATA)
        selected_configuration(provider)


def test_v12_concurrent_requests_keep_their_own_provenance(taxonomy):
    class EchoTransport:
        def complete(self, payload):
            text = payload["input"][1]["content"]
            return response(Extraction(requirements=[]).model_dump(mode="json"), request_id=text)

    provider = OpenAIProvider(EchoTransport(), "synthetic", taxonomy)
    sources = ["synthetic-one", "synthetic-two"]
    with ThreadPoolExecutor(2) as executor:
        results = list(
            executor.map(lambda text: provider.extract(text, "openai_structured_v1"), sources)
        )
    assert [r.provenance["request_id"] for r in results] == sources
    assert results[0].provenance["source_sha256"] != results[1].provenance["source_sha256"]
