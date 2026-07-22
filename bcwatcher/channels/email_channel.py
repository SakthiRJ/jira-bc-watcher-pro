"""Email delivery channel: a thin adapter over the existing SMTP Mailer."""
from __future__ import annotations

from bcwatcher.channels.base import Channel, Message


class EmailChannel(Channel):
    name = "email"

    def __init__(self, mailer):
        self.mailer = mailer

    def deliver(self, message: Message) -> None:
        if not message.recipients:
            return
        self.mailer.send(message.subject, message.body_html, to=message.recipients)
