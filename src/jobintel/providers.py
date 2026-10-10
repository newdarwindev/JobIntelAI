import json
import os
from pathlib import Path
from typing import Protocol

from jobintel.config import openai_key
from jobintel.normalization import Taxonomy
from jobintel.openai_provider import OpenAIProvider, ProviderResult
from jobintel.openai_transport import EMULATOR_TOKEN, HttpOpenAITransport
from jobintel.provider_config import configuration_for, identity
from jobintel.schemas import Extraction
from jobintel.snapshots import content_hash, validate_grounding


class ProviderUnavailable(RuntimeError):
    pass


class ExtractionProvider(Protocol):
    def extract(self, text: str, configuration: str) -> Extraction | ProviderResult: ...


class FixtureProvider:
    """Replay synthetic responses by content hash; never infer labels from gold data."""

    name = "fixture"
    default_configuration = "fixture_normalized"

    def __init__(self, root: Path):
        self.responses = json.loads((root / "provider_responses.json").read_text())
        self.taxonomy = Taxonomy(root / "taxonomy.json")

    def extract(self, text: str, configuration: str) -> Extraction:
        configuration_for(configuration, self.name)
        response = self.responses.get(content_hash(text))
        if response is None:
            raise ProviderUnavailable(
                "fixture provider only supports bundled synthetic snapshots; explicitly select OpenAI for other inputs"
            )
        if response.get("schema_version") != 2:
            raise ValueError("fixture responses require extraction schema v2")
        result = Extraction.model_validate(response)
        validate_grounding(text, result)
        if configuration == "fixture_normalized":
            result = result.model_copy(
                update={"requirements": [self.taxonomy.normalize(r) for r in result.requirements]}
            )
        return result


def extract_result(provider, text, configuration):
    result = provider.extract(text, configuration)
    if isinstance(result, ProviderResult):
        return result
    provenance = None
    if isinstance(provider, FixtureProvider):
        provenance = {
            **identity("fixture", configuration, None, provider.taxonomy),
            "source_sha256": content_hash(text),
            "response_model": None,
            "request_id": None,
            "response_id": None,
            "attempt_count": 0,
            "attempts": [],
            "usage": None,
            "elapsed_seconds": None,
            "llm_elapsed_seconds": None,
            "estimated_cost": None,
        }
    return ProviderResult(result, provenance)


def selected_provider(root, name=None, *, transport=None, model=None):
    name = name or os.getenv("JOBINTEL_PROVIDER", "fixture")
    if name == "fixture":
        return FixtureProvider(root)
    if name != "openai":
        raise ValueError("unknown provider; choose fixture or openai")
    model = model or os.getenv("JOBINTEL_OPENAI_MODEL")
    if not model or not model.strip():
        raise ValueError("JOBINTEL_OPENAI_MODEL is required for OpenAI")
    if transport is None:
        mode = os.getenv("JOBINTEL_RESPONSES_MODE", "hosted")
        key = EMULATOR_TOKEN if mode == "emulator" else openai_key()
        try:
            timeout = float(os.getenv("JOBINTEL_OPENAI_TIMEOUT", "30"))
        except ValueError as error:
            raise ValueError("OpenAI timeout must be between 1 and 120 seconds") from error
        if not 1 <= timeout <= 120:
            raise ValueError("OpenAI timeout must be between 1 and 120 seconds")
        transport = HttpOpenAITransport(
            key, timeout, mode=mode, endpoint=os.getenv("JOBINTEL_RESPONSES_ENDPOINT")
        )
    return OpenAIProvider(transport, model, Taxonomy(root / "taxonomy.json"))


def selected_configuration(provider, configuration=None):
    name = configuration or os.getenv("JOBINTEL_CONFIGURATION") or provider.default_configuration
    configuration_for(name, provider.name)
    return name
