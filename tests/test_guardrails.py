"""Guardrail tests: these are the anti-hallucination safety net and must be
provider-independent, so they exercise pure functions with no network."""
from __future__ import annotations

from bcwatcher.guardrails import (
    clean_text,
    find_ungrounded_keys,
    is_grounded,
    sanitize_html_fragment,
    sanitize_line,
    strip_unknown_keys,
)

ALLOWED = {"CON-2004", "T3-1412"}


def test_sanitize_line_strips_dashes_quotes_markdown_and_whitespace():
    raw = '  "**Working** on it \u2014 almost done"   with   gaps  '
    out = sanitize_line(raw)
    assert "\u2014" not in out
    assert "*" not in out
    assert not out.startswith('"')
    assert "  " not in out
    assert out.startswith("Working on it")


def test_sanitize_line_truncates():
    out = sanitize_line("x" * 500, max_len=50)
    assert len(out) == 53  # 50 chars + "..."
    assert out.endswith("...")


def test_sanitize_line_handles_none():
    assert sanitize_line(None) == ""


def test_clean_text_drops_signature_and_collapses_blank_lines():
    raw = "Line one\n\n\n\nLine two\n-- \nSent from my phone\nRegards"
    out = clean_text(raw)
    assert "Sent from my phone" not in out
    assert "\n\n\n" not in out
    assert "Line one" in out and "Line two" in out


def test_clean_text_respects_max_len():
    out = clean_text("abcdefghij", max_len=5)
    assert out.startswith("abcde")
    assert "truncated" in out


def test_find_ungrounded_keys():
    assert find_ungrounded_keys("Progress on CON-2004 and CON-9999", ALLOWED) == ["CON-9999"]
    assert find_ungrounded_keys("Only CON-2004 here", ALLOWED) == []
    assert find_ungrounded_keys("No keys at all", ALLOWED) == []


def test_is_grounded():
    assert is_grounded("Waiting on the vendor for CON-2004", ALLOWED)
    assert not is_grounded("See also ABC-1", ALLOWED)


def test_strip_unknown_keys_neutralises_fabricated_keys():
    out = strip_unknown_keys("Caused by CON-9999, tracked in CON-2004", ALLOWED)
    assert "CON-9999" not in out
    assert "CON-2004" in out
    assert "the related ticket" in out


def test_sanitize_html_removes_scripts_attrs_and_disallowed_tags():
    frag = (
        '<h4>Summary</h4><p style="color:red" onclick="x()">Fixed</p>'
        '<a href="http://evil">link</a><script>alert(1)</script>'
        "<iframe></iframe>"
    )
    out = sanitize_html_fragment(frag)
    assert "<script>" not in out and "alert" not in out
    assert "onclick" not in out and "style=" not in out
    assert "<a" not in out and "href" not in out
    assert "<iframe>" not in out
    assert "<h4>Summary</h4>" in out
    assert "<p>Fixed</p>" in out


def test_sanitize_html_handles_empty():
    assert sanitize_html_fragment("") == ""
    assert sanitize_html_fragment(None) == ""
