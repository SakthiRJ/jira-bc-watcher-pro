# Phase 0 Sign-off - Baseline hardening and test harness

## Scope delivered
- Fixed scan-loop reliability: per-case try/except around AI + `mailer.send(...)` in
  `scanner.py`; failed cases do not abort the cycle and keep their state pointers to
  retry next cycle.
- Pinned exact dependency versions (`requirements.txt`, `requirements-dev.txt`).
- Added pytest suite and fixtures under `tests/`.
- Baseline unit tests for `grouping.py` and `state.py`.
- Golden grouping snapshot (`tests/golden/grouping_default.json`) as the Phase 5
  regression lock.
- Fault-injection test proving one failed case does not stop others or lose state.
- CI (`.github/workflows/ci.yml`) running ruff + pytest.
- Docs scaffold (`docs/`).

## Verification (local)
- `ruff check .` - all checks passed.
- `pytest` - 13 passed.

## Acceptance checklist
- [ ] CI is green on main.
- [ ] Reliability bug demonstrably fixed (fault-injection test + log evidence).
- [ ] Dependencies pinned and reproducible install verified in CI.

## Sign-off
- Engineering lead: ______________________  Date: __________
- Product owner:   ______________________  Date: __________

After both sign-offs, tag the commit `phase-0-signed`.
