"""Delivery channels for notifications (email now; Teams etc. later)."""
from __future__ import annotations

from bcwatcher.channels.base import Channel, Message
from bcwatcher.channels.email_channel import EmailChannel

__all__ = ["Channel", "Message", "EmailChannel"]
