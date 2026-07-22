"""Progress updates route through subscriptions, falling back to env config."""
from __future__ import annotations

import pytest

import bcwatcher.scanner as scanner
import bcwatcher.subscriptions as subs
from bcwatcher.config import config


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, subject, body_html, to=None):
        self.sent.append({"subject": subject, "to": to})


def _case():
    return {
        "display_keys": ["CON-1"],
        "primary_key": "CON-1",
        "member_keys": ["CON-1"],
        "summary": "Login outage",
        "status": "In Progress",
        "priority": "Business Critical",
        "owner": "Alice Dev",
        "current_status": "Vendor patch applied.",
        "whats_next": "Monitor overnight.",
        "customer_impact": "Some users cannot log in.",
        "technical_summary": "Auth cache misconfig.",
        "last_update_author": "Alice Dev",
        "last_update_time": "2026-07-22T10:00:00.000+0000",
        "last_update_body": "Applied the vendor patch.",
    }


@pytest.fixture
def clean_subs(tmp_path, monkeypatch):
    monkeypatch.setattr(subs, "SUBS_FILE", str(tmp_path / "subscriptions.json"))
    monkeypatch.setattr(config, "projects", ["CON", "T3", "CL"])


def test_routes_to_matching_subscriber(clean_subs):
    subs.add({
        "email": "support@company.com",
        "audience": "support",
        "events": ["realtime"],
        "projects": ["CON"],
    })
    mailer = FakeMailer()
    scanner._send_progress_emails(mailer, _case())
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["to"] == ["support@company.com"]
    assert mailer.sent[0]["subject"].startswith("[Support Update]")


def test_out_of_scope_subscriber_gets_nothing_falls_back(clean_subs, monkeypatch):
    # Subscriber only wants T3; the CON case does not match, so no audience subs ->
    # fall through to the env path (which we force to the general update here).
    subs.add({
        "email": "t3@company.com",
        "audience": "support",
        "events": ["realtime"],
        "projects": ["T3"],
    })
    monkeypatch.setattr(config, "audience_recipients", lambda: {})
    mailer = FakeMailer()
    scanner._send_progress_emails(mailer, _case())
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["to"] is None


def test_general_fallback_when_no_subscriptions(clean_subs, monkeypatch):
    monkeypatch.setattr(config, "audience_recipients", lambda: {})
    mailer = FakeMailer()
    scanner._send_progress_emails(mailer, _case())
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["to"] is None
