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


def _row(label: str, value: str) -> str:
    return f'<div style="margin-top:6px"><b>{label}:</b> {value}</div>'


def _fact(case: dict, key: str, fallback: str = "Not stated in ticket") -> str:
    return html.escape(case.get(key) or fallback)


# Per-audience view: which facts to show, subject prefix, and a friendly label.
# Rendering is pure code from the single validated fact set, so notifying more
# audiences costs no extra AI calls.
_ROWS = {
    "current_status": lambda c: _row("Current Status", _fact(c, "current_status")),
    "whats_next": lambda c: _row("What's next", _fact(c, "whats_next")),
    "customer_impact": lambda c: _row("Customer impact", _fact(c, "customer_impact")),
    "technical_summary": lambda c: _row("Technical summary", _fact(c, "technical_summary")),
    "owner": lambda c: _row("Owner", html.escape(c.get("owner") or "Unassigned")),
    "priority": lambda c: _row("Priority", html.escape(c.get("priority") or "Business Critical")),
    "last_update": lambda c: _row("Last Update", _last_update_line(c)),
    "last_comment": lambda c: _row(
        "Latest comment", html.escape(c.get("last_update_body") or "No recent comment")
    ),
}

_AUDIENCE_SPECS = {
    "support": {
        "prefix": "[Support Update]",
        "label": "Support",
        "rows": ["current_status", "whats_next", "customer_impact", "last_update"],
    },
    "dev": {
        "prefix": "[Engineering]",
        "label": "Engineering",
        "rows": ["technical_summary", "current_status", "whats_next", "last_comment", "owner"],
    },
    "manager": {
        "prefix": "[BC Update]",
        "label": "Manager",
        "rows": ["current_status", "customer_impact", "whats_next", "owner", "priority"],
    },
    "leadership": {
        "prefix": "[Business Critical]",
        "label": "Leadership",
        "rows": ["customer_impact", "current_status", "priority"],
    },
}

AUDIENCES = tuple(_AUDIENCE_SPECS.keys())


def render_audience_email(case: dict, audience: str, jira_base_url: str) -> tuple[str, str]:
    """Render a recipient-tailored update for one audience from validated facts."""
    spec = _AUDIENCE_SPECS.get(audience, _AUDIENCE_SPECS["support"])
    title = _keys_title(case)
    summary = case.get("summary", "")
    subject = f"{spec['prefix']} {title}: {summary}"[:180]

    primary = case.get("primary_key", "")
    url = f"{jira_base_url}/browse/{primary}" if primary else "#"
    rows_html = "".join(_ROWS[key](case) for key in spec["rows"] if key in _ROWS)

    body = _wrap(
        f'<p style="margin:0 0 8px 0;color:#6b778c">Business-critical case - {spec["label"]} update</p>'
        '<div style="border:1px solid #dfe1e6;border-radius:8px;padding:14px 16px">'
        '<div style="font-size:15px;font-weight:600;color:#172b4d">'
        f'<a href="{url}" style="color:#0052cc;text-decoration:none">{html.escape(title)}</a>'
        f' <span style="color:#6b778c;font-weight:400">| {html.escape(case.get("status", ""))}</span></div>'
        f'<div style="margin-top:6px;color:#172b4d">{html.escape(summary)}</div>'
        + rows_html
        + f'<div style="margin-top:12px"><a href="{url}">Open {html.escape(primary)}</a></div>'
        "</div>"
    )
    return subject, body


def render_rca_email(record: dict, jira_base_url: str) -> tuple[str, str]:
    """Render the final RCA email from a queued record.

    ``body_html`` was already sanitised by the guardrails when generated (and
    again if an approver edited it), so it is trusted here.
    """
    keys_title = " + ".join(record.get("display_keys") or [record.get("primary_key", "")])
    primary = record.get("primary_key", "")
    summary = record.get("summary", "")
    subject = record.get("subject") or f"[RCA] {keys_title}"
    url = f"{jira_base_url}/browse/{primary}" if primary else "#"
    body = _wrap(
        f'<h2 style="color:#172b4d;margin:0 0 10px 0">RCA: {html.escape(keys_title)}</h2>'
        f'<p style="color:#6b778c;margin:0 0 14px 0">{html.escape(primary)} - {html.escape(summary)}</p>'
        + (record.get("body_html") or "")
        + f'<p style="margin-top:14px"><a href="{url}">Open {html.escape(primary)}</a></p>'
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
