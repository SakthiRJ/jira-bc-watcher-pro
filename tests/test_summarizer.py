"""Summarizer tests: verify the extract -> validate -> render contract holds
regardless of what the (fake) provider returns."""
from __future__ import annotations

import pytest
from _factories import build_comment, build_issue

from bcwatcher.config import Config
from bcwatcher.llm import LLMError
from bcwatcher.summarizer import Summarizer


class FakeProvider:
    def __init__(self, payload=None, exc=None):
        self.payload = payload
        self.exc = exc
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.payload


def _group():
    primary = build_issue("CON-2004", "CON", "Bug", status="In Progress")
    linked = build_issue("T3-1412", "T3", "Support")
    return primary, [primary, linked]


def _summarizer(payload=None, exc=None):
    return Summarizer(Config(), provider=FakeProvider(payload=payload, exc=exc))


def test_status_returns_clean_grounded_fields():
    primary, group = _group()
    s = _summarizer({"current_status": "Vendor is fixing CON-2004.", "whats_next": "Deploy tonight."})
    out = s.status(primary, group, [build_comment("1")])
    assert out["current_status"] == "Vendor is fixing CON-2004."
    assert out["whats_next"] == "Deploy tonight."


def test_status_falls_back_on_ungrounded_key():
    primary, group = _group()
    s = _summarizer({"current_status": "Blocked by CON-9999.", "whats_next": "Wait"})
    out = s.status(primary, group, [build_comment("1")])
    assert "CON-9999" not in out["current_status"]
    assert out["current_status"] == "Update received; see ticket for details."


def test_status_falls_back_on_empty():
    primary, group = _group()
    s = _summarizer({"current_status": "", "whats_next": ""})
    out = s.status(primary, group, [build_comment("1")])
    assert out["current_status"] == "Update received; see ticket for details."
    assert out["whats_next"] == "Not stated in ticket"


def test_status_propagates_llm_error():
    primary, group = _group()
    s = _summarizer(exc=LLMError("down"))
    with pytest.raises(LLMError):
        s.status(primary, group, [build_comment("1")])


def test_rca_sanitizes_html_and_prefixes_subject():
    primary, group = _group()
    payload = {
        "subject": "CON-2004 outage",
        "body_html": '<h4>Root Cause</h4><p onclick="x">Bad deploy in CON-9999</p><script>evil()</script>',
    }
    s = _summarizer(payload)
    out = s.rca(primary, group, [build_comment("1")])
    assert out["subject"].startswith("[RCA]")
    assert "<script>" not in out["body_html"] and "onclick" not in out["body_html"]
    assert "CON-9999" not in out["body_html"]
    assert "<h4>Root Cause</h4>" in out["body_html"]


def test_rca_falls_back_on_empty_body():
    primary, group = _group()
    s = _summarizer({"subject": "[RCA] CON-2004", "body_html": ""})
    out = s.rca(primary, group, [build_comment("1")])
    assert "review the ticket" in out["body_html"]


def test_case_facts_returns_all_validated_fields():
    primary, group = _group()
    payload = {
        "current_status": "Vendor patch applied to CON-2004.",
        "whats_next": "Monitor overnight.",
        "customer_impact": "Some users could not log in.",
        "technical_summary": "Token cache misconfig fixed.",
    }
    s = _summarizer(payload)
    out = s.case_facts(primary, group, [build_comment("1")])
    assert out["current_status"].startswith("Vendor patch")
    assert out["customer_impact"].startswith("Some users")
    assert out["technical_summary"].startswith("Token cache")


def test_case_facts_falls_back_on_ungrounded_and_empty():
    primary, group = _group()
    payload = {
        "current_status": "Working on it.",
        "whats_next": "",
        "customer_impact": "Impact traced to CON-9999.",
        "technical_summary": "",
    }
    s = _summarizer(payload)
    out = s.case_facts(primary, group, [build_comment("1")])
    assert out["whats_next"] == "Not stated in ticket"
    assert out["customer_impact"] == "Not stated in ticket"  # ungrounded key rejected
    assert out["technical_summary"] == "Not stated in ticket"


def test_status_delegates_to_case_facts():
    primary, group = _group()
    payload = {
        "current_status": "All good.",
        "whats_next": "Close it.",
        "customer_impact": "None.",
        "technical_summary": "n/a",
    }
    s = _summarizer(payload)
    out = s.status(primary, group, [build_comment("1")])
    assert set(out.keys()) == {"current_status", "whats_next"}
    assert out["current_status"] == "All good."
