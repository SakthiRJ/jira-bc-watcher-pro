"""Unit tests and a golden-snapshot regression lock for ticket grouping.

The golden snapshot pins the CURRENT (hardcoded) grouping behavior. When the
Phase 5 configurable grouping engine lands, its default policy must reproduce
this exact output.
"""
from __future__ import annotations

import json
from pathlib import Path

from bcwatcher.grouping import build_groups, display_keys
from bcwatcher.jira_client import in_scope

GOLDEN = Path(__file__).parent / "golden" / "grouping_default.json"


def _canonical(groups) -> list[dict]:
    out = []
    for members in groups:
        out.append(
            {
                "members": sorted(m.key for m in members),
                "display_keys": display_keys(members),
            }
        )
    out.sort(key=lambda g: g["members"][0])
    return out


def test_golden_snapshot(sample_issues, projects):
    result = _canonical(build_groups(sample_issues, projects))
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert result == expected


def test_cross_project_link_merges(make_issue, projects):
    issues = {
        i.key: i
        for i in [
            make_issue("CON-1", "CON", linked_keys=["T3-9"]),
            make_issue("T3-9", "T3", "Support"),
        ]
    }
    groups = build_groups(issues, projects)
    assert len(groups) == 1
    assert sorted(m.key for m in groups[0]) == ["CON-1", "T3-9"]


def test_epic_parent_field_rolls_up(make_issue, projects):
    issues = {
        i.key: i
        for i in [
            make_issue("CON-10", "CON", "Epic"),
            make_issue("CON-11", "CON", "Bug", parent_key="CON-10", parent_type="Epic"),
        ]
    }
    groups = build_groups(issues, projects)
    assert len(groups) == 1
    # Sub-ticket is represented by its Epic in the display.
    assert display_keys(groups[0]) == ["CON-10"]


def test_same_project_epic_link_rolls_up(make_issue, projects):
    issues = {
        i.key: i
        for i in [
            make_issue("CON-20", "CON", "Epic"),
            make_issue("CON-21", "CON", "Bug", linked_keys=["CON-20"]),
        ]
    }
    groups = build_groups(issues, projects)
    assert len(groups) == 1
    assert display_keys(groups[0]) == ["CON-20"]


def test_standalone_tickets_stay_separate(make_issue, projects):
    issues = {
        i.key: i
        for i in [
            make_issue("CON-30", "CON"),
            make_issue("CL-31", "CL"),
        ]
    }
    groups = build_groups(issues, projects)
    assert len(groups) == 2


def test_in_scope_filters_out_of_scope_keys():
    keys = ["CON-1", "T3-2", "ZZ-3", "CL-4"]
    assert in_scope(keys, ["CON", "T3", "CL"]) == ["CON-1", "T3-2", "CL-4"]
