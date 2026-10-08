import hashlib

from bs4 import BeautifulSoup

from jobintel.predicates import validate_experience, validate_metadata, validate_versions
from jobintel.schemas import Extraction


class GroundingError(ValueError):
    pass


def clean_text(text: str, is_html: bool = False) -> str:
    if is_html:
        soup = BeautifulSoup(text, "html.parser")
        for element in soup.select(
            "script, style, title, nav, header, footer, form, noscript, [data-cookie-banner], "
            "[role='navigation'], [role='banner'], .cookie-banner, #cookie-banner"
        ):
            element.decompose()
        container = (
            soup.select_one("main")
            or soup.select_one("article")
            or soup.select_one(
                "#job-description, .job-description, #jobDescriptionText, "
                "[data-automation-id='jobPostingDescription'], [itemprop='description']"
            )
            or soup
        )
        for element in container.find_all("br"):
            element.replace_with("\n")
        for element in container.find_all(
            [
                "p",
                "div",
                "section",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "li",
                "tr",
                "table",
                "ul",
                "ol",
            ]
        ):
            element.insert_before("\n")
            element.insert_after("\n")
        for element in container.find_all(["td", "th"]):
            element.append(" ")
        text = container.get_text(separator="")
    # Character offsets refer exclusively to this final Unicode string, never raw HTML.
    return "\n".join(
        line.strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
        if line.strip()
    )


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_grounding(text: str, extraction: Extraction) -> None:
    metadata = [f for f in [extraction.geography, extraction.work_mode] if f is not None]
    evidence_items = (
        [r.evidence for r in extraction.requirements]
        + extraction.responsibilities
        + [f.evidence for f in metadata + (extraction.filters or [])]
        + [v.evidence for r in extraction.requirements for v in r.version_constraints]
    )
    for evidence in evidence_items:
        if evidence.end > len(text) or text[evidence.start : evidence.end] != evidence.quote:
            raise GroundingError("evidence must exactly match the clean snapshot at [start:end]")
    for requirement in extraction.requirements:
        if requirement.raw_text != requirement.evidence.quote:
            raise GroundingError("raw_text must equal the quoted source wording")
    try:
        validate_metadata(extraction)
        for requirement in extraction.requirements:
            validate_experience(requirement)
            validate_versions(requirement)
    except ValueError as error:
        raise GroundingError(str(error)) from error
    # Span validity is necessary, but does not prove semantic entailment. Golden review
    # must still catch misleading quotes, invented years and incorrect classifications.
