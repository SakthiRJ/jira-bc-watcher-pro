# Phase 2 Sign-off - Recipient-tailored emails

## Scope delivered

- One grounded extraction per case (`Summarizer.case_facts`) yields an
  audience-neutral fact set: current status, what's next, customer impact, and
  technical summary. All fields pass the Phase 1 guardrails.
- Audience templates (`emailfmt.render_audience_email`) for Support, Engineering,
  Manager, and Leadership. Each renders only the facts relevant to its audience
  (leadership omits technical detail and comment bodies), in pure code, so extra
  audiences cost no extra AI calls.
- Per-audience delivery routing via `Config.audience_recipients()` from
  `EMAIL_RECIPIENTS_SUPPORT/DEV/MANAGER/LEADERSHIP`. With none configured, the
  watcher falls back to the single general update to `EMAIL_RECIPIENTS`
  (backward compatible).
- `Mailer.send` gained an optional per-message recipient override.
- Bug fix: `digest.py` lazy import corrected to `bcwatcher.scanner` (broken by
  the Phase 0 package move).

## Verification (local)

- `ruff check .` - all checks passed.
- `pytest` - full suite green, including new audience-template, `case_facts`
  validation, and audience-routing config tests.

## Acceptance checklist

- [ ] Each audience receives a correctly scoped email in a real dry-run.
- [ ] Leadership email contains no technical detail or raw comment text.
- [ ] Fallback to `EMAIL_RECIPIENTS` confirmed when no audience lists are set.
- [ ] Single extraction per case confirmed (no extra AI calls per audience).

## Sign-off

- Engineering lead: ________________   Date: _______
- Product owner:   ________________   Date: _______

After both sign-offs, tag the commit `phase-2-signed`.
