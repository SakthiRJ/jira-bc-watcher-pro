"""End-of-day consolidated digest.

Sends a single email that mirrors the dashboard: every open business-critical
case with its Description, Current Status, Last Update and What's next. The
scheduled end-of-day job runs a fresh scan first so the digest reflects the
latest ticket activity; the manual "send now" button emails the current
snapshot as-is.
"""
from __future__ import annotations

from datetime import datetime

from bcwatcher import store
from bcwatcher.config import config
from bcwatcher.emailfmt import render_digest
from bcwatcher.mailer import Mailer


def send_digest(scan_first: bool = False, reason: str = "manual") -> dict:
    """Email the consolidated end-of-day digest.

    Returns a small result dict describing what happened so callers (the
    dashboard API and the scheduler) can log / surface it.
    """
    if scan_first:
        # Imported lazily to avoid a circular import at module load time.
        from bcwatcher.scanner import run_scan

        run_scan(reason=f"digest:{reason}")

    snapshot = store.load_results()
    cases = snapshot.get("cases", [])
    open_cases = [c for c in cases if c.get("status_category") != "done"]

    date_str = datetime.now().strftime("%A, %d %b %Y")
    subject, body = render_digest(cases, config.jira_base_url, date_str)
    Mailer(config).send(subject, body)

    return {
        "sent": True,
        "dry_run": config.dry_run,
        "open_cases": len(open_cases),
        "subject": subject,
        "reason": reason,
    }
