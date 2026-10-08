from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementType(StrEnum):
    MUST = "MUST"
    PREFERRED = "PREFERRED"
    EXPERIENCE = "EXPERIENCE"
    OTHER = "OTHER"


class Evidence(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("evidence end must be greater than start")
        return self


class Years(StrictModel):
    minimum: float = Field(ge=0)
    maximum: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("invalid years range")
        return self


class Requirement(StrictModel):
    raw_text: str = Field(min_length=1)
    normalized_skill_or_requirement: str = Field(min_length=1)
    skills: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    operator: Literal["SINGLE", "ANY", "ALL"] = "SINGLE"
    requirement_type: RequirementType
    category: str = Field(min_length=1)
    evidence: Evidence
    explicit_production_required: bool | None = None
    years_required: Years | None = None
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None

    @model_validator(mode="after")
    def group_shape(self):
        if len(self.skills) != len(set(self.skills)):
            raise ValueError("duplicate group skills")
        if (self.operator == "SINGLE") != (len(self.skills) == 1):
            raise ValueError("SINGLE has one skill; ANY/ALL have at least two")
        return self


class Extraction(StrictModel):
    requirements: list[Requirement]
    responsibilities: list[Evidence] = Field(default_factory=list)
    geography: str | None = None
    work_mode: Literal["remote", "hybrid", "onsite"] | None = None


class JobInput(StrictModel):
    job_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    official_url: str | None = None
    status: str | None = None
    applied: bool | None = None


class ImportInput(StrictModel):
    jobs: list[JobInput] | None = None
    csv_text: str | None = None

    @model_validator(mode="after")
    def one_format(self):
        if (self.jobs is None) == (self.csv_text is None):
            raise ValueError("provide exactly one of jobs or csv_text")
        return self


class SnapshotInput(StrictModel):
    text: str = Field(min_length=1, max_length=200_000)
    source_url: str | None = None
    format: Literal["text", "html"] = "text"


class CandidateEvidence(StrictModel):
    skill: str = Field(min_length=1)
    current_capability: Literal["strong", "basic", "none", "unknown"]
    production_evidence: Literal["confirmed", "limited", "none", "unknown"]
    source: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class CandidateProfile(StrictModel):
    profile_id: str = Field(min_length=1)
    complete: bool = False
    evidence: list[CandidateEvidence]


class ExtractInput(StrictModel):
    configuration: Literal["fixture_raw", "fixture_normalized"] = "fixture_normalized"


class EvaluateInput(StrictModel):
    configurations: list[Literal["fixture_raw", "fixture_normalized"]] = Field(
        default_factory=lambda: ["fixture_raw", "fixture_normalized"], min_length=1
    )
