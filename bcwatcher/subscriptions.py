"""Per-recipient notification subscriptions and routing resolution.

A subscription records which event types a person wants (realtime progress
updates, RCAs, and/or the end-of-day digest), which audience template they should
receive, an optional scope (projects / priorities), and the delivery channel.

Timing (scan interval, digest time) stays a tenant-level setting; this module
only governs *who* gets *what*, not *when*. Subscriptions are stored flat in
``subscriptions.json`` (moves to Postgres in Phase 5).

``add()`` applies self-subscribe guardrails so the dashboard can be exposed
without letting users inject arbitrary recipients, audiences, or channels.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone

from bcwatcher import guardrails
from bcwatcher.config import config
from bcwatcher.emailfmt import AUDIENCES

SUBS_FILE = "subscriptions.json"

EVENTS = ("realtime", "rca", "digest")
KNOWN_CHANNELS = ("email",)
MAX_SUBSCRIPTIONS = 1000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read() -> dict:
    if os.path.exists(SUBS_FILE):
        try:
            with open(SUBS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write(data: dict) -> None:
    tmp = f"{SUBS_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, SUBS_FILE)


def load_all() -> list[dict]:
    with _lock:
        records = list(_read().values())
    records.sort(key=lambda r: r.get("created_at", ""))
    return records


def get(email: str) -> dict | None:
    with _lock:
        rec = _read().get(email.strip().lower())
        return dict(rec) if rec else None


def sanitize(payload: dict) -> dict:
    """Validate and normalise a subscription payload (self-subscribe guardrails).

    Raises ValueError on anything we will not accept, so the API can return 400.
    """
    email = str(payload.get("email", "")).strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("A valid email address is required.")

    audience = str(payload.get("audience", "")).strip().lower()
    if audience not in AUDIENCES:
        raise ValueError(f"audience must be one of {', '.join(AUDIENCES)}.")

    channel = str(payload.get("channel", "email")).strip().lower() or "email"
    if channel not in KNOWN_CHANNELS:
        raise ValueError(f"channel must be one of {', '.join(KNOWN_CHANNELS)}.")

    raw_events = payload.get("events") or []
    events = [e for e in EVENTS if e in raw_events]
    if not events:
        raise ValueError(f"Select at least one event from {', '.join(EVENTS)}.")

    allowed_projects = set(config.projects)
    projects = sorted({
        str(p).strip().upper()
        for p in (payload.get("projects") or [])
        if str(p).strip().upper() in allowed_projects
    })

    priorities = sorted({
        guardrails.sanitize_line(p, 60)
        for p in (payload.get("priorities") or [])
        if guardrails.sanitize_line(p, 60)
    })

    return {
        "email": email,
        "name": guardrails.sanitize_line(payload.get("name"), 120),
        "audience": audience,
        "channel": channel,
        "events": events,
        "projects": projects,
        "priorities": priorities,
        "active": bool(payload.get("active", True)),
    }


def add(payload: dict) -> dict:
    record = sanitize(payload)
    with _lock:
        data = _read()
        existing = data.get(record["email"])
        if not existing and len(data) >= MAX_SUBSCRIPTIONS:
            raise ValueError("Subscription limit reached.")
        record["created_at"] = existing.get("created_at", _now()) if existing else _now()
        record["updated_at"] = _now()
        data[record["email"]] = record
        _write(data)
        return dict(record)


def remove(email: str) -> bool:
    key = email.strip().lower()
    with _lock:
        data = _read()
        if key in data:
            del data[key]
            _write(data)
            return True
        return False


# --------------------------------------------------------------------------
# Routing resolution
# --------------------------------------------------------------------------
def _case_projects(case: dict) -> set[str]:
    keys = case.get("member_keys") or case.get("display_keys") or [case.get("primary_key")]
    return {str(k).split("-")[0] for k in keys if k}


def _matches(record: dict, case: dict | None) -> bool:
    if case is None:
        return True
    projects = record.get("projects") or []
    if projects and not (_case_projects(case) & set(projects)):
        return False
    priorities = record.get("priorities") or []
    case_priority = (case.get("priority") or "").strip()
    if priorities and case_priority and case_priority not in priorities:
        return False
    return True


def resolve(event: str, case: dict | None = None) -> list[dict]:
    """All active subscribers for an event whose scope matches the case."""
    return [
        r for r in load_all()
        if r.get("active", True) and event in r.get("events", []) and _matches(r, case)
    ]


def audience_map(event: str, case: dict | None = None) -> dict[str, list[dict]]:
    """Subscribers for an event grouped by audience (for tailored rendering)."""
    grouped: dict[str, list[dict]] = {}
    for record in resolve(event, case):
        grouped.setdefault(record["audience"], []).append(record)
    return grouped
