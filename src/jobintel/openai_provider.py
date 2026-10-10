"""Schema-constrained extraction with local validation and per-call provenance."""

import json
from dataclasses import dataclass
from time import perf_counter

from pydantic import ValidationError

from jobintel.normalization import Taxonomy
from jobintel.openai_transport import OpenAITransport, ProviderError
from jobintel.provider_config import PROMPT, configuration_for, digest, identity, strict_schema
from jobintel.provider_execution import execution_mode
from jobintel.schemas import Extraction
from jobintel.snapshots import GroundingError, content_hash, validate_grounding


@dataclass(frozen=True)
class ProviderResult:
    extraction: Extraction
    provenance: dict | None


class OpenAIProvider:
    name = "openai"
    default_configuration = "openai_normalized_v1"

    def __init__(self, transport: OpenAITransport, model: str, taxonomy: Taxonomy):
        if not model or not model.strip():
            raise ValueError("OpenAI requires an explicit model")
        self.transport = transport
        self.model = model
        self._taxonomy = taxonomy

    def extract(self, text: str, configuration: str) -> ProviderResult:
        policy = configuration_for(configuration, self.name)
        payload = self.request(text)
        started = perf_counter()
        attempts = []
        for attempt in range(2):
            attempts.append(self.metadata(None))
            attempt_started = perf_counter()
            try:
                response = self.transport.complete(payload)
                attempts[-1] = self.metadata(response)
                if execution_mode(self) == "emulator":
                    attempts[-1]["usage"] = None
                attempts[-1]["elapsed_seconds"] = perf_counter() - attempt_started
                self.validate_response(response.body)
                extraction = self.parse(response.body)
                break
            except ProviderError as error:
                attempts[-1]["elapsed_seconds"] = perf_counter() - attempt_started
                error.provenance = self.provenance(text, configuration, payload, attempts, started)
                if error.code not in {"malformed_json", "invalid_schema", "truncated_json"}:
                    raise
                if attempt == 1:
                    final_error = ProviderError(error.code, error.status, False)
                    final_error.provenance = error.provenance
                    raise final_error from error
                # Repeat the original schema request once. Never echo untrusted model output.
        try:
            validate_grounding(text, extraction)
        except GroundingError as error:
            provider_error = ProviderError("invalid_evidence", 422, False)
            provider_error.provenance = self.provenance(
                text, configuration, payload, attempts, started
            )
            raise provider_error from error
        if policy.normalize:
            extraction = extraction.model_copy(
                update={
                    "requirements": [self._taxonomy.normalize(r) for r in extraction.requirements]
                }
            )
        return ProviderResult(
            extraction, self.provenance(text, configuration, payload, attempts, started)
        )

    def provenance(self, text, configuration, payload, attempts, started):
        return {
            **identity(self.name, configuration, self.model, self._taxonomy),
            "execution_mode": execution_mode(self),
            "source_sha256": content_hash(text),
            "request_sha256": digest(payload),
            "request_parameters": {
                "api": "responses",
                "max_output_tokens": 8192,
                "store": False,
                "timeout_seconds": getattr(self.transport, "timeout", None),
            },
            "response_model": attempts[-1]["response_model"],
            "request_id": attempts[-1]["request_id"],
            "response_id": attempts[-1]["response_id"],
            "attempts": attempts,
            "attempt_count": len(attempts),
            "usage": total_usage(attempts),
            "elapsed_seconds": perf_counter() - started,
            "llm_elapsed_seconds": None,
            "estimated_cost": None,
        }

    def validate_response(self, body):
        pass

    def parse(self, body):
        return parse_response(body)

    def metadata(self, response):
        return response_metadata(response)

    def request(self, text):
        return {
            "model": self.model,
            "store": False,
            "max_output_tokens": 8192,
            "input": [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": text},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "job_extraction_v2",
                    "strict": True,
                    "schema": strict_schema(),
                }
            },
        }


def response_text(body):
    try:
        contents = [part for item in body.get("output", []) for part in item.get("content", [])]
        if any(part.get("type") == "refusal" for part in contents):
            raise ProviderError("refusal", 422, False)
        if body.get("status") == "incomplete":
            raise ProviderError("truncated_json", 502, True)
        if body.get("status") != "completed":
            raise ProviderError("provider_failure", 502, True)
        parts = [part["text"] for part in contents if part.get("type") == "output_text"]
        if len(parts) != 1 or not isinstance(parts[0], str):
            raise ProviderError("invalid_schema", 502, True)
        return parts[0]
    except (AttributeError, KeyError, TypeError) as error:
        raise ProviderError("invalid_schema", 502, True) from error


def parse_response(body):
    return parse_extraction(response_text(body))


def parse_extraction(text):
    try:
        payload = json.loads(text)
    except (ValueError, UnicodeError) as error:
        raise ProviderError("malformed_json", 502, True) from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise ProviderError("invalid_schema", 502, True)
    try:
        return Extraction.model_validate_json(json.dumps(payload), strict=True)
    except ValidationError as error:
        raise ProviderError("invalid_schema", 502, True) from error


def response_metadata(response):
    body = response.body if response else {}
    return {
        "elapsed_seconds": None,
        "request_id": response.request_id if response else None,
        "response_id": string_or_none(body.get("id")),
        "response_model": string_or_none(body.get("model")),
        "usage": read_usage(body.get("usage")),
    }


def string_or_none(value):
    return value if isinstance(value, str) else None


def read_usage(value):
    if not isinstance(value, dict):
        return None
    fields = ["input_tokens", "output_tokens", "total_tokens"]
    return {k: v if type(v := value.get(k)) is int and v >= 0 else None for k in fields}


def total_usage(attempts):
    if not attempts or any(a["usage"] is None for a in attempts):
        return None
    return {
        key: None
        if any(a["usage"][key] is None for a in attempts)
        else sum(a["usage"][key] for a in attempts)
        for key in ["input_tokens", "output_tokens", "total_tokens"]
    }
