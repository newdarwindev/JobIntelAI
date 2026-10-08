"""V09-V11: authored ATS/table/list markup retains requirement clauses."""

import json
from pathlib import Path

import pytest

from jobintel.snapshots import clean_text

CASES = json.loads((Path(__file__).parents[1] / "fixtures/acquisition_cleaning.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_v09_cleaning_retains_authored_clauses_and_discards_navigation(case):
    cleaned = clean_text(case["html"], True)
    assert all(clause in cleaned for clause in case["clauses"])
    assert all(value not in cleaned for value in case["excluded"])
    assert clean_text(cleaned) == cleaned
