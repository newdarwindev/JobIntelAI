"""Frozen source-reviewed annotations, separate from replay/model predictions."""

from datetime import date
from pathlib import Path

from pydantic import Field, model_validator

from jobintel.experiment_corpus import FrozenCase, Review, digest, read_json
from jobintel.schemas import CandidateProfile, StrictModel
from jobintel.snapshots import content_hash

REVIEWED_CORPUS_SHA256 = "63356ace397e0034d86b207259cbea21ee0a0de870c161fb9a2561d7a328e329"


class ReviewedCase(FrozenCase):
    rationale: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    expected_matches: list[str]
    expected_filter_matches: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def match_labels(self):
        states = {"COVERED", "PARTIAL", "MISSING", "UNKNOWN"}
        if len(self.expected_matches) != len(self.gold.requirements):
            raise ValueError("matching labels must align to reviewed requirements")
        filters = len(self.gold.filters or []) + (self.gold.geography is not None)
        if len(self.expected_filter_matches) != filters:
            raise ValueError("matching labels must align to reviewed filters")
        if not set(self.expected_matches + self.expected_filter_matches) <= states:
            raise ValueError("invalid matching label")
        return self


class ReviewedCorpus(StrictModel):
    format_version: int = 1
    revision: str = Field(min_length=1)
    license: str = Field(min_length=1)
    review: Review
    taxonomy_sha256: str
    as_of: date
    candidate: CandidateProfile
    cases: list[ReviewedCase] = Field(min_length=20, max_length=30)

    @model_validator(mode="after")
    def reviewed(self):
        if self.format_version != 1:
            raise ValueError("unsupported reviewed corpus version")
        review = self.review
        if not (review.independent and review.reviewer and review.method and review.revision):
            raise ValueError("source review requires reviewer, method and revision")
        if len({c.case_id for c in self.cases}) != len(self.cases):
            raise ValueError("duplicate reviewed case IDs")
        return self


def load_reviewed(root: Path) -> ReviewedCorpus:
    path = root / "evaluation/reviewed-v1.json"
    if content_hash(path.read_text(encoding="utf-8")) != REVIEWED_CORPUS_SHA256:
        raise ValueError("frozen reviewed corpus differs from its source pin")
    corpus = ReviewedCorpus.model_validate(read_json(path))
    if corpus.taxonomy_sha256 != digest(read_json(root / "taxonomy.json")):
        raise ValueError("reviewed taxonomy hash mismatch")
    return corpus
