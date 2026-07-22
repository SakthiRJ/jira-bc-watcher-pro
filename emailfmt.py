"""HTML formatting for emails: per-case blocks, incremental updates, and the
end-of-day consolidated digest. Layout is Description, Current Status,
Last Update, What's next, one ticket after another.
"""
from __future__ import annotations

import html


def _fmt_when(iso: str | None) -> str:
    if not iso:
        return "unknown time"
    # Jira gives e.g. 2026-06-30T05:36:22.803+0100 -> keep date + HH:MM
    return iso.replace("T", " ")[:16]


def _keys_title(case: dict) -> str:
    return " + ".join(case.get("display_keys") or [case.get("primary_key", "")])


def _last_update_line(case: dict) -> str:
    if case.get("no_update"):
        return "No update since last check"
    author = case.get("last_update_author")
    when = _fmt_when(case.get("last_update_time"))
    if author:
        return f"{html.escape(author)} at {when}"
    return "No comments recorded"


def render_case_block(case: dict, jira_base_url: str) -> str:
    title = html.escape(_keys_title(case))
    primary = case.get("primary_key", "")
    url = f"{jira_base_url}/browse/{primary}" if primary else "#"
    summary = html.escape(case.get("summary", ""))
    ctype = html.escape(case.get("type", ""))
    status = html.escape(case.get("status", ""))
    description = html.escape(case.get("description", "") or "Not stated in ticket")
    current = html.escape(case.get("current_status", "") or "No update since last check")
    whats_next = html.escape(case.get("whats_next", "") or "Not stated in ticket")

    return (
        '<div style="border:1px solid #dfe1e6;border-radius:8px;padding:14px 16px;margin:0 0 14px 0">'
        f'<div style="font-size:15px;font-weight:600;color:#172b4d">'
        f'<a href="{url}" style="color:#0052cc;text-decoration:none">{title}</a>'
        f' <span style="color:#6b778c;font-weight:400">| {ctype} | {status}</span></div>'
        f'<div style="margin-top:6px;color:#172b4d">{summary}</div>'
        f'<div style="margin-top:10px"><b>Description:</b> {description}</div>'
        f'<div style="margin-top:6px"><b>Current Status:</b> {current}</div>'
        f'<div style="margin-top:6px"><b>Last Update:</b> {_last_update_line(case)}</div>'
        f'<div style="margin-top:6px"><b>What\'s next:</b> {whats_next}</div>'
        "</div>"
    )


def _wrap(body: str) -> str:
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#172b4d;'
        'max-width:820px">' + body + "</div>"
    )


def render_progress_email(case: dict, jira_base_url: str) -> tuple[str, str]:
    title = _keys_title(case)
    subject = f"[Update] {title}: {case.get('summary', '')}"[:180]
    body = _wrap(
        '<p style="margin:0 0 12px 0">A business-critical case received a new update:</p>'
        + render_case_block(case, jira_base_url)
    )
    return subject, body


def render_digest(cases: list[dict], jira_base_url: str, date_str: str) -> tuple[str, str]:
    active = [c for c in cases if c.get("status_category") != "done"]
    subject = f"Business-Critical Daily Digest - {date_str} ({len(active)} open case(s))"
    if not active:
        inner = '<p>No open business-critical cases at end of day.</p>'
    else:
        blocks = "".join(render_case_block(c, jira_base_url) for c in active)
        inner = (
            f'<p style="margin:0 0 12px 0">End-of-day summary of <b>{len(active)}</b> '
            "open business-critical case(s):</p>" + blocks
        )
    header = (
        '<h2 style="color:#172b4d;margin:0 0 12px 0">Business-Critical Ticket Status</h2>'
        f'<p style="color:#6b778c;margin:0 0 16px 0">{date_str}</p>'
    )
    return subject, _wrap(header + inner)
