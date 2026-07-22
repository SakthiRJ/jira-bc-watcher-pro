"""A closed case must queue its RCA for engineering approval (default) instead of
broadcasting it, and only email directly when approval is turned off.
"""
from __future__ import annotations

from _factories import OLD_TIME, build_comment, build_issue

import bcwatcher.rca_store as rca_store
import bcwatcher.scanner as scanner
from bcwatcher.state import State


class FakeJira:
    def __init__(self, config):
        pass

    def business_critical_open(self):
        return []

    def business_critical_recently_closed(self):
        return [build_issue("CON-9", "CON", status="Done", status_category="done")]

    def get_issue(self, key):
        return None

    def get_comments(self, key, limit: int = 50):
        return [build_comment("old", created=OLD_TIME, body="baseline")]


class FakeSummarizer:
    def __init__(self, config):
        pass

    def case_facts(self, primary, group, new_comments):
        return {
            "current_status": "Closed.",
            "whats_next": "None",
            "customer_impact": "Not stated in ticket",
            "technical_summary": "Not stated in ticket",
        }

    def rca(self, primary, group, comments):
        return {"subject": "[RCA] CON-9", "body_html": "<h4>Root Cause</h4><p>Cache misconfig.</p>"}


class FakeMailer:
    def __init__(self, config):
        self.sent = []

    def send(self, subject, body_html, to=None):
        self.sent.append({"subject": subject, "to": to})


def _run(tmp_path, monkeypatch, settings):
    state_path = str(tmp_path / "state.json")
    monkeypatch.setattr(rca_store, "RCA_FILE", str(tmp_path / "rca_queue.json"))

    # Closed key is "known" and was NOT previously done, so closure is detected.
    seed = State(state_path)
    seed.set_last_comment("CON-9", "old", OLD_TIME)
    seed.set_status_category("CON-9", "indeterminate")
    seed.mark_initialized()
    seed.save()

    monkeypatch.setattr(scanner.config, "state_file", state_path)
    monkeypatch.setattr(
        scanner.store, "load_results", lambda: {"last_scan": None, "scanning": False, "cases": []}
    )
    monkeypatch.setattr(scanner.store, "load_settings", lambda: settings)
    monkeypatch.setattr(scanner.store, "set_scanning", lambda flag: None)
    monkeypatch.setattr(scanner.store, "save_results", lambda snap: None)
    monkeypatch.setattr(scanner, "JiraClient", FakeJira)
    monkeypatch.setattr(scanner, "Summarizer", FakeSummarizer)

    holder = {}

    def _fake_mailer(config):
        holder["m"] = FakeMailer(config)
        return holder["m"]

    monkeypatch.setattr(scanner, "Mailer", _fake_mailer)
    scanner.run_scan(reason="test")
    return holder["m"]


def test_closure_queues_rca_for_approval_by_default(tmp_path, monkeypatch):
    mailer = _run(
        tmp_path,
        monkeypatch,
        {"realtime_emails": False, "rca_emails": True, "rca_approval_required": True, "digest_enabled": False},
    )
    pending = rca_store.pending()
    assert [r["id"] for r in pending] == ["CON-9"]
    assert pending[0]["subject"] == "[RCA] CON-9"
    # Nothing was broadcast.
    assert mailer.sent == []


def test_closure_sends_directly_when_approval_disabled(tmp_path, monkeypatch):
    mailer = _run(
        tmp_path,
        monkeypatch,
        {"realtime_emails": False, "rca_emails": True, "rca_approval_required": False, "digest_enabled": False},
    )
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["subject"] == "[RCA] CON-9"
    assert rca_store.get("CON-9")["status"] == rca_store.SENT
