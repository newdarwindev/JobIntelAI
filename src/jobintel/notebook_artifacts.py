"""Hash-bound run envelopes, separate from the unchanged experiment report schema."""

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from jobintel.experiment_corpus import digest, read_json, write_json
from jobintel.notebook_contracts import NotebookRejected
from jobintel.schemas import StrictModel


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Artifact(StrictModel):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=0, strict=True)


class RunManifest(StrictModel):
    format_version: Literal[1] = 1
    mode: Literal["fixture", "saved-report", "local-inference"]
    evidence_mode: Literal["fake", "live", "local-inference", "emulator"]
    status: Literal["planned", "succeeded", "completed_with_failures", "failed", "interrupted"]
    created_at: str
    completed_at: str | None = None
    parameters: dict
    parameters_sha256: str
    input_sha256: str
    code: dict
    reservation: dict
    error_code: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    manifest_sha256: str

    @model_validator(mode="after")
    def identities(self):
        value = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if self.manifest_sha256 != digest(value):
            raise ValueError("run manifest checksum mismatch")
        if self.parameters_sha256 != digest(self.parameters):
            raise ValueError("run parameters checksum mismatch")
        if len({a.path for a in self.artifacts}) != len(self.artifacts):
            raise ValueError("duplicate artifact paths")
        return self


def seal_manifest(value):
    value = {k: v for k, v in value.items() if k != "manifest_sha256"}
    value = {**value, "artifacts": value.get("artifacts", []), "format_version": 1}
    value["manifest_sha256"] = digest(value)
    return RunManifest.model_validate(value)


def collect_artifacts(directory):
    return [
        Artifact(path=name, sha256=file_hash(path), bytes=path.stat().st_size).model_dump()
        for name in ["report.json", "scores.json", "comparison.md"]
        if (path := directory / name).is_file()
    ]


def save_manifest(directory, value):
    manifest = seal_manifest({**value, "artifacts": collect_artifacts(directory)})
    write_json(directory / "manifest.json", manifest.model_dump(mode="json"))
    return manifest


def verify_manifest(path):
    """Verify contents and confinement; this checksum is not a publication approval."""
    path = Path(path).resolve()
    manifest = RunManifest.model_validate(read_json(path))
    for artifact in manifest.artifacts:
        target = (path.parent / artifact.path).resolve()
        if Path(artifact.path).is_absolute() or not target.is_relative_to(path.parent):
            raise NotebookRejected("artifact_path")
        if target.stat().st_size != artifact.bytes or file_hash(target) != artifact.sha256:
            raise NotebookRejected("artifact_checksum")
    return manifest
