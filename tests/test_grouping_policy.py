"""Configurable grouping: policies gate the union edges and the display rollup."""
from __future__ import annotations

from _factories import build_issue

from bcwatcher.grouping import GroupingPolicy, build_groups, display_keys

PROJECTS = ["CON", "T3", "CL"]


class StubTenant:
    def __init__(self, policy: GroupingPolicy, overrides=None):
        self.policy = policy
        self.overrides = overrides or {}

    def grouping_for(self, project):
        return self.overrides.get(project, self.policy)


def _issues():
    lst = [
        build_issue("CON-100", "CON", "Epic", status="In Progress"),
        build_issue("CON-101", "CON", "Bug", linked_keys=["CON-100"]),
        build_issue("T3-200", "T3", "Support", linked_keys=["CON-101"]),
    ]
    return {i.key: i for i in lst}


def test_default_policy_matches_no_tenant():
    without = build_groups(_issues(), PROJECTS)
    with_default = build_groups(_issues(), PROJECTS, StubTenant(GroupingPolicy()))
    assert [[m.key for m in g] for g in without] == [[m.key for m in g] for g in with_default]
    # All three consolidate into one case by default.
    assert len(without) == 1 and len(without[0]) == 3


def test_cross_project_links_off_splits_support():
    tenant = StubTenant(GroupingPolicy(cross_project_links=False))
    groups = build_groups(_issues(), PROJECTS, tenant)
    assert sorted([m.key for g in groups for m in g if len(g) == 1]) == ["T3-200"]
    assert len(groups) == 2


def test_same_project_epic_link_off_splits_epic():
    tenant = StubTenant(GroupingPolicy(same_project_epic_links=False))
    groups = build_groups(_issues(), PROJECTS, tenant)
    keysets = sorted([sorted(m.key for m in g) for g in groups])
    assert keysets == [["CON-100"], ["CON-101", "T3-200"]]


def test_rollup_on_shows_epic_only():
    group = build_groups(_issues(), PROJECTS)[0]
    assert display_keys(group) == ["CON-100", "T3-200"]


def test_rollup_off_shows_subtickets():
    tenant = StubTenant(GroupingPolicy(rollup_subtasks_to_epic=False))
    group = build_groups(_issues(), PROJECTS, tenant)[0]
    assert display_keys(group, tenant) == ["CON-100", "CON-101", "T3-200"]


def test_per_project_override_disables_rollup_for_one_project():
    tenant = StubTenant(
        GroupingPolicy(),
        overrides={"CON": GroupingPolicy(rollup_subtasks_to_epic=False)},
    )
    group = build_groups(_issues(), PROJECTS, tenant)[0]
    assert "CON-101" in display_keys(group, tenant)
