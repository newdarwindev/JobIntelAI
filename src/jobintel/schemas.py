from datetime import date
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


SCHEMA_VERSION = 2


class Obligation(StrEnum):
    MUST = "MUST"
    PREFERRED = "PREFERRED"
    UNKNOWN = "UNKNOWN"


class Evidence(StrictModel):
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("evidence end must be greater than start")
        return self


class Years(StrictModel):
    minimum: float = Field(ge=0, allow_inf_nan=False)
    maximum: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("invalid years range")
        return self


class GeographyValue(StrictModel):
    value: str = Field(min_length=1)
    evidence: Evidence


class WorkModeValue(StrictModel):
    value: Literal["remote", "hybrid", "onsite"]
    evidence: Evidence


class FilterValue(StrictModel):
    kind: Literal["work_authorization", "travel", "residency", "attendance"]
    value: str = Field(min_length=1)
    evidence: Evidence


class VersionConstraint(StrictModel):
    skill: str = Field(min_length=1)
    product: str = Field(min_length=1)
    source_product: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)
    comparator: Literal["EQ", "GTE", "GT", "LTE", "LT"]
    version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)*$")
    evidence: Evidence


class Requirement(StrictModel):
    raw_text: str = Field(min_length=1)
    normalized_skill_or_requirement: str = Field(min_length=1)
    skills: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
    operator: Literal["SINGLE", "ANY", "ALL"] = "SINGLE"
    requirement_type: RequirementType
    category: str = Field(min_length=1)
    evidence: Evidence
    experience_obligation: Obligation = Obligation.UNKNOWN
    production_obligation: Obligation = Obligation.UNKNOWN
    explicit_production_required: bool | None = Field(default=None, strict=True)
    years_required: Years | None = None
    version_constraints: list[VersionConstraint] = Field(default_factory=list)
    source_skills: list[Annotated[str, Field(min_length=1)]] | None = Field(
        default=None, min_length=1
    )
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None

    @model_validator(mode="after")
    def group_shape(self):
        if len(self.skills) != len(set(self.skills)):
            raise ValueError("duplicate group skills")
        original = self.source_skills or self.skills
        if (self.operator == "SINGLE") != (len(original) == 1) or (
            self.operator == "SINGLE" and len(self.skills) != 1
        ):
            raise ValueError("SINGLE has one source skill; ANY/ALL have at least two")
        if any(v.skill not in self.skills for v in self.version_constraints):
            raise ValueError("version constraints must reference a skill branch")
        return self


class Extraction(StrictModel):
    schema_version: Literal[2] = SCHEMA_VERSION
    requirements: list[Requirement]
    responsibilities: list[Evidence] = Field(default_factory=list)
    geography: GeographyValue | None = None
    work_mode: WorkModeValue | None = None
    filters: list[FilterValue] | None = None


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
    skill: str = Field(min_length=1, pattern=r"\S")
    current_capability: Literal["strong", "basic", "none", "unknown"]
    production_evidence: Literal["confirmed", "limited", "none", "unknown"]
    source: str = Field(min_length=1, pattern=r"\S")
    quote: str = Field(min_length=1, pattern=r"\S")


class TenureEvidence(StrictModel):
    skill: str = Field(min_length=1, pattern=r"\S")
    kind: Literal["experience", "production"] = "experience"
    status: Literal["confirmed", "none", "unknown"] = "confirmed"
    start: date | None = None
    end: date | None = None
    source: str = Field(min_length=1, pattern=r"\S")
    quote: str = Field(min_length=1, pattern=r"\S")

    @model_validator(mode="after")
    def dates(self):
        if self.start and self.end and self.end <= self.start:
            raise ValueError("tenure end must follow start (end exclusive)")
        if self.status != "confirmed" and (self.start or self.end):
            raise ValueError("only confirmed tenure can carry dates")
        return self


class EligibilityEvidence(StrictModel):
    kind: Literal["location", "work_authorization", "travel", "residency", "attendance"]
    value: str = Field(min_length=1, pattern=r"\S")
    status: Literal["confirmed", "denied", "unknown"]
    observed_on: date
    valid_until: date | None = None
    source: str = Field(min_length=1, pattern=r"\S")
    quote: str = Field(min_length=1, pattern=r"\S")

    @model_validator(mode="after")
    def dates(self):
        if self.valid_until and self.valid_until < self.observed_on:
            raise ValueError("eligibility expiry precedes observation")
        return self


class CandidateProfile(StrictModel):
    profile_id: str = Field(min_length=1, max_length=100, pattern=r"\S")
    complete: bool = Field(default=False, strict=True)
    evidence: list[CandidateEvidence]
    tenure: list[TenureEvidence] = Field(default_factory=list)
    tenure_complete: bool = Field(default=False, strict=True)
    eligibility: list[EligibilityEvidence] = Field(default_factory=list)
    eligibility_complete: list[
        Literal["location", "work_authorization", "travel", "residency", "attendance"]
    ] = Field(default_factory=list)


class MatchSelection(StrictModel):
    profile_id: str = Field(min_length=1, max_length=100)
    profile_revision_id: str = Field(min_length=1, max_length=32)
    expected_run_id: str = Field(min_length=1, max_length=32)
    as_of: date = Field(default_factory=date.today)


class ExtractInput(StrictModel):
    configuration: str | None = Field(default=None, min_length=1, max_length=100)


class EvaluateInput(StrictModel):
    configurations: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = Field(
        default=None, min_length=1
    )
