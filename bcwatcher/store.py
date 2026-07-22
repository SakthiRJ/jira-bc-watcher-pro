"""Persistence for dashboard settings and the latest scan snapshot.

- settings.json : runtime settings editable from the dashboard.
- results.json  : the latest scan snapshot the dashboard renders and the digest emails.
"""
from __future__ import annotations

import json
import os
import threading

SETTINGS_FILE = "settings.json"
RESULTS_FILE = "results.json"

_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "poll_interval_minutes": 5,
    "realtime_emails": True,   # email each new comment as it arrives
    "rca_emails": True,        # email an RCA when a case closes
    "rca_approval_required": True,  # queue RCAs for engineering sign-off before broadcast
    "digest_enabled": True,    # send one consolidated email at end of day
    "eod_hour": 19,
    "eod_minute": 0,
}


def load_settings() -> dict:
    with _lock:
        data = dict(DEFAULT_SETTINGS)
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                    data.update(json.load(fh))
            except (json.JSONDecodeError, OSError):
                pass
        return data


def save_settings(new_values: dict) -> dict:
    with _lock:
        data = dict(DEFAULT_SETTINGS)
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                    data.update(json.load(fh))
            except (json.JSONDecodeError, OSError):
                pass
        data.update(new_values)
        # sanitize
        data["poll_interval_minutes"] = max(1, int(data.get("poll_interval_minutes", 5)))
        data["eod_hour"] = min(23, max(0, int(data.get("eod_hour", 19))))
        data["eod_minute"] = min(59, max(0, int(data.get("eod_minute", 0))))
        for flag in ("realtime_emails", "rca_emails", "rca_approval_required", "digest_enabled"):
            data[flag] = bool(data.get(flag))
        _atomic_write(SETTINGS_FILE, data)
        return data


def load_results() -> dict:
    with _lock:
        if os.path.exists(RESULTS_FILE):
            try:
                with open(RESULTS_FILE, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        return {"last_scan": None, "scanning": False, "cases": []}


def save_results(snapshot: dict) -> None:
    with _lock:
        _atomic_write(RESULTS_FILE, snapshot)


def set_scanning(flag: bool) -> None:
    snap = load_results()
    snap["scanning"] = flag
    save_results(snap)


def _atomic_write(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)
