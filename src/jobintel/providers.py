import json
from pathlib import Path
from typing import Protocol

from jobintel.normalization import Taxonomy
from jobintel.schemas import Extraction
from jobintel.snapshots import content_hash, validate_grounding


class ProviderUnavailable(RuntimeError):
    pass


class ExtractionProvider(Protocol):
    def extract(self, text: str, configuration: str) -> Extraction: ...


class FixtureProvider:
    """Replay synthetic responses by content hash; never infer labels from gold data."""

    def __init__(self, root: Path):
        self.responses = json.loads((root / "provider_responses.json").read_text())
        self.taxonomy = Taxonomy(root / "taxonomy.json")

    def extract(self, text: str, configuration: str) -> Extraction:
        if configuration not in {"fixture_raw", "fixture_normalized"}:
            raise ProviderUnavailable("unknown fixture configuration")
        response = self.responses.get(content_hash(text))
        if response is None:
            raise ProviderUnavailable(
                "fixture provider only supports bundled synthetic snapshots; live extraction is not implemented"
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


class OpenAIProvider:
    """Deliberate boundary: a future adapter must obey the same typed contract."""

    def extract(self, text: str, configuration: str) -> Extraction:
        raise ProviderUnavailable(
            "OpenAI adapter is planned; do not silently substitute fixture responses"
        )
