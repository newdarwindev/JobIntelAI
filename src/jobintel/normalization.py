import json
from pathlib import Path

from jobintel.schemas import Requirement


class Taxonomy:
    def __init__(self, path: Path):
        self._load(json.loads(path.read_text()))

    @classmethod
    def from_records(cls, records: list[dict]):
        instance = cls.__new__(cls)
        instance._load(records)
        return instance

    def _load(self, records: list[dict]):
        self.records = records
        self.aliases = {}
        for record in self.records:
            for alias in [record["canonical"], *record["aliases"]]:
                key = alias.strip().casefold()
                if key in self.aliases and self.aliases[key] != record["canonical"]:
                    raise ValueError(f"ambiguous taxonomy alias: {alias}")
                self.aliases[key] = record["canonical"]

    def canonical(self, value: str) -> str:
        return self.aliases.get(value.strip().casefold(), value.strip())

    def normalize(self, requirement: Requirement) -> Requirement:
        versions = [
            v.model_copy(
                update={
                    "product": self.canonical(v.product),
                    "skill": v.raw_text.replace(v.source_product, self.canonical(v.product), 1),
                }
            )
            for v in requirement.version_constraints
        ]
        versioned = {
            old.skill: new.skill
            for old, new in zip(requirement.version_constraints, versions, strict=True)
        }
        skills = list(
            dict.fromkeys(versioned.get(s, self.canonical(s)) for s in requirement.skills)
        )
        operator = requirement.operator
        joiner = " OR " if operator == "ANY" else " AND "
        return Requirement.model_validate(
            {
                **requirement.model_dump(),
                "skills": skills,
                "source_skills": requirement.source_skills or requirement.skills,
                "version_constraints": [v.model_dump() for v in versions],
                "operator": operator,
                "normalized_skill_or_requirement": joiner.join(skills),
            }
        )
