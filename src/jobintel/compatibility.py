"""Read legacy extraction JSON without rewriting immutable historical runs."""

from copy import deepcopy

from jobintel.schemas import Extraction, Requirement


def stored_extraction(payload: dict) -> Extraction:
    version = payload.get("schema_version", 1)
    if version == 2:
        return Extraction.model_validate(payload)
    if version != 1:
        raise ValueError("unsupported stored extraction schema")
    result = deepcopy(payload)
    result["schema_version"] = 2
    # Legacy scalar metadata has no evidence and cannot become a sourced claim.
    result["geography"] = None
    result["work_mode"] = None
    result["filters"] = None
    result["requirements"] = [
        stored_requirement(r, version).model_dump(mode="json") for r in result["requirements"]
    ]
    return Extraction.model_validate(result)


def stored_requirement(payload: dict, version: int) -> Requirement:
    if version == 2:
        return Requirement.model_validate(payload)
    if version != 1:
        raise ValueError("unsupported stored requirement schema")
    result = deepcopy(payload)
    # v1 did not distinguish preferred from mandatory production experience.
    result["explicit_production_required"] = None
    result["experience_obligation"] = "UNKNOWN"
    result["production_obligation"] = "UNKNOWN"
    result["version_constraints"] = []
    result["source_skills"] = None
    return Requirement.model_validate(result)
