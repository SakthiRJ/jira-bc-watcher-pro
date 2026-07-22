"""RCA approval workflow: list, approve (broadcast), and reject queued RCAs.

Kept free of Flask so it is unit-testable and reusable. The dashboard API is a
thin wrapper over these functions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bcwatcher import guardrails, rca_store, subscriptions
from bcwatcher.config import config
from bcwatcher.emailfmt import render_rca_email
from bcwatcher.mailer import Mailer
from bcwatcher.notifier import Notifier


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_records() -> list[dict]:
    return rca_store.load_all()


def list_pending() -> list[dict]:
    return rca_store.pending()


def approve(rca_id: str, approver: str = "engineering", edited_body: str | None = None, mailer=None) -> dict:
    """Approve an RCA and broadcast it to the RCA recipient list.

    An optional approver edit is re-sanitised before it goes out. Already-sent
    records are returned unchanged (idempotent).
    """
    rec = rca_store.get(rca_id)
    if not rec:
        raise KeyError(rca_id)
    if rec.get("status") == rca_store.SENT:
        return rec

    if edited_body is not None:
        rec["body_html"] = guardrails.sanitize_html_fragment(edited_body)

    subject, body = render_rca_email(rec, config.jira_base_url)
    sender = mailer or Mailer(config)
    case_scope = {"member_keys": rec.get("display_keys") or [rec.get("primary_key")]}
    subs = subscriptions.resolve("rca", case_scope)
    if subs:
        Notifier.with_email(sender).send(subs, subject, body, kind="rca")
    else:
        sender.send(subject, body, to=config.rca_recipients())

    return rca_store.set_status(
        rca_id,
        rca_store.SENT,
        body_html=rec["body_html"],
        approved_by=approver,
        approved_at=_now(),
        sent_at=_now(),
    )


def reject(rca_id: str, approver: str = "engineering", reason: str = "") -> dict:
    if not rca_store.get(rca_id):
        raise KeyError(rca_id)
    return rca_store.set_status(
        rca_id,
        rca_store.REJECTED,
        rejected_by=approver,
        reason=guardrails.sanitize_line(reason, 500),
        rejected_at=_now(),
    )
