"""Notifier dispatch across channels + email channel behavior."""
from __future__ import annotations

from bcwatcher.channels import Channel, EmailChannel, Message
from bcwatcher.notifier import Notifier


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, subject, body_html, to=None):
        self.sent.append({"subject": subject, "to": to})


class RecordingChannel(Channel):
    name = "rec"

    def __init__(self):
        self.messages = []

    def deliver(self, message: Message) -> None:
        self.messages.append(message)


def _rec(email, channel="email"):
    return {"email": email, "channel": channel, "audience": "support", "events": ["realtime"]}


def test_email_channel_sends_to_recipients():
    mailer = FakeMailer()
    ch = EmailChannel(mailer)
    ch.deliver(Message("Subj", "<p>x</p>", ["a@x.com", "b@x.com"], audience="support"))
    assert mailer.sent == [{"subject": "Subj", "to": ["a@x.com", "b@x.com"]}]


def test_email_channel_skips_when_no_recipients():
    mailer = FakeMailer()
    EmailChannel(mailer).deliver(Message("Subj", "<p>x</p>", []))
    assert mailer.sent == []


def test_notifier_groups_and_dedupes_recipients():
    mailer = FakeMailer()
    notifier = Notifier.with_email(mailer)
    records = [_rec("a@x.com"), _rec("b@x.com"), _rec("a@x.com")]
    skipped = notifier.send(records, "Subj", "<p>x</p>", audience="support")
    assert skipped == []
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["to"] == ["a@x.com", "b@x.com"]


def test_notifier_reports_unknown_channel():
    mailer = FakeMailer()
    notifier = Notifier.with_email(mailer)
    skipped = notifier.send([_rec("a@x.com", channel="teams")], "Subj", "<p>x</p>")
    assert skipped == ["teams"]
    assert mailer.sent == []


def test_notifier_routes_multiple_channels():
    mailer = FakeMailer()
    rec_channel = RecordingChannel()
    notifier = Notifier({"email": EmailChannel(mailer), "rec": rec_channel})
    notifier.send([_rec("a@x.com"), _rec("b@x.com", channel="rec")], "Subj", "<p>x</p>")
    assert mailer.sent[0]["to"] == ["a@x.com"]
    assert rec_channel.messages[0].recipients == ["b@x.com"]
