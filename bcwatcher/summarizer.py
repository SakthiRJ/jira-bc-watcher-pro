"""AI summaries via Groq (OpenAI-compatible chat completions).

- ``status(...)`` returns {"current_status", "whats_next"} for a case with new
  activity (used by both the dashboard and the incremental emails).
- ``rca(...)`` returns {"subject", "body_html"} for a closed case.

Payloads are bounded (comment count, per-comment length, total size, and
description length) so long threads stay under Groq's request-size limit. If a
call fails, deterministic fallbacks are returned so the scan never crashes.
"""
from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING

import requests

from bcwatcher.config import Config

if TYPE_CHECKING:  # avoid circular import at runtime
    from bcwatcher.jira_client import Comment, Issue

MAX_COMMENTS = 12
MAX_COMMENT_CHARS = 1200
MAX_TOTAL_COMMENT_CHARS = 9000
MAX_DESCRIPTION_CHARS = 700
MAX_OUTPUT_TOKENS = 700


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ...[truncated]"


def _build_comment_block(comments: list["Comment"]) -> str:
    selected = comments[-MAX_COMMENTS:]
    omitted = len(comments) - len(selected)
    lines: list[str] = []
    if omitted > 0:
        lines.append(f"({omitted} earlier comment(s) omitted for brevity)")
    total = 0
    for c in selected:
        body = truncate(c.body, MAX_COMMENT_CHARS)
        entry = f"- {c.author} ({c.created}):\n{body}"
        total += len(entry)
        if total > MAX_TOTAL_COMMENT_CHARS:
            lines.append("...[older comments trimmed]")
            break
        lines.append(entry)
    return "\n\n".join(lines) if lines else "(no comments)"


class Summarizer:
    def __init__(self, config: Config):
        self.config = config

    def status(self, primary: "Issue", group: list["Issue"], new_comments: list["Comment"]) -> dict:
        keys = ", ".join(i.key for i in group)
        context = self._case_context(primary, group)
        comment_block = _build_comment_block(new_comments)
        system = (
            "You write concise, factual status updates about business-critical "
            "support tickets for non-technical stakeholders. Never invent details "
            "not in the data. Do not use em dashes."
        )
        user = textwrap.dedent(
            f"""
            Business-critical case ({keys}) has new activity. Summarize it.

            CASE CONTEXT:
            {context}

            NEW COMMENT(S) SINCE LAST UPDATE:
            {comment_block}

            Return ONLY valid JSON with two keys:
            "current_status": one or two sentences on where the case stands now,
            "whats_next": one sentence on the next action or expected step
            (use "Not stated in ticket" if it cannot be inferred).
            """
        ).strip()
        data = self._complete(system, user)
        return {
            "current_status": (data.get("current_status") or "Update received; see ticket for details.").strip(),
            "whats_next": (data.get("whats_next") or "Not stated in ticket").strip(),
        }

    def rca(self, primary: "Issue", group: list["Issue"], comments: list["Comment"]) -> dict:
        keys = ", ".join(i.key for i in group)
        context = self._case_context(primary, group)
        thread = _build_comment_block(comments)
        system = (
            "You write clear Root Cause Analysis (RCA) summaries for closed "
            "business-critical tickets, based strictly on the ticket data. If a "
            "section cannot be determined, say 'Not stated in ticket'. Do not use em dashes."
        )
        user = textwrap.dedent(
            f"""
            The business-critical case ({keys}) has been resolved/closed. Write an RCA.

            CASE CONTEXT:
            {context}

            COMMENT THREAD (most recent activity):
            {thread}

            Return ONLY valid JSON with two keys:
            "subject": a one-line subject starting with "[RCA]" and the key(s),
            "body_html": an HTML fragment (no <html>/<body> tags) with these
            <h4> sections: Summary, Impact, Root Cause, Resolution, Preventive Actions.
            Keep each to 1-3 sentences.
            """
        ).strip()
        data = self._complete(system, user)
        subject = (data.get("subject") or f"[RCA] {keys}: {primary.summary}").strip()
        body = (data.get("body_html") or "").strip()
        if not body:
            body = "<p>RCA could not be generated automatically; please review the ticket.</p>"
        return {"subject": subject, "body_html": body}

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _case_context(primary: "Issue", group: list["Issue"]) -> str:
        lines = []
        for issue in group:
            role = "primary" if issue.key == primary.key else "linked"
            desc = truncate(issue.description, MAX_DESCRIPTION_CHARS)
            lines.append(
                f"[{role}] {issue.key} ({issue.project}) | type={issue.issue_type} "
                f"| priority={issue.priority} | status={issue.status} "
                f"| assignee={issue.assignee}\n  summary: {issue.summary}"
                + (f"\n  description: {desc}" if desc else "")
            )
        return "\n".join(lines)

    def _complete(self, system: str, user: str) -> dict:
        try:
            resp = requests.post(
                f"{self.config.groq_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.config.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.groq_model,
                    "temperature": 0.2,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=60,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as exc:  # noqa: BLE001 - never break the scan
            return {"_error": str(exc)}
