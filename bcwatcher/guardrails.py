"""Deterministic, provider-agnostic guardrails against LLM hallucination.

The pipeline is: extract (one bounded LLM call) -> validate (this module) ->
render (pure-code email templates). Nothing an LLM emits reaches an email
without passing through here first, so a change of provider cannot weaken the
safety properties.

What this module enforces:
  - length caps and whitespace/quote/markdown cleanup on short fields,
  - removal of em/en dashes (house writing style),
  - grounding: any Jira-key-like token in the output must be one of the case's
    real ticket keys; ungrounded short fields are rejected in favour of a
    deterministic fallback, and ungrounded keys in RCA HTML are neutralised,
  - HTML sanitisation to an allow-list of attribute-less tags (no links,
    scripts, styles, or inline handlers).
"""
from __future__ import annotations

import re
from collections.abc import Iterable

_EM_DASH = "\u2014"
_EN_DASH = "\u2013"

# A Jira key looks like PROJECT-123 (e.g. CON-2084, T3-1412).
_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_WS_RE = re.compile(r"\s+")
_MD_RE = re.compile(r"[*_`#]+")
_ALLOWED_TAGS = {"h4", "p", "ul", "ol", "li", "b", "strong", "i", "em", "br"}
_TAG_RE = re.compile(r"</?([a-zA-Z0-9]+)(?:\s[^>]*)?>")
_BLOCK_RE = re.compile(r"(?is)<(script|style)\b.*?>.*?</\1>")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _dedash(text: str) -> str:
    return text.replace(_EM_DASH, " - ").replace(_EN_DASH, "-")


def clean_text(text: str | None, max_len: int | None = None) -> str:
    """Pre-clean source text before sending it to the model.

    Trims trailing whitespace, collapses long blank runs, drops a trailing
    signature block, and optionally caps length. Reduces token usage without
    dropping meaningful content.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Signature separator: everything after a line that is exactly "-- " / "--".
    text = re.split(r"\n--\s*\n", text, maxsplit=1)[0]
    text = _MULTI_NL_RE.sub("\n\n", text).strip()
    if max_len is not None and len(text) > max_len:
        text = text[:max_len].rstrip() + " ...[truncated]"
    return text


def sanitize_line(text: str | None, max_len: int = 280) -> str:
    """Normalise a short single-line field coming back from the model."""
    if not text:
        return ""
    line = _dedash(str(text))
    line = _MD_RE.sub("", line)
    line = _WS_RE.sub(" ", line).strip()
    line = line.strip('"').strip("'").strip()
    if len(line) > max_len:
        line = line[:max_len].rstrip() + "..."
    return line


def find_ungrounded_keys(text: str | None, allowed_keys: Iterable[str]) -> list[str]:
    """Return Jira-key-like tokens in ``text`` that are not in ``allowed_keys``."""
    if not text:
        return []
    allowed = {k.upper() for k in allowed_keys}
    found = {m.upper() for m in _KEY_RE.findall(text)}
    return sorted(k for k in found if k not in allowed)


def is_grounded(text: str | None, allowed_keys: Iterable[str]) -> bool:
    return not find_ungrounded_keys(text, allowed_keys)


def strip_unknown_keys(text: str | None, allowed_keys: Iterable[str], replacement: str = "the related ticket") -> str:
    """Replace any ungrounded Jira key token with a neutral phrase."""
    if not text:
        return ""
    allowed = {k.upper() for k in allowed_keys}

    def _repl(m: re.Match[str]) -> str:
        return m.group(0) if m.group(0).upper() in allowed else replacement

    return _KEY_RE.sub(_repl, text)


def sanitize_html_fragment(fragment: str | None) -> str:
    """Reduce an HTML fragment to attribute-less tags from a small allow-list.

    Removes <script>/<style> blocks entirely, strips every attribute (so no
    href/onclick/style injection survives), and drops any tag not on the
    allow-list while keeping its inner text.
    """
    if not fragment:
        return ""
    frag = _BLOCK_RE.sub("", fragment)

    def _repl(m: re.Match[str]) -> str:
        name = m.group(1).lower()
        if name not in _ALLOWED_TAGS:
            return ""
        return f"</{name}>" if m.group(0).startswith("</") else f"<{name}>"

    frag = _TAG_RE.sub(_repl, frag)
    frag = _dedash(frag)
    return frag.strip()
