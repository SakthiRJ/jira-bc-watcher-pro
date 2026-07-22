"""Consolidate related tickets into a single logical case.

Three things get merged into one case:
  1. Cross-project links (a T3 support ticket linked to its CON/CL ticket).
  2. Epic parent field (a sub-ticket whose Jira parent field points to an Epic).
  3. Same-project Epic links (a CON bug that is issue-linked to a CON Epic -
     this Jira instance uses issue links rather than the parent field to tie
     CON sub-tickets to their Epic).

For display we then roll CON sub-tickets up to their Epic, so a case that spans
several sibling CON tickets is shown as the single Epic key (plus any linked
T3/CL ticket), never as a long list of sub-tickets.
"""
from __future__ import annotations

from dataclasses import dataclass

from bcwatcher.jira_client import Issue, in_scope


@dataclass(frozen=True)
class GroupingPolicy:
    """How tickets are consolidated into one case. Defaults reproduce the
    original hardcoded behavior, so an unset policy is a no-op.

    Per-project overrides let different companies express their own linking
    conventions (e.g. one Jira uses the Epic parent field, another uses issue
    links to tie sub-tickets to their Epic).
    """

    cross_project_links: bool = True
    epic_parent_field: bool = True
    same_project_epic_links: bool = True
    rollup_subtasks_to_epic: bool = True

    @classmethod
    def from_dict(cls, data: dict | None) -> "GroupingPolicy":
        data = data or {}
        return cls(
            cross_project_links=bool(data.get("cross_project_links", True)),
            epic_parent_field=bool(data.get("epic_parent_field", True)),
            same_project_epic_links=bool(data.get("same_project_epic_links", True)),
            rollup_subtasks_to_epic=bool(data.get("rollup_subtasks_to_epic", True)),
        )


DEFAULT_POLICY = GroupingPolicy()


def _policy_for(tenant, project: str) -> GroupingPolicy:
    """Resolve the grouping policy for a project (tenant may override per project)."""
    if tenant is None:
        return DEFAULT_POLICY
    return tenant.grouping_for(project)


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, key: str) -> None:
        self.parent.setdefault(key, key)

    def find(self, key: str) -> str:
        self.add(key)
        root = key
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[key] != root:
            self.parent[key], key = root, self.parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_groups(issues: dict[str, Issue], projects: list[str], tenant=None) -> list[list[Issue]]:
    """Group issues into cases using the (optionally per-project) grouping policy.

    ``tenant`` is any object exposing ``grouping_for(project) -> GroupingPolicy``;
    when omitted, the default policy (original behavior) applies to every project.
    """
    uf = _UnionFind()
    for key in issues:
        uf.add(key)
    for key, issue in issues.items():
        policy = _policy_for(tenant, issue.project)
        # Cross-project links (T3 <-> CON/CL)
        if policy.cross_project_links:
            for linked in in_scope(issue.linked_keys, projects):
                partner = issues.get(linked)
                if partner is not None and partner.project != issue.project:
                    uf.union(key, linked)
        # Epic membership via the Jira parent field
        if policy.epic_parent_field and issue.has_epic_parent and issue.parent_key in issues:
            uf.union(key, issue.parent_key)
        # Same-project Epic membership expressed via an issue link (this Jira
        # uses issue links instead of the parent field for CON sub-tickets).
        if policy.same_project_epic_links and not issue.is_epic:
            for linked in in_scope(issue.linked_keys, projects):
                epic = issues.get(linked)
                if epic is not None and epic.is_epic and epic.project == issue.project:
                    uf.union(key, linked)

    groups: dict[str, list[Issue]] = {}
    for key, issue in issues.items():
        root = uf.find(key)
        groups.setdefault(root, []).append(issue)

    result = []
    for members in groups.values():
        members.sort(key=lambda i: i.key)
        result.append(members)
    result.sort(key=lambda g: g[0].key)
    return result


def display_keys(members: list[Issue], tenant=None) -> list[str]:
    """Roll CON sub-tickets up to their Epic key for display.

    A ticket is suppressed (represented by its Epic instead) when:
      * its Jira parent field points to an Epic that is in the same case, OR
      * it is issue-linked to an Epic in the same case AND lives in the same
        project (this Jira uses issue links to tie CON bugs to their CON Epic).

    Epics themselves and cross-project partners (T3, CL) are shown as-is.
    The result is that a multi-bug CON Epic case shows as just the Epic key
    (e.g. CON-2004) plus any linked T3 support ticket - never a long list of
    CON sub-tickets.
    """
    epic_keys = {m.key for m in members if m.is_epic}

    def _rolls_up(m: Issue) -> bool:
        if m.is_epic:
            return False
        if not _policy_for(tenant, m.project).rollup_subtasks_to_epic:
            return False
        # Parent-field membership
        if m.has_epic_parent and m.parent_key in epic_keys:
            return True
        # Same-project issue-link membership
        return any(
            linked in epic_keys and (members_by_key.get(linked) or _dummy(linked)).project == m.project
            for linked in m.linked_keys
        )

    members_by_key: dict[str, Issue] = {m.key: m for m in members}

    def _dummy(key: str) -> Issue:
        # Fallback: if the Epic is not in our dict (shouldn't happen), use the
        # key prefix as a project approximation so we don't suppress incorrectly.
        from bcwatcher.jira_client import Issue as _I
        proj = key.split("-")[0] if "-" in key else ""
        return _I(key=key, summary="", project=proj, status="", status_category="",
                  priority="", issue_type="Epic", assignee="", updated="")

    keys: list[str] = []
    seen: set[str] = set()

    def _add(k: str) -> None:
        if k and k not in seen:
            seen.add(k)
            keys.append(k)

    for m in members:
        if _rolls_up(m):
            continue  # represented by its Epic
        _add(m.key)

    return sorted(keys)
