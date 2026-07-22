"""Fault-injection: a failing email/AI step on one case must not abort the scan
or lose state, and the failed case must be retried next cycle (its pointer is
not advanced), while healthy cases proceed and are persisted.
"""
from __future__ import annotations

from _factories import NEW_TIME, OLD_TIME, build_comment, build_issue

import bcwatcher.scanner as scanner
from bcwatcher.state import State


class FakeJira:
    def __init__(self, config):
        self._open = [
            build_issue("CON-1", "CON"),
            build_issue("CON-2", "CON"),
        ]

    def business_critical_open(self):
        return list(self._open)

    def business_critical_recently_closed(self):
        return []

    def get_issue(self, key):
        return None

    def get_comments(self, key, limit: int = 50):
        return [
            build_comment("old", created=OLD_TIME, body="baseline"),
            build_comment(f"new-{key}", created=NEW_TIME, body="fresh human update"),
        ]


class FakeSummarizer:
    def __init__(self, config):
        pass

    def status(self, primary, group, new_comments):
        return {"current_status": "Investigating.", "whats_next": "Deploy fix."}

    def rca(self, primary, group, comments):
        return {"subject": "[RCA] x", "body_html": "<p>x</p>"}


class FakeMailer:
    def __init__(self, config):
        self.attempts = 0
        self.sent = []

    def send(self, subject, body_html):
        self.attempts += 1
        # Fail the FIRST case only (CON-1, processed first because groups sort by key).
        if self.attempts == 1:
            raise RuntimeError("simulated SMTP failure")
        self.sent.append(subject)


def test_one_failure_does_not_abort_or_lose_state(tmp_path, monkeypatch):
    state_path = str(tmp_path / "state.json")

    # Pre-seed state so both issues are "known" with an old comment pointer,
    # making the NEW_TIME comment count as fresh activity.
    seed = State(state_path)
    for key in ("CON-1", "CON-2"):
        seed.set_last_comment(key, "old", OLD_TIME)
        seed.set_status_category(key, "indeterminate")
    seed.mark_initialized()
    seed.save()

    monkeypatch.setattr(scanner.config, "state_file", state_path)

    saved = {}
    monkeypatch.setattr(scanner.store, "load_results", lambda: {"last_scan": None, "scanning": False, "cases": []})
    monkeypatch.setattr(
        scanner.store,
        "load_settings",
        lambda: {"realtime_emails": True, "rca_emails": True, "digest_enabled": True},
    )
    monkeypatch.setattr(scanner.store, "set_scanning", lambda flag: None)
    monkeypatch.setattr(scanner.store, "save_results", lambda snap: saved.update(snap))

    monkeypatch.setattr(scanner, "JiraClient", FakeJira)
    monkeypatch.setattr(scanner, "Summarizer", FakeSummarizer)
    mailer_holder = {}

    def _fake_mailer(config):
        mailer_holder["m"] = FakeMailer(config)
        return mailer_holder["m"]

    monkeypatch.setattr(scanner, "Mailer", _fake_mailer)

    # Should not raise despite the first case failing.
    snapshot = scanner.run_scan(reason="test")

    mailer = mailer_holder["m"]
    # Both cases were attempted; the healthy one still went out.
    assert mailer.attempts == 2
    assert len(mailer.sent) == 1

    # State was saved with both cases.
    assert snapshot["cases"] and len(snapshot["cases"]) == 2
    assert saved.get("cases")

    # Failed case (CON-1) keeps its old pointer -> retried next cycle.
    reloaded = State(state_path)
    assert reloaded.initialized is True
    assert reloaded.last_comment_time("CON-1") == OLD_TIME
    # Healthy case (CON-2) advanced to the newest comment.
    assert reloaded.last_comment_time("CON-2") == NEW_TIME
