"""Dispatch a rendered notification to subscriber records across channels.

The notifier groups subscriber records by their ``channel`` and hands each group
to the matching ``Channel``. Records destined for an unregistered channel are
skipped (returned as ``skipped`` so callers can log), which keeps a missing
future channel from raising in the scan loop.
"""
from __future__ import annotations

from bcwatcher.channels import Channel, EmailChannel, Message


class Notifier:
    def __init__(self, channels: dict[str, Channel]):
        self.channels = channels

    @classmethod
    def with_email(cls, mailer) -> "Notifier":
        return cls({"email": EmailChannel(mailer)})

    def send(
        self,
        records: list[dict],
        subject: str,
        body_html: str,
        audience: str | None = None,
        kind: str = "update",
    ) -> list[str]:
        by_channel: dict[str, list[str]] = {}
        for record in records:
            by_channel.setdefault(record.get("channel", "email"), []).append(record["email"])

        skipped: list[str] = []
        for channel_name, emails in by_channel.items():
            channel = self.channels.get(channel_name)
            if channel is None:
                skipped.append(channel_name)
                continue
            channel.deliver(
                Message(
                    subject=subject,
                    body_html=body_html,
                    recipients=sorted(set(emails)),
                    audience=audience,
                    kind=kind,
                )
            )
        return skipped
