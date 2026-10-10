"""llama.cpp Chat Completions with shared strict validation and exact source grounding."""

import json
import math
from copy import deepcopy

from jobintel.local_model import MODEL, model_identity
from jobintel.openai_provider import OpenAIProvider, parse_extraction, read_usage, string_or_none
from jobintel.openai_transport import ProviderError
from jobintel.provider_config import digest, local_prompt, strict_schema


def source_lines(text):
    lines = []
    start = 0
    for line in text.splitlines(keepends=True):
        quote = line.rstrip("\r\n")
        if quote:
            lines.append({"start": start, "end": start + len(quote), "quote": quote})
        start += len(line)
    return lines


def source_message(text):
    return json.dumps({"posting": text, "lines": source_lines(text)}, ensure_ascii=False)


def source_schema(text):
    """Constrain generation to exact source lines, never rewrite a generated response."""
    schema = strict_schema()
    lines = source_lines(text)
    if not lines or len(lines) > 64:
        raise ProviderError("context_limit", 422, False)
    requirement = schema["$defs"]["Requirement"]
    variants = []
    for line in lines:
        variant = deepcopy(requirement)
        variant["properties"]["raw_text"] = {"const": line["quote"]}
        variant["properties"]["evidence"] = {"const": line}
        variants.append(variant)
    schema["$defs"]["Requirement"] = {"oneOf": variants}
    # Version evidence is a product/version subspan, checked by the shared validator.
    schema["$defs"]["VersionConstraint"]["properties"]["evidence"] = deepcopy(
        schema["$defs"]["Evidence"]
    )
    schema["$defs"]["Evidence"] = {"enum": lines}
    return schema


def chat_text(body):
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ProviderError("invalid_schema", 502, True)
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ProviderError("invalid_schema", 502, True)
    if message.get("refusal") or choice.get("finish_reason") == "content_filter":
        raise ProviderError("refusal", 422, False)
    if choice.get("finish_reason") == "length":
        raise ProviderError("truncated_json", 502, True)
    text = message.get("content")
    if (
        choice.get("finish_reason") != "stop"
        or not isinstance(text, str)
        or message.get("tool_calls")
    ):
        raise ProviderError("invalid_schema", 502, True)
    return text


def engine_seconds(body):
    timings = body.get("timings")
    if not isinstance(timings, dict):
        return None
    values = [timings.get("prompt_ms"), timings.get("predicted_ms")]
    if not all(
        type(value) in {float, int} and math.isfinite(value) and value >= 0 for value in values
    ):
        return None
    return sum(values) / 1000


class LocalProvider(OpenAIProvider):
    name = "local"
    default_configuration = "local_normalized_v1"

    def __init__(self, transport, taxonomy):
        super().__init__(transport, MODEL, taxonomy)

    def request(self, text):
        if len(text) > 6000:
            raise ProviderError("context_limit", 422, False)
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": local_prompt()},
                {"role": "user", "content": source_message(text)},
            ],
            "max_tokens": 2048,
            "temperature": 0,
            "seed": 42,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "job_extraction_v2",
                    "strict": True,
                    "schema": source_schema(text),
                },
            },
        }

    def parse(self, body):
        return parse_extraction(chat_text(body))

    def metadata(self, response):
        body = response.body if response else {}
        usage = body.get("usage")
        return {
            "elapsed_seconds": None,
            "request_id": response.request_id if response else None,
            "response_id": string_or_none(body.get("id")),
            "response_model": string_or_none(body.get("model")),
            "system_fingerprint": string_or_none(body.get("system_fingerprint")),
            "usage": read_usage(
                {
                    "input_tokens": usage.get("prompt_tokens"),
                    "output_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                }
            )
            if isinstance(usage, dict)
            else None,
            "llm_elapsed_seconds": engine_seconds(body),
        }

    def provenance(self, text, configuration, payload, attempts, started):
        provenance = super().provenance(text, configuration, payload, attempts, started)
        provenance.update(model_identity())
        provenance["generation_schema_sha256"] = digest(
            payload["response_format"]["json_schema"]["schema"]
        )
        provenance["system_fingerprint"] = attempts[-1]["system_fingerprint"]
        provenance["request_parameters"] = {
            "api": "chat_completions",
            "max_tokens": 2048,
            "temperature": 0,
            "seed": 42,
            "stream": False,
            "timeout_seconds": getattr(self.transport, "timeout", None),
        }
        values = [attempt["llm_elapsed_seconds"] for attempt in attempts]
        provenance["llm_elapsed_seconds"] = (
            sum(values) if all(v is not None for v in values) else None
        )
        return provenance

    def validate_response(self, body):
        if body.get("model") != MODEL:
            raise ProviderError("model_mismatch", 502, False)
