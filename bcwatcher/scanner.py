"""Core scan: one pass over business-critical cases.

Per scan it:
  - loads open + recently-closed BC tickets across the scope projects,
  - pulls in linked cross-project partners and parent Epics,
  - groups them into cases (Epic roll-up so sub-tickets show as their Epic),
  - for cases with a NEW human comment since last scan: generates an AI status
    and (if enabled) sends an incremental update email,
  - for in-progress cases with no new comment: marks "No update",
  - for cases that just closed: sends an AI RCA email (if enabled),
  - writes results.json (the dashboard + digest snapshot).
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from bcwatcher import rca_store, store, subscriptions, tenants
from bcwatcher.config import config
from bcwatcher.emailfmt import render_audience_email, render_progress_email, render_rca_email
from bcwatcher.grouping import build_groups, display_keys
from bcwatcher.jira_client import Comment, Issue, JiraClient, in_scope
from bcwatcher.mailer import Mailer
from bcwatcher.notifier import Notifier
from bcwatcher.state import State
from bcwatcher.summarizer import Summarizer, truncate

_scan_lock = threading.Lock()


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=timezone.utc)


def _pick_primary(members: list[Issue], bc_keys: set[str]) -> Issue:
    active_bc = [m for m in members if m.key in bc_keys and not m.is_done and not m.is_epic]
    if active_bc:
        return active_bc[0]
    bc = [m for m in members if m.key in bc_keys and not m.is_epic]
    if bc:
        return bc[0]
    non_epic = [m for m in members if not m.is_epic]
    return (non_epic or members)[0]


def run_scan(reason: str = "scheduled") -> dict:
    """Run one scan. Returns the snapshot dict that was persisted."""
    if not _scan_lock.acquire(blocking=False):
        log("Scan already running; skipping this trigger.")
        return store.load_results()
    try:
        return _run_scan_locked(reason)
    except Exception:
        _safe_clear_scanning()
        raise
    finally:
        _scan_lock.release()


def _run_scan_locked(reason: str) -> dict:
    settings = store.load_settings()
    jira = JiraClient(config)
    summarizer = Summarizer(config)
    mailer = Mailer(config)
    state = State(config.state_file)

    prev = store.load_results()
    prev_by_key = {c.get("primary_key"): c for c in prev.get("cases", [])}
    store.set_scanning(True)

    log(f"Scan start ({reason}). Fetching business-critical tickets...")
    open_issues = jira.business_critical_open()
    closed_issues = jira.business_critical_recently_closed()
    bc_keys = {i.key for i in open_issues} | {i.key for i in closed_issues}

    issues: dict[str, Issue] = {}
    for issue in open_issues + closed_issues:
        issues[issue.key] = issue

    # Cross-project linked partners
    for issue in list(issues.values()):
        for linked in in_scope(issue.linked_keys, config.projects):
            if linked not in issues:
                partner = jira.get_issue(linked)
                if partner:
                    issues[partner.key] = partner
    # Parent Epics (so we can roll sub-tickets up to them)
    for issue in list(issues.values()):
        if issue.has_epic_parent and issue.parent_key not in issues:
            epic = jira.get_issue(issue.parent_key)
            if epic:
                issues[epic.key] = epic

    tenant = tenants.default_tenant()
    groups = build_groups(issues, config.projects, tenant)
    log(f"Loaded {len(issues)} tickets in {len(groups)} case(s); {len(bc_keys)} business critical.")

    known_before = state.known_keys()
    prior_status = {k: state.status_category(k) for k in known_before}
    comment_cache: dict[str, list[Comment]] = {}

    def comments_of(key: str) -> list[Comment]:
        if key not in comment_cache:
            comment_cache[key] = jira.get_comments(key)
        return comment_cache[key]

    def baseline(issue: Issue) -> None:
        cs = comments_of(issue.key)
        if cs:
            state.set_last_comment(issue.key, cs[-1].id, cs[-1].created)
        else:
            state.set_last_comment(issue.key, None, None)
        state.set_status_category(issue.key, issue.status_category)
        if issue.is_done:
            state.mark_rca_sent(issue.key)

    for key, issue in issues.items():
        if key not in known_before:
            baseline(issue)

    # root key -> dashboard status label for a just-closed case this cycle.
    rca_roots: dict[str, str] = {}
    # Keys whose AI/email step failed this cycle. We deliberately do NOT advance
    # their state pointers below so the case is retried on the next scan instead
    # of being silently skipped.
    failed_rca_keys: set[str] = set()
    failed_update_member_keys: set[str] = set()

    # -- RCA on closure -----------------------------------------------------
    for issue in closed_issues:
        key = issue.key
        if key not in known_before or state.rca_sent(key) or prior_status.get(key) == "done":
            continue
        try:
            group = _group_of(key, groups)
            primary = _pick_primary(group, bc_keys)
            all_comments: list[Comment] = []
            for m in group:
                all_comments.extend(comments_of(m.key))
            all_comments.sort(key=lambda c: c.created)
            rca = summarizer.rca(primary, group, all_comments)
            root = group[0].key
            keys_title = " + ".join(display_keys(group, tenant))
            record = {
                "id": root,
                "primary_key": primary.key,
                "display_keys": display_keys(group, tenant),
                "summary": primary.summary,
                "subject": rca["subject"],
                "body_html": rca["body_html"],
            }
            if settings.get("rca_approval_required", True):
                # Park for engineering sign-off; do NOT broadcast yet.
                rca_store.upsert({**record, "status": rca_store.PENDING})
                rca_roots[root] = "Closed - RCA pending approval"
                log(f"RCA for {keys_title} queued for engineering approval.")
            elif settings.get("rca_emails", True):
                subject, body = render_rca_email(record, config.jira_base_url)
                mailer.send(subject, body, to=config.rca_recipients())
                rca_store.upsert(
                    {**record, "status": rca_store.SENT, "sent_at": datetime.now(timezone.utc).isoformat()}
                )
                rca_roots[root] = "Closed - RCA sent"
                log(f"RCA email for closed case {keys_title}.")
            else:
                rca_roots[root] = "Closed"
            state.mark_rca_sent(key)
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the scan
            failed_rca_keys.add(key)
            log(f"RCA failed for {key}: {exc}. Will retry next cycle.")
            continue

    # -- Cases + incremental updates ---------------------------------------
    cases_out: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for group in groups:
        root = group[0].key
        members = group
        primary = _pick_primary(members, bc_keys)
        dkeys = display_keys(members, tenant)
        active = any(not m.is_done for m in members)

        # newest human comment across members (for "Last Update")
        newest_human: Comment | None = None
        new_comments: list[Comment] = []
        for m in members:
            for c in comments_of(m.key):
                if c.is_human:
                    if newest_human is None or c.created > newest_human.created:
                        newest_human = c
                if m.key in known_before:
                    if config.human_only and not c.is_human:
                        continue
                    if parse_dt(c.created) > parse_dt(state.last_comment_time(m.key)):
                        new_comments.append(c)

        prev_case = prev_by_key.get(dkeys[0]) if dkeys else None
        case = {
            "display_keys": dkeys,
            "primary_key": dkeys[0] if dkeys else primary.key,
            "type": primary.issue_type,
            "summary": primary.summary,
            "description": truncate(primary.description, 600) or "Not stated in ticket",
            "status": primary.status,
            "status_category": primary.status_category,
            "priority": primary.priority,
            "owner": primary.assignee,
            "member_keys": [m.key for m in members],
            "last_update_author": newest_human.author if newest_human else None,
            "last_update_time": newest_human.created if newest_human else None,
            "last_update_body": truncate(newest_human.body, 220) if newest_human else None,
            "scanned_at": now_iso,
            "no_update": False,
            "current_status": "",
            "whats_next": "",
            "customer_impact": "",
            "technical_summary": "",
        }

        if root in rca_roots:
            case["current_status"] = rca_roots[root]
            case["whats_next"] = "None"
        elif new_comments:
            new_comments.sort(key=lambda c: c.created)
            try:
                facts = summarizer.case_facts(primary, members, new_comments)
                case["current_status"] = facts["current_status"]
                case["whats_next"] = facts["whats_next"]
                case["customer_impact"] = facts["customer_impact"]
                case["technical_summary"] = facts["technical_summary"]
                case["last_update_author"] = new_comments[-1].author
                case["last_update_time"] = new_comments[-1].created
                case["last_update_body"] = truncate(new_comments[-1].body, 220)
                log(f"Update for {' + '.join(dkeys)} ({len(new_comments)} new comment(s)).")
                if settings.get("realtime_emails", True) and active:
                    _send_progress_emails(mailer, case)
            except Exception as exc:  # noqa: BLE001 - one bad case must not abort the scan
                failed_update_member_keys.update(m.key for m in members)
                log(f"Update failed for {' + '.join(dkeys)}: {exc}. Will retry next cycle.")
                case["current_status"] = (prev_case or {}).get("current_status") or "Update received; see ticket for details."
                case["whats_next"] = (prev_case or {}).get("whats_next") or "Not stated in ticket"
        elif active:
            case["no_update"] = True
            case["current_status"] = (prev_case or {}).get("current_status") or "No update since last check"
            case["whats_next"] = (prev_case or {}).get("whats_next") or "Not stated in ticket"
        else:
            case["current_status"] = (prev_case or {}).get("current_status") or "Closed"
            case["whats_next"] = "None"

        cases_out.append(case)

    # -- advance pointers + statuses ---------------------------------------
    # Cases whose AI/email step failed this cycle keep their old pointers so the
    # next scan re-detects the same new comment / closure and retries.
    for key, issue in issues.items():
        if key in known_before:
            if key not in failed_update_member_keys:
                cs = comments_of(key)
                if cs:
                    state.set_last_comment(key, cs[-1].id, cs[-1].created)
            if key not in failed_rca_keys:
                state.set_status_category(key, issue.status_category)

    state.mark_initialized()
    state.save()

    cases_out.sort(key=lambda c: (c.get("status_category") == "done", c.get("primary_key", "")))
    snapshot = {"last_scan": now_iso, "scanning": False, "cases": cases_out}
    store.save_results(snapshot)
    log("Scan complete.")
    return snapshot


def _safe_clear_scanning() -> None:
    """Ensure scanning=False is written even when the scan raises."""
    try:
        snap = store.load_results()
        if snap.get("scanning"):
            snap["scanning"] = False
            store.save_results(snap)
    except Exception:  # noqa: BLE001
        pass


def _send_progress_emails(mailer: Mailer, case: dict) -> None:
    """Send recipient-tailored progress updates.

    Routing precedence:
      1. Per-recipient subscriptions (Phase 3): each audience's subscribers whose
         scope matches the case get that audience's template, delivered via their
         channel.
      2. Static per-audience env lists (Phase 2).
      3. The single general update to EMAIL_RECIPIENTS (backward compatible).
    """
    audience_subs = subscriptions.audience_map("realtime", case)
    if audience_subs:
        notifier = Notifier.with_email(mailer)
        for audience, records in audience_subs.items():
            subject, body = render_audience_email(case, audience, config.jira_base_url)
            notifier.send(records, subject, body, audience=audience, kind="update")
        return

    audiences = config.audience_recipients()
    if audiences:
        for audience, recipients in audiences.items():
            subject, body = render_audience_email(case, audience, config.jira_base_url)
            mailer.send(subject, body, to=recipients)
    else:
        subject, body = render_progress_email(case, config.jira_base_url)
        mailer.send(subject, body)


def _group_of(key: str, groups: list[list[Issue]]) -> list[Issue]:
    for group in groups:
        if any(m.key == key for m in group):
            return group
    return []
