"""One Responses request per experimental prediction; credentials stay in transport."""

import json
import re
from copy import deepcopy
from time import perf_counter

from jobintel.experiment_corpus import digest
from jobintel.experiments import Prediction, Usage
from jobintel.openai_provider import parse_response, response_metadata
from jobintel.openai_transport import ProviderError
from jobintel.snapshots import content_hash


def request_payload(text, configuration, spec):
    prompt = configuration["prompt"]
    if not configuration["structured"]:
        prompt += "\nReturn one JSON object conforming to this schema:\n" + json.dumps(
            configuration["schema"], ensure_ascii=False, sort_keys=True
        )
    payload = {
        "model": spec.model,
        "store": False,
        "max_output_tokens": spec.max_output_tokens,
        "input": [{"role": "system", "content": prompt}, {"role": "user", "content": text}],
    }
    if configuration["structured"]:
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": "job_extraction_v2",
                "strict": True,
                "schema": deepcopy(configuration["schema"]),
            }
        }
    return payload


class OpenAIExperimentProvider:
    mode = "live"

    def __init__(self, transport):
        self.transport = transport

    def predict(self, text, configuration, spec):
        payload = request_payload(text, configuration, spec)
        started = perf_counter()
        metadata = response_metadata(None)
        output_text = None
        try:
            response = self.transport.complete(payload)
            metadata = response_metadata(response)
            output_text = raw_output(response.body)
            validate_response_limits(metadata, spec)
            extraction = parse_response(response.body)
            return Prediction(
                extraction=extraction,
                usage=measured_usage(metadata),
                model=metadata["response_model"],
                request_id=metadata["request_id"],
                provenance=provenance(payload, text, metadata, perf_counter() - started),
                output_text=output_text,
            )
        except ProviderError as error:
            error.provenance = provenance(payload, text, metadata, perf_counter() - started)
            error.output_text = output_text
            raise


def measured_usage(metadata):
    usage = metadata["usage"]
    if usage is None or any(usage[k] is None for k in ["input_tokens", "output_tokens"]):
        return None
    return Usage(input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"])


def raw_output(body):
    output = body.get("output")
    if not isinstance(output, list):
        return None
    parts = [
        part.get("text")
        for item in output
        if isinstance(item, dict) and isinstance(item.get("content"), list)
        for part in item["content"]
        if isinstance(part, dict) and part.get("type") == "output_text"
    ]
    return "".join(p for p in parts if isinstance(p, str))[:128000] or None


def validate_response_limits(metadata, spec):
    if metadata["response_model"] is None:
        raise ProviderError("model_unavailable", 502, False)
    if not same_model(spec.model, metadata["response_model"]):
        raise ProviderError("model_mismatch", 502, False)
    usage = metadata["usage"] or {}
    for key, limit in [
        ("input_tokens", spec.max_input_tokens),
        ("output_tokens", spec.max_output_tokens),
    ]:
        if usage.get(key) is not None and usage[key] > limit:
            raise ProviderError("token_limit", 502, False)


def same_model(requested, actual):
    return actual == requested or (
        actual.startswith(requested + "-")
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", actual[len(requested) + 1 :]) is not None
    )


def provenance(payload, text, metadata, elapsed):
    return {
        **metadata,
        "elapsed_seconds": elapsed,
        "llm_elapsed_seconds": None,
        "request_sha256": digest(payload),
        "source_sha256": content_hash(text),
        "prompt_sha256": content_hash(payload["input"][0]["content"]),
        "schema_sha256": digest(payload.get("text", {}).get("format", {}).get("schema")),
        "requested_model": payload["model"],
        "request_parameters": {
            "api": "responses",
            "store": False,
            "max_output_tokens": payload["max_output_tokens"],
        },
        "attempt_count": 1,
    }
