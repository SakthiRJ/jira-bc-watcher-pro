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

## Phase 4 changes (RCA approval workflow)

- When a case closes, the RCA is generated once and parked in a persistent queue
  (`bcwatcher/rca_store.py`, `rca_queue.json`) as `pending_approval` instead of
  being emailed. State machine: `pending_approval -> approved -> sent`, or
  `pending_approval -> rejected`. Records are keyed by case root, so re-scans
  update the same record and an already-`sent` RCA is never resurrected.
- `bcwatcher/rca_service.py` is the Flask-free approval logic: `approve()`
  broadcasts to `Config.rca_recipients()` (dedicated `EMAIL_RECIPIENTS_RCA` list,
  else `EMAIL_RECIPIENTS`) and marks the record `sent`; `reject()` records the
  reason. Approver edits are re-run through the guardrails before sending.
- `emailfmt.render_rca_email` is the single reusable RCA wrapper (shared by the
  scanner legacy direct-send path and the approval service).
- The dashboard gains a "Pending RCA approvals" panel with per-RCA preview and
  Approve/Reject actions, backed by `/api/rca`, `/api/rca/<id>/approve`, and
  `/api/rca/<id>/reject`. A `rca_approval_required` setting (default on) gates the
  workflow; turning it off restores the immediate-send behavior.

## Phase 3 changes (subscriptions + channel abstraction)

- `bcwatcher/subscriptions.py` stores per-recipient subscriptions
  (`subscriptions.json`): which events a person wants (`realtime`, `rca`,
  `digest`), an audience template, an optional project/priority scope, and a
  delivery channel. `add()` applies self-subscribe guardrails (email format,
  known audience/channel, non-empty events, project allow-listing, a cap) so the
  dashboard form can be exposed safely.
- Routing is resolved by `resolve(event, case)` and `audience_map(event, case)`;
  scope matching is by case project (from member keys) and priority.
- `bcwatcher/channels/` is the delivery abstraction: a `Channel` base plus an
  `EmailChannel` over the SMTP `Mailer`. `bcwatcher/notifier.py` groups
  subscriber records by channel and dispatches; an unregistered channel is
  reported as skipped rather than raising, so a future Teams channel (Phase 7)
  drops in without touching the scan/RCA/digest code.
- Progress updates (`scanner`), RCA broadcast (`rca_service`), and the digest
  (`digest`) now resolve subscribers first and fall back to the Phase 2/4
  `EMAIL_RECIPIENTS*` lists when none are configured (backward compatible).
- Timing (scan interval, digest time) stays a tenant-level dashboard setting;
  subscriptions only govern who gets what, not when.

## Phase 5 changes (multi-tenant config, configurable grouping, secrets, preflight)

- Decision: no database. The working set is a handful of open BC cases that clear
  when their RCA is generated - kilobytes, single-writer, regenerated each scan.
  Storage stays flat-file; a storage abstraction plus SQLite/Postgres backends are
  documented for later (audit history / multi-node HA) but not required.
- `bcwatcher/tenants.py`: a `Tenant` carries the Jira connection, projects,
  priorities, grouping policy (+ per-project overrides), recipients, and schedule.
  `load_tenants()` reads `TENANTS_FILE` (JSON); with no file it synthesizes a
  single `default` tenant from `Config`, so existing single-tenant runs are
  unchanged. A `Tenant` is config-compatible enough to drive `JiraClient` later.
- `bcwatcher/grouping.py` is now policy-driven. `GroupingPolicy` gates each union
  edge and the display rollup, resolved per project via `tenant.grouping_for()`.
  The default policy reproduces the original behavior (the Phase 0 golden snapshot
  is unchanged). The scanner passes the active tenant's policy.
- `bcwatcher/secrets.py`: `resolve_secret()` handles `env:`, `enc:` (Fernet via
  `SECRETS_KEY`), and literal values; `cryptography` is only needed for `enc:`.
- `jira_client` builds `priority in (...)` for multiple configured priorities,
  else `priority = "..."` (back-compat).
- `bcwatcher/preflight.py` (`python -m bcwatcher.preflight`) validates config,
  tenants, LLM, Jira auth, and SMTP, with a `--no-net` offline mode; it exits
  non-zero on any hard FAIL so it can gate a deployment.
- Auth stays token-only (decision); OAuth deferred. Concurrent multi-tenant
  execution (per-tenant schedulers/state) is the documented next step.
