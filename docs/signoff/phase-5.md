# Phase 5 Sign-off - Multi-tenant config, configurable grouping, secrets, preflight

## Scope delivered

- No database. Given the data is tiny and mostly ephemeral (the board clears when
  an RCA is generated), storage stays flat-file. A storage abstraction / SQLite /
  Postgres are documented as drop-in options for later if audit history or
  multi-node HA is ever needed.
- Multi-tenant config model (`bcwatcher/tenants.py`): per-tenant Jira connection,
  projects, priorities, grouping policy (with per-project overrides), recipients,
  and schedule. Loaded from `TENANTS_FILE` (JSON); when absent, a single
  `default` tenant is synthesized from `.env` so single-tenant deployments and
  the first test need no extra setup.
- Configurable per-project grouping (`bcwatcher/grouping.py`): `GroupingPolicy`
  gates the union edges (cross-project links, Epic parent field, same-project
  Epic links) and the display rollup, per project. Default policy reproduces the
  original behavior, so the Phase 0 golden snapshot still passes. Also fixed a
  latent broken import in the `display_keys` fallback.
- Encrypted secrets (`bcwatcher/secrets.py`): tenant secret values may be
  `env:VAR`, `enc:<fernet-token>` (via `SECRETS_KEY`), or literal. `cryptography`
  is only needed for `enc:` values.
- Multiple priorities: `jira_client` builds `priority in (...)` when more than one
  priority is configured, else `priority = "..."` (back-compat).
- Preflight command (`python -m bcwatcher.preflight`): validates config, each
  tenant, the LLM key/model, Jira auth, and SMTP (when `DRY_RUN` is off), with a
  `--no-net` offline mode. Non-zero exit on any hard FAIL so it can gate rollout.
- Auth stays token-only (per decision); OAuth deferred.
- Read-only `GET /api/tenants` with secrets redacted.
- First full test runbook: `docs/FIRST_TEST.md`.

## Deferred (documented, not in this pass)

- Concurrent multi-tenant execution (per-tenant schedulers + namespaced runtime
  state). The config model is built for it; the runtime loop is the next step and
  does not change the config format.
- SQLite/Postgres storage backends and a live Jira OAuth 3LO handshake.

## Verification (local)

- `ruff check .` - all checks passed.
- `pytest` - full suite green (117 tests), including grouping policy (engine +
  rollup + per-project override), secrets (env/literal/encrypt round-trip/error),
  tenants (default-from-config, file parsing, validation, redaction), JQL
  priority clause, and preflight report/exit codes.
- `python -m bcwatcher.preflight --no-net` - config/llm/tenants all PASS.

## Acceptance checklist

- [ ] Preflight passes against the real Jira/LLM/SMTP before the full test.
- [ ] Default (single-tenant) run behaves exactly as before.
- [ ] A `tenants.json` with per-project grouping overrides changes grouping as
      expected without touching code.
- [ ] `enc:` secrets decrypt with the configured `SECRETS_KEY`.
- [ ] `GET /api/tenants` never exposes a raw token.

## Sign-off

- Engineering lead: ________________   Date: _______
- Product owner:   ________________   Date: _______

After both sign-offs, tag the commit `phase-5-signed`.
