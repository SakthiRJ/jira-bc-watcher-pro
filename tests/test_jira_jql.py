"""JQL priority clause: single priority vs. a list, with back-compat fallback."""
from __future__ import annotations

from bcwatcher.jira_client import JiraClient


class Ctx:
    jira_base_url = "https://x.atlassian.net"
    jira_email = "e@x.com"
    jira_api_token = "tok"
    projects = ["CON", "T3"]
    priority = "Business Critical"
    closed_lookback_days = 3

    def __init__(self, priorities=None):
        if priorities is not None:
            self.priorities = priorities


def test_single_priority_uses_equals():
    jc = JiraClient(Ctx(["Business Critical"]))
    assert jc._priority_clause() == 'priority = "Business Critical"'


def test_multiple_priorities_uses_in():
    jc = JiraClient(Ctx(["Business Critical", "Critical"]))
    assert jc._priority_clause() == 'priority in ("Business Critical", "Critical")'


def test_falls_back_to_priority_when_no_list():
    ctx = Ctx()  # no `priorities` attribute at all
    jc = JiraClient(ctx)
    assert jc._priority_clause() == 'priority = "Business Critical"'


def test_open_jql_contains_projects_and_priority():
    jc = JiraClient(Ctx(["Business Critical", "Critical"]))
    clause = jc._priority_clause()
    assert clause in 'project in (CON, T3) AND ' + clause + ' AND statusCategory != Done'
