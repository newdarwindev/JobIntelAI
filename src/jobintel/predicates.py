"""Conservative source checks for explicit extraction predicates.

These checks admit a documented English evidence grammar. Unsupported or ambiguous
wording must be represented as unknown; this is not a general entailment model.
"""

import re

from jobintel.schemas import Obligation

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
NUMBER = r"(?:\d+(?:\.\d+)?|" + "|".join(NUMBER_WORDS) + ")"
YEARS = re.compile(
    rf"(?P<minimum>{NUMBER})(?:\s*(?:to|\u2013|-)\s*(?P<maximum>{NUMBER}))?"
    r"(?:\s*(?:\+|or more))?\s+years?\s+(?:of|with)\s+.+?experience",
    re.IGNORECASE,
)
AMBIGUOUS = re.compile(r"\b(may|might|could|possibly|perhaps|either|depending|tbd)\b", re.I)
NEGATED = re.compile(r"\b(not|no|neither)\b", re.I)


def obligation(quote: str) -> Obligation:
    text = re.sub(r"\bnot\s+(required|mandatory)\b", "", quote.casefold())
    must = bool(re.search(r"\b(required|must|mandatory)\b", text))
    preferred = bool(re.search(r"\b(preferred|bonus|nice to have|optional)\b", text))
    if AMBIGUOUS.search(text) or must == preferred:
        return Obligation.UNKNOWN
    return Obligation.MUST if must else Obligation.PREFERRED


def number(value: str) -> float:
    return float(NUMBER_WORDS[value]) if value in NUMBER_WORDS else float(value)


def validate_experience(requirement) -> None:
    quote = requirement.evidence.quote
    years = list(YEARS.finditer(quote.casefold()))
    if requirement.years_required is not None:
        expected = (requirement.years_required.minimum, requirement.years_required.maximum)
        ranges = {
            (number(m["minimum"]), number(m["maximum"]) if m["maximum"] else None) for m in years
        }
        if (
            ranges != {expected}
            or AMBIGUOUS.search(quote)
            or re.search(r"\b(up to|less than|under|at most|no more than)\b", quote, re.I)
        ):
            raise ValueError("years predicate is not explicit in requirement evidence")
    if requirement.experience_obligation != Obligation.UNKNOWN:
        statements = [s for s in re.split(r"[.\n]", quote) if "experience" in s.casefold()]
        if not statements or {obligation(s) for s in statements} != {
            requirement.experience_obligation
        }:
            raise ValueError("experience obligation is not explicit in source evidence")
    production = requirement.explicit_production_required
    if production is not None or requirement.production_obligation != Obligation.UNKNOWN:
        statements = [s for s in re.split(r"[.\n]", quote) if "production" in s.casefold()]
        observed = {obligation(s) for s in statements}
        expected = requirement.production_obligation
        if not statements or observed != {expected}:
            raise ValueError("production obligation is not explicit in source evidence")
        if expected != Obligation.UNKNOWN and production != (expected == Obligation.MUST):
            raise ValueError("production preference cannot be a mandatory production predicate")
        if expected == Obligation.UNKNOWN and (
            production is not False or not any("not required" in s.casefold() for s in statements)
        ):
            raise ValueError("unknown production predicate must remain null")


def validate_metadata(extraction) -> None:
    if extraction.geography:
        fact = extraction.geography
        quote = fact.evidence.quote
        cues = r"\b(?:job|role|position|work location|remote work within|onsite in)\b"
        location = rf"(?:\b(?:in|within)\s+|\blocation\s*:\s*){re.escape(fact.value)}(?!\w)"
        if (
            not re.search(rf"(?<!\w){re.escape(fact.value)}(?!\w)", quote, re.I)
            or not re.search(cues, quote, re.I)
            or not re.search(location, quote, re.I)
            or re.search(r"\b(company|headquarters|address|offices?)\b", quote, re.I)
            or AMBIGUOUS.search(quote)
            or NEGATED.search(quote)
            or re.search(r"\b(or|and)\b", quote, re.I)
        ):
            raise ValueError("geography evidence must explicitly describe the job location")
    if extraction.work_mode:
        fact = extraction.work_mode
        quote = fact.evidence.quote.casefold()
        modes = {m for m in ("remote", "hybrid", "onsite") if re.search(rf"\b{m}\b", quote)}
        cues = r"\b(?:job|role|position|work|onsite in)\b"
        if (
            modes != {fact.value}
            or not re.search(cues, quote)
            or AMBIGUOUS.search(quote)
            or NEGATED.search(quote)
        ):
            raise ValueError("work mode evidence must explicitly describe an unambiguous job mode")
        if re.search(r"\b(company|headquarters|address|offices?)\b", quote):
            raise ValueError("company metadata cannot establish the job work mode")
    for fact in extraction.filters or []:
        cues = {
            "work_authorization": r"\bwork authorization\b",
            "travel": r"\btravel\b",
            "residency": r"\b(?:residency|resident|work within)\b",
            "attendance": r"\b(?:onsite|attendance)\b",
        }
        quote = fact.evidence.quote
        if (
            fact.value not in quote
            or not re.search(cues[fact.kind], quote, re.I)
            or AMBIGUOUS.search(quote)
            or re.search(r"\b(company|headquarters|address)\b", quote, re.I)
        ):
            raise ValueError("filter value must be explicit in relevant job evidence")


def validate_versions(requirement) -> None:
    for constraint in requirement.version_constraints:
        if constraint.raw_text != constraint.evidence.quote:
            raise ValueError("version raw wording must equal its source quote")
        source = re.escape(constraint.source_product)
        version = re.escape(constraint.version)
        forms = {
            "EQ": rf"{source}\s+(?:version\s+)?{version}",
            "GTE": rf"(?:{source}\s+(?:>=\s*{version}|{version}\+|{version}\s+or later))",
            "GT": rf"{source}\s+>\s*{version}",
            "LTE": rf"{source}\s+<=\s*{version}",
            "LT": rf"{source}\s+<\s*{version}",
        }
        if not re.fullmatch(forms[constraint.comparator], constraint.raw_text, re.I):
            raise ValueError("version comparator/product must match explicit source wording")
        if constraint.skill != constraint.raw_text.replace(
            constraint.source_product, constraint.product, 1
        ):
            raise ValueError("version constraint must retain its skill branch")
        if not (
            requirement.evidence.start <= constraint.evidence.start
            and constraint.evidence.end <= requirement.evidence.end
        ):
            raise ValueError("version evidence must belong to the requirement quote")
    for match in re.finditer(r"\b\d+\.\d+(?:\.\d+)*(?:\+)?", requirement.raw_text):
        if re.match(r"\s+years?\b", requirement.raw_text[match.end() :]):
            continue
        start = requirement.evidence.start + match.start()
        end = requirement.evidence.start + match.end()
        if not any(
            v.evidence.start <= start and end <= v.evidence.end
            for v in requirement.version_constraints
        ):
            raise ValueError("explicit source versions require structured constraints")
