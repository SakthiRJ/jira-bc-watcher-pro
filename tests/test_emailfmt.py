"""Audience-tailored email rendering: each audience sees the right facts, and
nothing is rendered unescaped."""
from __future__ import annotations

from bcwatcher.emailfmt import AUDIENCES, render_audience_email

BASE = "https://example.atlassian.net"


def _case(**overrides):
    case = {
        "display_keys": ["CON-2004 + T3-1412"],
        "primary_key": "CON-2004",
        "summary": "Login outage",
        "status": "In Progress",
        "priority": "Business Critical",
        "owner": "Alice Dev",
        "current_status": "Vendor patch applied.",
        "whats_next": "Monitor overnight.",
        "customer_impact": "Some users cannot log in.",
        "technical_summary": "Auth token cache misconfiguration.",
        "last_update_author": "Alice Dev",
        "last_update_time": "2026-07-22T10:00:00.000+0000",
        "last_update_body": "Applied the vendor patch.",
    }
    case.update(overrides)
    return case


def test_all_audiences_render_with_link_and_summary():
    for audience in AUDIENCES:
        subject, body = render_audience_email(_case(), audience, BASE)
        assert "CON-2004" in subject
        assert "Login outage" in body
        assert f"{BASE}/browse/CON-2004" in body


def test_leadership_hides_technical_detail():
    _, body = render_audience_email(_case(), "leadership", BASE)
    assert "Customer impact" in body
    assert "Technical summary" not in body
    assert "Latest comment" not in body


def test_dev_shows_technical_and_latest_comment():
    subject, body = render_audience_email(_case(), "dev", BASE)
    assert subject.startswith("[Engineering]")
    assert "Technical summary" in body
    assert "Auth token cache misconfiguration." in body
    assert "Latest comment" in body
    assert "Applied the vendor patch." in body


def test_support_shows_impact_and_next():
    subject, body = render_audience_email(_case(), "support", BASE)
    assert subject.startswith("[Support Update]")
    assert "Customer impact" in body
    assert "What&#x27;s next" in body or "What's next" in body


def test_manager_shows_owner_and_priority():
    subject, body = render_audience_email(_case(), "manager", BASE)
    assert subject.startswith("[BC Update]")
    assert "Owner" in body and "Alice Dev" in body
    assert "Priority" in body


def test_unknown_audience_falls_back_to_support():
    subject, _ = render_audience_email(_case(), "nope", BASE)
    assert subject.startswith("[Support Update]")


def test_summary_is_html_escaped():
    _, body = render_audience_email(_case(summary="<script>alert(1)</script>"), "support", BASE)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
