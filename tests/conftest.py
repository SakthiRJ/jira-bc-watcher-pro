"""Shared pytest fixtures for the BC Watcher test suite."""
from __future__ import annotations

import pytest
from _factories import build_comment, build_issue

from bcwatcher.jira_client import Issue


@pytest.fixture
def make_issue():
    return build_issue


@pytest.fixture
def make_comment():
    return build_comment


@pytest.fixture
def projects() -> list[str]:
    return ["CON", "T3", "CL"]


@pytest.fixture
def sample_issues() -> dict[str, Issue]:
    """A representative cross-section of grouping scenarios.

    - CON-100 Epic with two sub-bugs: CON-101 (same-project issue link) and
      CON-102 (Epic parent field).
    - T3-200 support ticket cross-project linked to CON-101.
    - CL-300 and CON-400 are standalone.
    Expected: {CON-100, CON-101, CON-102, T3-200} form one case that displays as
    the Epic plus the cross-project partner; CL-300 and CON-400 stand alone.
    """
    issues: dict[str, Issue] = {}
    for issue in [
        build_issue("CON-100", "CON", "Epic", status="In Progress"),
        build_issue("CON-101", "CON", "Bug", linked_keys=["CON-100"]),
        build_issue("CON-102", "CON", "Bug", parent_key="CON-100", parent_type="Epic"),
        build_issue("T3-200", "T3", "Support", linked_keys=["CON-101"]),
        build_issue("CL-300", "CL", "Bug"),
        build_issue("CON-400", "CON", "Bug"),
    ]:
        issues[issue.key] = issue
    return issues
