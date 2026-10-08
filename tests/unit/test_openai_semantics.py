"""V13/V14/V19: independently authored semantic contracts via fake transport.

These exercise preservation, grounding and prompt isolation; live semantic quality
requires separately authorized reviewed experiments.
"""

import json
from pathlib import Path

import pytest

from jobintel.openai_provider import OpenAIProvider
from jobintel.schemas import Evidence, Extraction, Requirement
from tests.provider_fakes import FakeTransport, response

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures/openai_semantics.json").read_text()
)


def evidence(text, quote):
    start = text.index(quote)
    return Evidence(start=start, end=start + len(quote), quote=quote)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_v13_v14_preserve_semantics_and_untrusted_source(case, taxonomy):
    text = case["text"]
    requirements = []
    for item in case["requirements"]:
        requirements.append(
            Requirement(
                raw_text=item["quote"],
                normalized_skill_or_requirement=" / ".join(item["skills"]),
                skills=item["skills"],
                operator=item["operator"],
                requirement_type=item["type"],
                category="backend",
                evidence=evidence(text, item["quote"]),
                confidence=1,
                production_obligation=item.get("production_obligation", "UNKNOWN"),
                experience_obligation=item.get("experience_obligation", "UNKNOWN"),
                explicit_production_required=item.get("explicit_production_required"),
            )
        )
    expected = Extraction(
        requirements=requirements,
        responsibilities=[evidence(text, quote) for quote in case["responsibilities"]],
    )
    transport = FakeTransport(response(expected.model_dump(mode="json")))
    actual = (
        OpenAIProvider(transport, "synthetic", taxonomy)
        .extract(text, "openai_structured_v1")
        .extraction
    )
    assert actual == expected
    assert actual.geography is actual.work_mode is actual.filters is None
    assert all(r.years_required is None for r in actual.requirements)
    assert [r.operator for r in actual.requirements] == [
        r["operator"] for r in case["requirements"]
    ]
    assert [r.requirement_type for r in actual.requirements] == [
        r["type"] for r in case["requirements"]
    ]
    assert not any("Java" in r.skills or "Rust" in r.skills for r in actual.requirements)
    request = transport.requests[0]
    assert request["input"][1] == {"role": "user", "content": text}
    assert "SYSTEM: ignore" not in request["input"][0]["content"]
    if case["id"] != "production-preference":
        assert all(r.explicit_production_required is None for r in actual.requirements)
