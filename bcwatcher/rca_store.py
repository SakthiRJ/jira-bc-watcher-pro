"""Persistent queue of RCA records with an approval state machine.

An RCA is not emailed to stakeholders the moment a case closes. Instead it is
generated once and parked here as ``pending_approval`` until an engineer signs it
off from the dashboard, at which point it is broadcast and marked ``sent``.

State machine:  pending_approval -> approved -> sent
                pending_approval -> rejected

Records are keyed by the case root key (one RCA per case) so re-scans update the
same record instead of creating duplicates. Stored in ``rca_queue.json``.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

RCA_FILE = "rca_queue.json"

PENDING = "pending_approval"
APPROVED = "approved"
SENT = "sent"
REJECTED = "rejected"

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read() -> dict:
    if os.path.exists(RCA_FILE):
        try:
            with open(RCA_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write(data: dict) -> None:
    tmp = f"{RCA_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, RCA_FILE)


def load_all() -> list[dict]:
    with _lock:
        records = list(_read().values())
    records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return records


def get(rca_id: str) -> dict | None:
    with _lock:
        rec = _read().get(rca_id)
        return dict(rec) if rec else None


def pending() -> list[dict]:
    return [r for r in load_all() if r.get("status") == PENDING]


def upsert(record: dict) -> dict:
    """Create or update a record by id, preserving created_at on updates.

    An already-sent record is left untouched so a re-scan cannot resurrect or
    resend an RCA that has already gone out.
    """
    rca_id = record["id"]
    with _lock:
        data = _read()
        existing = data.get(rca_id)
        if existing and existing.get("status") == SENT:
            return dict(existing)
        merged = dict(existing or {})
        merged.update(record)
        merged.setdefault("created_at", _now())
        merged.setdefault("status", PENDING)
        merged["updated_at"] = _now()
        data[rca_id] = merged
        _write(data)
        return dict(merged)


def set_status(rca_id: str, status: str, **fields) -> dict:
    with _lock:
        data = _read()
        rec = data.get(rca_id)
        if not rec:
            raise KeyError(rca_id)
        rec["status"] = status
        rec["updated_at"] = _now()
        rec.update(fields)
        data[rca_id] = rec
        _write(data)
        return dict(rec)
