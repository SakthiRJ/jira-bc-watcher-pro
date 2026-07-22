"""Thin Jira Cloud REST client for the business-critical watcher.

Uses the Atlassian email + API token (HTTP basic auth). Search uses the
current ``/rest/api/3/search/jql`` endpoint; comments are read through the v2
API so bodies come back as plain text instead of ADF JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import requests

from config import Config


@dataclass
class Comment:
    id: str
    author: str
    author_type: str  # "atlassian" for humans, "app" for bots/automation
    created: str  # ISO 8601 string
    body: str

    @property
    def is_human(self) -> bool:
        return self.author_type == "atlassian"


@dataclass
class Issue:
    key: str
    summary: str
    project: str
    status: str
    status_category: str  # "new", "indeterminate", or "done"
    priority: str
    issue_type: str
    assignee: str
    updated: str
    description: str = ""
    linked_keys: list[str] = field(default_factory=list)
    parent_key: str | None = None
    parent_type: str | None = None  # issue type name of the parent, e.g. "Epic"

    @property
    def is_done(self) -> bool:
        return self.status_category == "done"

    @property
    def is_epic(self) -> bool:
        return self.issue_type.lower() == "epic"

    @property
    def has_epic_parent(self) -> bool:
        return bool(self.parent_key) and (self.parent_type or "").lower() == "epic"



def _adf_to_text(node) -> str:
    """Recursively extract plain text from an Atlassian Document Format node."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    t = node.get("type", "")
    if t == "text":
        return node.get("text", "")
    if t in ("hardBreak", "rule"):
        return "\n"
    parts = [_adf_to_text(c) for c in (node.get("content") or [])]
    text = "".join(parts)
    if t in ("paragraph", "heading", "listItem", "bulletList",
             "orderedList", "blockquote", "codeBlock", "panel"):
        text = text.rstrip("\n") + "\n"
    return text

class JiraClient:
    def __init__(self, config: Config):
        self.config = config
        self.base = config.jira_base_url
        self.session = requests.Session()
        self.session.auth = (config.jira_email, config.jira_api_token)
        self.session.headers.update({"Accept": "application/json"})

    # -- low level ----------------------------------------------------------
    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(f"{self.base}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        resp = self.session.post(f"{self.base}{path}", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # -- search -------------------------------------------------------------
    _SEARCH_FIELDS = [
        "summary",
        "status",
        "priority",
        "issuetype",
        "assignee",
        "updated",
        "project",
        "issuelinks",
        "description",
        "parent",
    ]

    def search(self, jql: str, max_pages: int = 20) -> list[Issue]:
        issues: list[Issue] = []
        next_token: str | None = None
        for _ in range(max_pages):
            payload: dict[str, Any] = {
                "jql": jql,
                "maxResults": 100,
                "fields": self._SEARCH_FIELDS,
            }
            if next_token:
                payload["nextPageToken"] = next_token
            data = self._post("/rest/api/3/search/jql", payload)
            for raw in data.get("issues", []):
                issues.append(self._parse_issue(raw))
            next_token = data.get("nextPageToken")
            if not next_token or data.get("isLast"):
                break
        return issues

    def get_issue(self, key: str) -> Issue | None:
        try:
            data = self._get(
                f"/rest/api/3/issue/{key}",
                params={"fields": ",".join(self._SEARCH_FIELDS)},
            )
        except requests.HTTPError:
            return None
        return self._parse_issue(data)

    def business_critical_open(self) -> list[Issue]:
        projects = ", ".join(self.config.projects)
        jql = (
            f'project in ({projects}) AND priority = "{self.config.priority}" '
            f"AND statusCategory != Done ORDER BY updated DESC"
        )
        return self.search(jql)

    def business_critical_recently_closed(self) -> list[Issue]:
        projects = ", ".join(self.config.projects)
        days = self.config.closed_lookback_days
        jql = (
            f'project in ({projects}) AND priority = "{self.config.priority}" '
            f"AND statusCategory = Done AND updated >= -{days}d ORDER BY updated DESC"
        )
        return self.search(jql)

    # -- comments -----------------------------------------------------------
    def get_comments(self, key: str, limit: int = 50) -> list[Comment]:
        """Return the most recent comments (oldest-first) using the v2 API."""
        try:
            data = self._get(
                f"/rest/api/2/issue/{key}/comment",
                params={"orderBy": "-created", "maxResults": limit},
            )
        except requests.HTTPError:
            return []
        comments: list[Comment] = []
        for raw in data.get("comments", []):
            author = raw.get("author") or {}
            comments.append(
                Comment(
                    id=str(raw.get("id")),
                    author=author.get("displayName", "Unknown"),
                    author_type=author.get("accountType", "app"),
                    created=raw.get("created", ""),
                    body=(raw.get("body") or "").strip(),
                )
            )
        comments.sort(key=lambda c: c.created)
        return comments

    # -- parsing ------------------------------------------------------------
    @staticmethod
    def _parse_issue(raw: dict) -> Issue:
        fields = raw.get("fields", {})
        status = fields.get("status") or {}
        status_cat = (status.get("statusCategory") or {}).get("key", "")
        priority = (fields.get("priority") or {}).get("name", "")
        issue_type = (fields.get("issuetype") or {}).get("name", "")
        project = (fields.get("project") or {}).get("key", "")
        assignee_obj = fields.get("assignee") or {}
        assignee = assignee_obj.get("displayName", "Unassigned")

        linked_keys: list[str] = []
        for link in fields.get("issuelinks", []) or []:
            for side in ("inwardIssue", "outwardIssue"):
                linked = link.get(side)
                if linked and linked.get("key"):
                    linked_keys.append(linked["key"])

        parent = fields.get("parent") or {}
        parent_key = parent.get("key")
        parent_type = None
        if parent:
            parent_type = ((parent.get("fields") or {}).get("issuetype") or {}).get("name")

        description = fields.get("description")
        if isinstance(description, dict):  # ADF from v3 - extract plain text
            description = _adf_to_text(description).strip()
        return Issue(
            key=raw.get("key", ""),
            summary=fields.get("summary", ""),
            project=project,
            status=status.get("name", ""),
            status_category=status_cat,
            priority=priority,
            issue_type=issue_type,
            assignee=assignee,
            updated=fields.get("updated", ""),
            description=description or "",
            linked_keys=linked_keys,
            parent_key=parent_key,
            parent_type=parent_type,
        )


def in_scope(keys: Iterable[str], projects: list[str]) -> list[str]:
    """Filter issue keys down to the configured scope projects."""
    prefixes = tuple(f"{p}-" for p in projects)
    return [k for k in keys if k.startswith(prefixes)]
