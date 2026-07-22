"""Plain, importable test factories (shared by conftest fixtures and tests)."""
from __future__ import annotations

from bcwatcher.jira_client import Comment, Issue

OLD_TIME = "2026-07-20T00:00:00.000+0000"
NEW_TIME = "2026-07-22T10:00:00.000+0000"


def build_issue(
    key: str,
    project: str,
    issue_type: str = "Bug",
    *,
    status: str = "Open",
    status_category: str = "indeterminate",
    priority: str = "Business Critical",
    assignee: str = "Alice Dev",
    updated: str = NEW_TIME,
    summary: str | None = None,
    description: str = "",
    linked_keys: list[str] | None = None,
    parent_key: str | None = None,
    parent_type: str | None = None,
) -> Issue:
    return Issue(
        key=key,
        summary=summary or f"{key} summary",
        project=project,
        status=status,
        status_category=status_category,
        priority=priority,
        issue_type=issue_type,
        assignee=assignee,
        updated=updated,
        description=description,
        linked_keys=list(linked_keys or []),
        parent_key=parent_key,
        parent_type=parent_type,
    )


def build_comment(
    cid: str,
    *,
    author: str = "Alice Dev",
    author_type: str = "atlassian",
    created: str = NEW_TIME,
    body: str = "A human update.",
) -> Comment:
    return Comment(id=cid, author=author, author_type=author_type, created=created, body=body)
