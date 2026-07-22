# Architecture Notes

This repository is the productization baseline of the Jira Business-Critical Watcher.
It is being evolved from a single-tenant prototype into an on-prem, multi-company product.

The authoritative phased plan (with testing and sign-off gates per phase) is tracked
separately as the "BC Watcher Productization" plan. This document captures durable
architecture notes as each phase lands.

## Current state

The application code lives in the `bcwatcher/` package; Windows helper scripts live in
`scripts/`. Entry points run as modules from the repo root (`python -m bcwatcher.app`).

Single-process Flask app plus an APScheduler timer:

- `bcwatcher/app.py` - dashboard + scheduler (scan timer + end-of-day digest).
- `bcwatcher/scanner.py` - one scan pass; writes `results.json` for the dashboard/digest.
- `bcwatcher/grouping.py` - union-find grouping of linked tickets into cases (currently
  hardcoded to this Jira's link/Epic conventions; becomes per-project configurable in Phase 5).
- `bcwatcher/jira_client.py` - Jira REST client (search, comments, linked issues).
- `bcwatcher/summarizer.py` - extract -> validate -> render over a swappable LLM provider.
- `bcwatcher/llm/` - pluggable provider layer (Groq/OpenAI/Azure + Anthropic).
- `bcwatcher/guardrails.py` - provider-independent anti-hallucination validation.
- `bcwatcher/emailfmt.py` / `bcwatcher/mailer.py` - HTML formatting and SMTP delivery.
- `bcwatcher/state.py` / `bcwatcher/store.py` - flat-file persistence (moves to Postgres in Phase 5).

## Design principle carried through every phase

Separate "extract facts" from "write emails":
1. One AI call per case produces strict, grounded fact JSON.
2. Pure-code validation rejects anything not present in the source ticket.
3. Pure-code templates render per-audience emails from that validated JSON.

## Phase 0 changes (reliability + test harness)

- Per-case try/except around the AI and email steps in `scanner.py`: one failing case
  no longer aborts the whole scan, and failed cases keep their state pointers so they
  retry on the next cycle instead of being silently skipped.
- Pinned dependencies (`requirements.txt`, `requirements-dev.txt`).
- Test suite (`tests/`) with a golden grouping snapshot that locks current grouping
  behavior as the regression baseline for the Phase 5 configurable engine.
- CI (`.github/workflows/ci.yml`) runs ruff + pytest on push/PR.

## Phase 1 changes (swappable LLM + guardrails)

- `bcwatcher/llm/` is a pluggable provider layer: `LLMProvider` base, an
  OpenAI-compatible provider (Groq/OpenAI/Azure), an Anthropic provider, and a
  `build_provider` factory. The active provider is chosen by `LLM_PROVIDER`;
  `Config.llm_settings()` resolves keys/model/base URL in one place.
- `bcwatcher/guardrails.py` holds all anti-hallucination logic (grounding,
  sanitisation, HTML allow-listing, dash/markdown cleanup) so safety is
  independent of which provider is active.
- `summarizer.py` does extract (one temperature-0 call) -> validate (guardrails)
  -> render; hard failures raise `LLMError` and the case retries.

## Phase 2 changes (recipient-tailored emails)

- One grounded extraction (`Summarizer.case_facts`) produces an audience-neutral
  fact set (current status, what's next, customer impact, technical summary).
  Rendering per audience is pure code, so notifying more audiences costs no extra
  AI calls.
- `emailfmt.render_audience_email` renders Support, Engineering, Manager, and
  Leadership views; each shows only the facts relevant to that audience
  (leadership omits technical detail and comment bodies).
- Delivery is routed by `Config.audience_recipients()` from per-audience env lists
  (`EMAIL_RECIPIENTS_SUPPORT/DEV/MANAGER/LEADERSHIP`). With none set, the watcher
  falls back to the single general update to `EMAIL_RECIPIENTS`.
- `Mailer.send` accepts a per-message recipient override so each audience email
  goes only to its list.
