# Phase 3 Sign-off - Notification subscriptions + channel abstraction

## Scope delivered

- Per-recipient subscriptions (`bcwatcher/subscriptions.py`, persisted to
  `subscriptions.json`). A subscription records email, name, audience template,
  delivery channel, the events wanted (`realtime` / `rca` / `digest`), and an
  optional project/priority scope.
- Self-subscribe guardrails in `subscriptions.add()`: valid email required,
  audience and channel must be known values, at least one event, unknown
  projects dropped (allow-listed against `config.projects`), strings sanitised,
  and a subscription cap. Invalid input returns HTTP 400 from the API.
- Routing resolution: `resolve(event, case)` and `audience_map(event, case)`,
  matching by case project (from member keys) and priority.
- Channel abstraction (`bcwatcher/channels/`): `Channel` base + `EmailChannel`
  over the SMTP `Mailer`. `bcwatcher/notifier.py` groups subscribers by channel
  and dispatches; an unregistered channel is reported as skipped (no raise), so
  Microsoft Teams (Phase 7) can be added without touching routing code.
- Integration with backward-compatible fallback: progress updates (`scanner`),
  RCA broadcast (`rca_service`), and the end-of-day digest (`digest`) resolve
  subscribers first and fall back to the `EMAIL_RECIPIENTS*` env lists when no
  subscriptions exist.
- Dashboard: a "Notification subscriptions" panel to add/update/remove
  subscriptions, backed by `/api/subscriptions` (GET/POST) and
  `/api/subscriptions/<email>` (DELETE).
- Timing (scan interval, digest time) remains a tenant-level setting;
  subscriptions govern only who gets what, not when.

## Verification (local)

- `ruff check .` - all checks passed.
- `pytest` - full suite green (89 tests), including subscription store +
  guardrails + scope resolution, notifier channel routing/dedupe/unknown-channel,
  and scanner progress routing with the env fallback.

## Acceptance checklist

- [ ] A dashboard subscription receives the correct audience template for the
      events and project scope it selected.
- [ ] Out-of-scope subscribers are not notified; env fallback still works when no
      subscriptions match.
- [ ] Invalid subscribe input (bad email, unknown audience, no events) is
      rejected with a clear message.
- [ ] RCA broadcast and digest honor subscriptions when present, else fall back.
- [ ] Timing changes remain tenant-level (no per-user timing introduced).

## Sign-off

- Engineering lead: ________________   Date: _______
- Product owner:   ________________   Date: _______

After both sign-offs, tag the commit `phase-3-signed`.
