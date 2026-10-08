"""V27-V30: distinct job/group states, predicate identity and unknown slice metadata."""

from copy import deepcopy

import pytest

from jobintel.analytics import corpus_summaries, remote_selected


def row(job="one", state="UNKNOWN", **updates):
    return {
        "job_id": job,
        "match_status": state,
        "normalized_skill_or_requirement": "AWS OR Azure",
        "skills": ["AWS", "Azure"],
        "operator": "ANY",
        "requirement_type": "MUST",
        "category": "cloud",
        "experience_obligation": "UNKNOWN",
        "production_obligation": "UNKNOWN",
        "explicit_production_required": None,
        "years_required": None,
        "version_constraints": [],
        **updates,
    }


def test_v27_v29_duplicate_mentions_do_not_multiply_cluster_or_group_states():
    requirement = row()
    jobs = [
        {"job_id": "one", "extraction": {"requirements": [requirement, requirement]}},
        {"job_id": "empty", "extraction": {"requirements": []}},
    ]
    report = corpus_summaries(jobs, [row(), row(), row(state="MISSING")], 2)
    assert report["clusters"]["clusters"] == [
        {"category": "cloud", "n": 1, "N": 2, "fraction": 0.5, "job_ids": ["one"]}
    ]
    group = report["gaps"]["groups"][0]
    assert group["operator"] == "ANY" and group["skills"] == ["AWS", "Azure"]
    assert group["UNKNOWN"] == group["MISSING"] == 1 and group["COVERED"] == group["PARTIAL"] == 0
    assert len(report["gaps"]["groups"]) == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"operator": "ALL"},
        {"requirement_type": "PREFERRED"},
        {"production_obligation": "MUST"},
        {"years_required": {"minimum": 3, "maximum": None}},
        {"category": "platform"},
        {
            "version_constraints": [
                {"skill": "AWS", "product": "AWS", "comparator": "GTE", "version": "2"}
            ]
        },
    ],
)
def test_v29_group_identity_preserves_typed_predicates(updates):
    result = corpus_summaries([], [row(), row("two", **updates)], 2)
    assert len(result["gaps"]["groups"]) == 2
    assert len({g["group_id"] for g in result["gaps"]["groups"]}) == 2


def test_v29_group_identity_excludes_quote_offsets_but_keeps_version_semantics():
    first = row(
        version_constraints=[
            {
                "skill": "AWS",
                "product": "AWS",
                "comparator": "GTE",
                "version": "2",
                "evidence": {"start": 0},
            }
        ]
    )
    other = deepcopy(first)
    other.update(job_id="two", match_status="COVERED")
    other["version_constraints"][0]["evidence"] = {"start": 80}
    group = corpus_summaries([], [first, other], 2)["gaps"]["groups"]
    assert len(group) == 1 and group[0]["COVERED"] == group[0]["UNKNOWN"] == 1


@pytest.mark.parametrize(
    "mode,selected", [("remote", True), ("hybrid", False), ("onsite", False), (None, None)]
)
def test_v30_remote_filter_excludes_unknown_metadata(mode, selected):
    view = {"extraction": {"work_mode": {"value": mode} if mode else None}}
    assert remote_selected(view, None)
    assert remote_selected(view, True) == (selected is True)
    assert remote_selected(view, False) == (selected is False)
