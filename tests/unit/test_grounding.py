import pytest
from pydantic import ValidationError

from jobintel.schemas import Evidence, Extraction, Requirement, Years
from jobintel.snapshots import GroundingError, clean_text, content_hash, validate_grounding


def test_exact_unicode_offsets():
    text = "café\nPython is required."
    requirement = Requirement(
        raw_text="Python is required.",
        normalized_skill_or_requirement="Python",
        skills=["Python"],
        requirement_type="MUST",
        category="backend",
        confidence=0.9,
        evidence=Evidence(start=5, end=len(text), quote="Python is required."),
    )
    validate_grounding(text, Extraction(requirements=[requirement]))
    with pytest.raises(GroundingError):
        validate_grounding("x" + text, Extraction(requirements=[requirement]))


def test_raw_wording_cannot_be_rewritten(requirement):
    text = " " * requirement.evidence.start + requirement.evidence.quote
    validate_grounding(text, Extraction(requirements=[requirement]))
    invalid = requirement.model_copy(update={"raw_text": "Invented wording"})
    with pytest.raises(GroundingError, match="raw_text must equal"):
        validate_grounding(text, Extraction(requirements=[invalid]))


def test_missing_evidence_and_extra_fields_rejected(requirement):
    payload = requirement.model_dump()
    del payload["evidence"]
    with pytest.raises(ValidationError):
        Requirement.model_validate(payload)
    with pytest.raises(ValidationError):
        Extraction.model_validate({"requirements": [], "invented_filter": "US"})


def test_invalid_confidence_years_and_groups(requirement):
    with pytest.raises(ValidationError):
        Years(minimum=4, maximum=2)
    for update in [{"confidence": 1.1}, {"operator": "ANY"}, {"skills": ["AWS", "Azure"]}]:
        with pytest.raises(ValidationError):
            Requirement.model_validate({**requirement.model_dump(), **update})


def test_html_cleanup_preserves_actual_content():
    html = "<nav>Menu</nav><main><h1>Engineer</h1><div data-cookie-banner>Cookies</div><p>Python required.</p><script>ignore()</script></main><footer>Links</footer>"
    assert clean_text(html, True) == "Engineer\nPython required."
    assert clean_text(" a\r\n\n b\r") == "a\nb"
    assert content_hash("café") == content_hash("café")
    assert content_hash("Python") != content_hash("python")
