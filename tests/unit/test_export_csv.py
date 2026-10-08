"""V32: spreadsheet prefixes, control variants and exact JSON/CSV cell boundaries."""

import csv
import io
import json

import pytest

from jobintel.export_selection import ExportInput
from jobintel.exports import csv_text, spreadsheet_cell


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
@pytest.mark.parametrize("leading", ["", " ", "\t", "\r\n", "\x00", "\ufeff", "\u200b", "\x1f \t"])
def test_v32_formula_prefix_after_whitespace_or_control_is_neutralized(prefix, leading):
    value = leading + prefix + 'Authored("comma, quote")'
    assert spreadsheet_cell(value) == "'" + value
    parsed = list(csv.DictReader(io.StringIO(csv_text([{"value": value}], ["value"]))))
    assert parsed == [{"value": "'" + value}]


def test_v32_csv_roundtrip_unicode_delimiters_null_and_nested_fields():
    values = {
        "text": '😀 quoted "field", comma\nnew line\ttab',
        "empty": "",
        "unknown": "UNKNOWN",
        "null": None,
        "number": 0,
        "boolean": False,
        "group": ["AWS", "Azure"],
        "sources": [{"source": "=AUTHORED", "quote": "@Authored"}],
    }
    result = next(csv.DictReader(io.StringIO(csv_text([values], list(values)))))
    assert result["text"] == values["text"]
    assert result["empty"] == result["null"] == ""
    assert result["unknown"] == "UNKNOWN"
    assert result["number"] == "0" and result["boolean"] == "false"
    assert json.loads(result["group"]) == values["group"]
    assert json.loads(result["sources"]) == values["sources"]
    assert csv_text([], ["value"]) == '"value"\r\n'


@pytest.mark.parametrize(
    "payload",
    [
        {"run_ids": ["old"]},
        {"historical": True},
        {"profile_id": "one"},
        {"profile_revision_id": "revision"},
        {"kind": "matches"},
        {"kind": "evidence"},
        {"kind": "requirements", "legacy_skills_csv": True},
        {"format": "pdf"},
        {"unrecognized": "field"},
    ],
)
def test_v31_ambiguous_or_implicit_historical_selections_are_rejected(payload):
    with pytest.raises(ValueError):
        ExportInput(**payload)
