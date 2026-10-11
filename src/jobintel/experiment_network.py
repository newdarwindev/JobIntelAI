"""Bounded, credential-free network protocols; emulator output is contract evidence."""

from copy import deepcopy
from time import perf_counter

from jobintel.experiment_corpus import digest
from jobintel.experiment_provider import (
    OpenAIExperimentProvider,
    measured_usage,
    validate_response_limits,
)
from jobintel.experiments import CONFIGURATIONS, Prediction
from jobintel.local_model import MODEL, model_identity
from jobintel.local_provider import LocalProvider
from jobintel.openai_provider import parse_extraction
from jobintel.openai_transport import EMULATOR_MODEL, ProviderError
from jobintel.provider_config import local_prompt
from jobintel.snapshots import content_hash

NETWORK_MODES = {"local-inference", "emulator"}


def configurations(mode):
    values = deepcopy(CONFIGURATIONS)
    if mode == "local-inference":
        for value in values.values():
            value.update(
                prompt=local_prompt().split("\nReturn JSON matching this schema: ")[0],
                prompt_version="local-experiment-v1",
                protocol="chat_completions",
                generation_schema="source-lines-v1",
                temperature=0,
                seed=42,
                model_identity=model_identity(),
            )
    elif mode == "emulator":
        for value in values.values():
            value.update(protocol="responses", execution_identity="authored-contract-v2")
    return values


def preflight(corpus, spec, mode):
    from jobintel.experiment_reviewed import ReviewedExperimentCorpus

    if "A" in spec.configurations:
        raise ValueError("network experiments support structured B and normalized C only")
    expected = MODEL if mode == "local-inference" else EMULATOR_MODEL
    if spec.model != expected:
        raise ValueError("network experiment model must match the pinned runtime")
    if spec.pricing is not None or spec.budget_usd != 0 or spec.authorization_reference:
        raise ValueError("network experiments use no purchased API budget or hosted authorization")
    if not isinstance(corpus, ReviewedExperimentCorpus):
        raise ValueError("network experiments require the source-reviewed frozen corpus")
    review = corpus.review
    if not (review.independent and review.reviewer and review.method and review.revision):
        raise ValueError("network experiments require an explicit source annotation review")
    limit = 2048 if mode == "local-inference" else 8192
    if spec.max_output_tokens > limit:
        raise ValueError("output reservation exceeds runtime capacity")
    if mode == "local-inference" and spec.max_input_tokens + spec.max_output_tokens > 8192:
        raise ValueError("token reservations exceed the pinned engine context")


def local_payload(text, configuration, spec):
    try:
        payload = LocalProvider(None, None).request(text)
    except ProviderError:
        raise ValueError("frozen source exceeds the local generation context") from None
    payload["model"] = spec.model
    payload["max_tokens"] = spec.max_output_tokens
    payload["messages"][0]["content"] = configuration["prompt"]
    return payload


class EmulatorExperimentProvider(OpenAIExperimentProvider):
    mode = "emulator"

    def predict(self, text, configuration, spec):
        try:
            result = super().predict(text, configuration, spec)
        except ProviderError as error:
            error.provenance.update(execution_mode=self.mode, inference=False)
            raise
        result.provenance.update(execution_mode=self.mode, inference=False)
        return result


class LocalExperimentProvider:
    mode = "local-inference"

    def __init__(self, transport):
        self.transport = transport

    def predict(self, text, configuration, spec):
        payload = local_payload(text, configuration, spec)
        adapter = LocalProvider(self.transport, None)
        metadata = adapter.metadata(None)
        started = perf_counter()
        output = None
        try:
            response = self.transport.complete(payload)
            metadata = adapter.metadata(response)
            output = bounded_chat_output(response.body)
            validate_response_limits(metadata, spec)
            adapter.validate_response(response.body)
            extraction = parse_extraction(adapter_text(response.body))
            return Prediction(
                extraction=extraction,
                usage=measured_usage(metadata),
                model=metadata["response_model"],
                request_id=metadata["request_id"],
                provenance=local_provenance(payload, text, metadata, perf_counter() - started),
                output_text=output,
            )
        except ProviderError as error:
            error.provenance = local_provenance(payload, text, metadata, perf_counter() - started)
            error.output_text = output
            raise


def adapter_text(body):
    from jobintel.local_provider import chat_text

    return chat_text(body)


def bounded_chat_output(body):
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    output = message.get("content") if isinstance(message, dict) else None
    return output[:128000] if isinstance(output, str) else None


def local_provenance(payload, text, metadata, elapsed):
    return {
        **metadata,
        **model_identity(),
        "execution_mode": "local-inference",
        "inference": True,
        "elapsed_seconds": elapsed,
        "request_sha256": digest(payload),
        "source_sha256": content_hash(text),
        "prompt_sha256": content_hash(payload["messages"][0]["content"]),
        "schema_sha256": digest(payload["response_format"]["json_schema"]["schema"]),
        "requested_model": payload["model"],
        "attempt_count": 1,
        "request_parameters": {
            "api": "chat_completions",
            "max_tokens": payload["max_tokens"],
            "temperature": 0,
            "seed": 42,
            "stream": False,
        },
    }
