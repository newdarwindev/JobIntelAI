import hashlib

from bs4 import BeautifulSoup

from jobintel.schemas import Extraction


class GroundingError(ValueError):
    pass


def clean_text(text: str, is_html: bool = False) -> str:
    if is_html:
        soup = BeautifulSoup(text, "html.parser")
        for element in soup.select(
            "script, style, nav, header, footer, form, [data-cookie-banner]"
        ):
            element.decompose()
        container = soup.select_one("main") or soup.select_one("article") or soup
        text = container.get_text(separator="\n")
    # Character offsets refer exclusively to this final Unicode string, never raw HTML.
    return "\n".join(
        line.strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
        if line.strip()
    )


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_grounding(text: str, extraction: Extraction) -> None:
    for evidence in [r.evidence for r in extraction.requirements] + extraction.responsibilities:
        if evidence.end > len(text) or text[evidence.start : evidence.end] != evidence.quote:
            raise GroundingError("evidence must exactly match the clean snapshot at [start:end]")
    for requirement in extraction.requirements:
        if requirement.raw_text != requirement.evidence.quote:
            raise GroundingError("raw_text must equal the quoted source wording")
    # Span validity is necessary, but does not prove semantic entailment. Golden review
    # must still catch misleading quotes, invented years and incorrect classifications.
