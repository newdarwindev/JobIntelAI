"""Explicit current/historical selection shared by API, CLI and browser exports."""

from typing import Literal

from pydantic import Field, model_validator

from jobintel.schemas import StrictModel


class ExportInput(StrictModel):
    kind: Literal["skills", "requirements", "matches", "evidence"] = "skills"
    format: Literal["json", "csv"] = "json"
    historical: bool = False
    applied: bool | None = None
    remote: bool | None = None
    job_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    match_run_ids: list[str] = Field(default_factory=list)
    profile_id: str | None = None
    profile_revision_id: str | None = None
    legacy_skills_csv: bool = False

    @model_validator(mode="after")
    def explicit_selection(self):
        if (self.profile_id is None) != (self.profile_revision_id is None):
            raise ValueError("select both profile_id and profile_revision_id")
        if self.historical != bool(self.run_ids or self.match_run_ids):
            raise ValueError("historical exports require explicit run_ids or match_run_ids")
        if self.kind == "matches" and not (self.profile_revision_id or self.match_run_ids):
            raise ValueError("match exports require an explicit candidate revision or match run")
        if self.kind == "evidence" and len(self.job_ids) != 1:
            raise ValueError("evidence exports require exactly one job_id")
        if self.legacy_skills_csv and self.kind != "skills":
            raise ValueError("legacy_skills_csv applies only to skills")
        return self
