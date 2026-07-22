"""RCA approval service: approve broadcasts + marks sent, reject, sanitisation."""
from __future__ import annotations

import pytest

import bcwatcher.rca_service as svc
import bcwatcher.rca_store as rs


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, subject, body_html, to=None):
        self.sent.append({"subject": subject, "body": body_html, "to": to})


@pytest.fixture
def store_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "RCA_FILE", str(tmp_path / "rca_queue.json"))
    return rs


def _seed(rca_id="CON-1", body="<h4>Root Cause</h4><p>Cache misconfig.</p>"):
    return rs.upsert({
        "id": rca_id,
        "primary_key": rca_id,
        "display_keys": [rca_id],
        "summary": "Login outage",
        "subject": f"[RCA] {rca_id}",
        "body_html": body,
    })


def test_approve_sends_and_marks_sent(store_file):
    _seed()
    mailer = FakeMailer()
    rec = svc.approve("CON-1", approver="alice", mailer=mailer)
    assert rec["status"] == rs.SENT
    assert rec["approved_by"] == "alice" and rec["sent_at"]
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["subject"].startswith("[RCA]")
    assert "Cache misconfig" in mailer.sent[0]["body"]


def test_approve_is_idempotent_when_already_sent(store_file):
    _seed()
    rs.set_status("CON-1", rs.SENT)
    mailer = FakeMailer()
    svc.approve("CON-1", mailer=mailer)
    assert mailer.sent == []


def test_approve_sanitizes_editor_changes(store_file):
    _seed()
    mailer = FakeMailer()
    rec = svc.approve(
        "CON-1",
        edited_body='<p onclick="steal()">Edited root cause</p><script>evil()</script>',
        mailer=mailer,
    )
    assert "script" not in rec["body_html"].lower()
    assert "onclick" not in rec["body_html"].lower()
    assert "Edited root cause" in rec["body_html"]


def test_approve_missing_raises(store_file):
    with pytest.raises(KeyError):
        svc.approve("nope")


def test_reject_marks_rejected(store_file):
    _seed()
    rec = svc.reject("CON-1", approver="bob", reason="Needs vendor confirmation")
    assert rec["status"] == rs.REJECTED
    assert rec["rejected_by"] == "bob"
    assert "vendor" in rec["reason"]
    assert rs.pending() == []
