"""Versioned notebook execution inputs; no service or model allocation at import."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from jobintel.experiments import ExperimentSpec
from jobintel.schemas import StrictModel

Sha256 = str


class NotebookRequest(StrictModel):
    format_version: Literal[1] = 1
    mode: Literal["fixture", "saved-report", "local-inference", "training"] = "fixture"
    output: Path
    dataset: Literal["fixture", "reviewed"] = "fixture"
    split: Literal["regression", "development", "test", "train"] = "regression"
    provider: Literal["fixture", "local"] | None = None
    cases: list[str] | None = None
    seed: int = Field(default=42, ge=0, le=2**32 - 1, strict=True)
    spec: ExperimentSpec | None = None
    report: Path | None = None
    endpoint: str | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=600, strict=True)
    max_steps: int | None = Field(default=None, ge=1, strict=True)
    corpus_sha256: Sha256 | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    report_sha256: Sha256 | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    model_weights_sha256: Sha256 | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def coherent(self):
        expected = {"fixture": "fixture", "local-inference": "local"}.get(self.mode)
        if self.provider is not None and self.provider != expected:
            raise ValueError("provider does not match execution mode")
        if (self.report is not None) != (self.mode == "saved-report"):
            raise ValueError("saved-report mode requires exactly one saved report")
        if self.mode != "local-inference" and self.endpoint is not None:
            raise ValueError("endpoint is only accepted for local inference")
        if self.mode != "training" and self.max_steps is not None:
            raise ValueError("training steps are not inference bounds")
        if self.mode != "saved-report" and self.report_sha256 is not None:
            raise ValueError("report hash requires saved-report mode")
        return self


class NotebookRejected(ValueError):
    """Only bounded public codes are exposed, never exception/input contents."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)
