# Phase 4 Sign-off - RCA approval workflow

## Scope delivered

- Closing a business-critical case no longer emails the RCA straight to
  stakeholders. The RCA is generated once and queued for engineering sign-off
  (`bcwatcher/rca_store.py`, persisted to `rca_queue.json`).
- State machine `pending_approval -> approved -> sent` (plus
  `pending_approval -> rejected`). Records are keyed by case root so re-scans
  update the same record, and an already-`sent` RCA is never resurrected or
  resent.
- `bcwatcher/rca_service.py` holds Flask-free approve/reject logic. `approve()`
  broadcasts to `Config.rca_recipients()` (dedicated `EMAIL_RECIPIENTS_RCA`,
  falling back to `EMAIL_RECIPIENTS`) and marks the record `sent`, recording the
  approver and timestamps. Any approver edit is re-sanitised through the Phase 1
  guardrails before it goes out.
- `emailfmt.render_rca_email` is the single reusable RCA wrapper, shared by the
  scanner's legacy immediate-send path and the approval service.
- Dashboard: a "Pending RCA approvals" panel with per-RCA preview and
  Approve/Reject actions, plus a `rca_approval_required` toggle (default on).
  Backed by `/api/rca`, `/api/rca/<id>/approve`, `/api/rca/<id>/reject`.
- Turning the approval toggle off restores the previous immediate-send behavior
  (backward compatible).

## Verification (local)

- `ruff check .` - all checks passed.
- `pytest` - full suite green (69 tests), including new RCA store state-machine,
  approval-service (send/reject/edit-sanitisation/idempotency), and scanner
  enqueue-vs-direct-send tests.

## Acceptance checklist

- [ ] A closing case appears in the dashboard "Pending RCA approvals" panel and
      is NOT emailed until approved.
- [ ] Approve broadcasts to the RCA recipient list and marks the record sent.
- [ ] Reject records the reason and removes the item from the pending panel.
- [ ] Approver edits are sanitised (no script/onclick) before broadcast.
- [ ] With approval turned off, RCAs send immediately as before.
- [ ] A re-scan does not resend an already-sent RCA.

## Sign-off

- Engineering lead: ________________   Date: _______
- Product owner:   ________________   Date: _______

After both sign-offs, tag the commit `phase-4-signed`.
