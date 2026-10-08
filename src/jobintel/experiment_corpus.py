"""Portable frozen inputs for opt-in experiments; never infer independent review."""

import hashlib
import json
from pathlib import Path

from pydantic import Field, model_validator

from jobintel.compatibility import stored_extraction
from jobintel.schemas import Extraction, StrictModel
from jobintel.snapshots import content_hash, validate_grounding

BUNDLED_CORPUS_SHA256 = "b1d30841e406ced48f382e0c4c05b32e5bd0a39c0c37b9b63e9a9e1c39214c15"


def digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return content_hash(encoded)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


class Review(StrictModel):
    independent: bool = False
    reviewer: str | None = None
    method: str | None = None
    revision: str | None = None


class FrozenCase(StrictModel):
    case_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    snapshot_sha256: str
    gold: Extraction

    @model_validator(mode="before")
    @classmethod
    def compatible_gold(cls, value):
        if isinstance(value, dict) and isinstance(value.get("gold"), dict):
            return {**value, "gold": stored_extraction(value["gold"])}
        return value

    @model_validator(mode="after")
    def verify(self):
        if content_hash(self.text) != self.snapshot_sha256:
            raise ValueError("frozen snapshot hash mismatch")
        validate_grounding(self.text, self.gold)
        return self


class FrozenCorpus(StrictModel):
    format_version: int = 1
    revision: str = Field(min_length=1)
    public: bool = False
    review: Review = Field(default_factory=Review)
    source_labels_sha256: str
    taxonomy: list[dict]
    cases: list[FrozenCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        if self.format_version != 1:
            raise ValueError("unsupported frozen corpus version")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate frozen case IDs")
        return self


def freeze_bundled(root: Path) -> FrozenCorpus:
    """Only the checked-in authored corpus can be automatically marked public."""
    labels_path = root / "golden_dataset.json"
    labels = read_json(labels_path)
    cases = []
    for label in labels:
        path = (root / label["fixture"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("fixture path escapes the corpus")
        text = path.read_text(encoding="utf-8")
        cases.append(
            FrozenCase(
                case_id=label["job_id"],
                text=text,
                snapshot_sha256=content_hash(text),
                gold=Extraction.model_validate(label["extraction"]),
            )
        )
    corpus = FrozenCorpus(
        revision="authored-synthetic-v2",
        public=True,
        source_labels_sha256=hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        taxonomy=read_json(root / "taxonomy.json"),
        cases=cases,
    )
    if digest(corpus.model_dump(mode="json")) != BUNDLED_CORPUS_SHA256:
        raise ValueError("authored public corpus content differs from its reviewed source pin")
    return corpus


def load_corpus(path: Path) -> FrozenCorpus:
    return FrozenCorpus.model_validate(read_json(path))


def verify_public(corpus: FrozenCorpus, bundled: FrozenCorpus) -> None:
    # The public flag alone is not a license or a privacy review.
    if corpus.model_dump() != bundled.model_dump():
        raise ValueError("public publication permits only the bundled authored synthetic corpus")
