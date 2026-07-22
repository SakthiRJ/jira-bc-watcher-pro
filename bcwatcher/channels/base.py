"""Channel abstraction so notifications are not hard-wired to email.

A ``Channel`` takes a rendered ``Message`` and delivers it. Email is the only
channel today; Microsoft Teams (Phase 7) slots in by adding another ``Channel``
implementation and registering it with the ``Notifier`` - no change to the
scanner, RCA, or digest routing code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    subject: str
    body_html: str
    recipients: list[str] = field(default_factory=list)
    audience: str | None = None
    kind: str = "update"


class Channel(ABC):
    name: str = "base"

    @abstractmethod
    def deliver(self, message: Message) -> None:
        """Deliver a message to its recipients on this channel."""
