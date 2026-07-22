"""AI summaries through a swappable LLM provider, with hard guardrails.

Pipeline: extract -> validate -> render.
  1. ``status(...)`` / ``rca(...)`` issue ONE bounded, temperature-0 call to the
     active provider (Groq by default; OpenAI/Anthropic by config) asking for
     strict JSON.
  2. Every field returned is run through ``bcwatcher.guardrails`` (length caps,
     dash/markdown/quote cleanup, grounding against the case's real ticket keys,
     HTML allow-listing) before it can reach an email.
  3. Deterministic fallbacks ("Not stated in ticket") replace anything empty or
     ungrounded, so a bad generation degrades safely instead of misinforming.

Payloads are bounded (comment count, per-comment length, total size, description
length) to stay under provider request limits and to keep token usage low. A
transport/parse failure raises ``LLMError`` so the scan retries that case next
cycle rather than sending empty content.
"""
from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from bcwatcher import guardrails
from bcwatcher.config import Config
from bcwatcher.guardrails import clean_text
from bcwatcher.llm import LLMProvider, build_provider

if TYPE_CHECKING:  # avoid circular import at runtime
    from bcwatcher.jira_client import Comment, Issue

MAX_COMMENTS = 12
MAX_COMMENT_CHARS = 1200
MAX_TOTAL_COMMENT_CHARS = 9000
MAX_DESCRIPTION_CHARS = 700

STATUS_MAX_CHARS = 280
NEXT_MAX_CHARS = 200
SUBJECT_MAX_CHARS = 180

_STATUS_FALLBACK = "Update received; see ticket for details."
_NOT_STATED = "Not stated in ticket"

_GROUNDING_RULES = (
    "Use only facts present in the data provided. Never invent ticket keys, "
    "names, dates, numbers, or causes. If something is not in the data, say "
    f"'{_NOT_STATED}'. Do not use em dashes."
)


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
        body = clean_text(c.body, MAX_COMMENT_CHARS)
        entry = f"- {c.author} ({c.created}):\n{body}"
        total += len(entry)
        if total > MAX_TOTAL_COMMENT_CHARS:
            lines.append("...[older comments trimmed]")
            break
        lines.append(entry)
    return "\n\n".join(lines) if lines else "(no comments)"


class Summarizer:
    def __init__(self, config: Config, provider: LLMProvider | None = None):
        self.config = config
        # Provider is resolved from config but can be injected (tests / future DI).
        self.provider = provider or build_provider(config)

    def status(self, primary: "Issue", group: list["Issue"], new_comments: list["Comment"]) -> dict:
        keys = ", ".join(i.key for i in group)
        context = self._case_context(primary, group)
        comment_block = _build_comment_block(new_comments)
        system = (
            "You write concise, factual status updates about business-critical "
            "support tickets for non-technical stakeholders. " + _GROUNDING_RULES
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
            (use "{_NOT_STATED}" if it cannot be inferred).
            """
        ).strip()

        data = self.provider.complete_json(system, user)  # raises LLMError on failure
        allowed = {i.key for i in group}

        current = guardrails.sanitize_line(data.get("current_status"), STATUS_MAX_CHARS)
        if not current or not guardrails.is_grounded(current, allowed):
            current = _STATUS_FALLBACK
        nxt = guardrails.sanitize_line(data.get("whats_next"), NEXT_MAX_CHARS)
        if not nxt or not guardrails.is_grounded(nxt, allowed):
            nxt = _NOT_STATED
        return {"current_status": current, "whats_next": nxt}

    def rca(self, primary: "Issue", group: list["Issue"], comments: list["Comment"]) -> dict:
        keys = ", ".join(i.key for i in group)
        context = self._case_context(primary, group)
        thread = _build_comment_block(comments)
        system = (
            "You write clear Root Cause Analysis (RCA) summaries for closed "
            "business-critical tickets, based strictly on the ticket data. "
            + _GROUNDING_RULES
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

        data = self.provider.complete_json(system, user)  # raises LLMError on failure
        allowed = {i.key for i in group}

        subject = guardrails.sanitize_line(data.get("subject"), SUBJECT_MAX_CHARS)
        if not subject:
            subject = f"[RCA] {keys}: {primary.summary}"
        elif not subject.startswith("[RCA]"):
            subject = f"[RCA] {subject}"

        body = guardrails.strip_unknown_keys(data.get("body_html"), allowed)
        body = guardrails.sanitize_html_fragment(body)
        if not body:
            body = "<p>RCA could not be generated automatically; please review the ticket.</p>"
        return {"subject": subject, "body_html": body}

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _case_context(primary: "Issue", group: list["Issue"]) -> str:
        lines = []
        for issue in group:
            role = "primary" if issue.key == primary.key else "linked"
            desc = clean_text(issue.description, MAX_DESCRIPTION_CHARS)
            lines.append(
                f"[{role}] {issue.key} ({issue.project}) | type={issue.issue_type} "
                f"| priority={issue.priority} | status={issue.status} "
                f"| assignee={issue.assignee}\n  summary: {issue.summary}"
                + (f"\n  description: {desc}" if desc else "")
            )
        return "\n".join(lines)
