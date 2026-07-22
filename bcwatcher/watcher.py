"""Main watcher.

One "cycle" does the following:
  1. Load open + recently-closed business-critical tickets in the scope projects.
  2. Pull in any linked in-scope partner tickets (e.g. a CON dev ticket linked
     to a T3 support ticket) and group linked tickets into single logical cases.
  3. For known cases with a new human comment, email a consolidated AI progress
     update to stakeholders.
  4. For cases whose ticket has just been closed, email an AI-written RCA.

First time it runs (or whenever it sees a brand-new ticket) it silently records
a baseline so it never floods stakeholders with historical activity.

Run once (for Task Scheduler):   python watcher.py
Run continuously (for a demo):    python watcher.py --loop
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from bcwatcher.config import config
from bcwatcher.grouping import build_groups
from bcwatcher.jira_client import Comment, Issue, JiraClient, in_scope
from bcwatcher.mailer import Mailer
from bcwatcher.state import State
from bcwatcher.summarizer import Summarizer


def _force_utf8_output() -> None:
    """Windows consoles default to cp1252 and crash on emoji in Jira data."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


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


class Watcher:
    def __init__(self) -> None:
        self.cfg = config
        self.jira = JiraClient(config)
        self.summarizer = Summarizer(config)
        self.mailer = Mailer(config)
        self.state = State(config.state_file)

    def run_cycle(self) -> None:
        log("Fetching business-critical tickets...")
        open_issues = self.jira.business_critical_open()
        closed_issues = self.jira.business_critical_recently_closed()
        bc_keys = {i.key for i in open_issues} | {i.key for i in closed_issues}

        issues: dict[str, Issue] = {}
        for issue in open_issues + closed_issues:
            issues[issue.key] = issue

        # Pull in linked in-scope partners we have not already loaded.
        for issue in list(issues.values()):
            for linked in in_scope(issue.linked_keys, self.cfg.projects):
                if linked not in issues:
                    partner = self.jira.get_issue(linked)
                    if partner:
                        issues[partner.key] = partner

        groups = build_groups(issues, self.cfg.projects)
        log(f"Loaded {len(issues)} tickets in {len(groups)} case(s); {len(bc_keys)} business critical.")

        known_before = self.state.known_keys()
        prior_status = {k: self.state.status_category(k) for k in known_before}
        comment_cache: dict[str, list[Comment]] = {}

        # Baseline any ticket we have never seen before (no emails).
        for key, issue in issues.items():
            if key not in known_before:
                self._baseline(issue, comment_cache)

        rca_group_roots: set[str] = set()

        # -- RCA on closure -------------------------------------------------
        for issue in closed_issues:
            key = issue.key
            if key not in known_before:
                continue  # freshly baselined above
            if self.state.rca_sent(key):
                continue
            if prior_status.get(key) == "done":
                continue  # was already closed when we last looked
            group = self._group_of(key, groups)
            self._send_rca(issue, group, comment_cache)
            self.state.mark_rca_sent(key)
            rca_group_roots.add(group[0].key)

        # -- Progress updates ----------------------------------------------
        for group in groups:
            root = group[0].key
            if root in rca_group_roots:
                continue  # closure already reported this case
            if not any(not m.is_done for m in group):
                continue  # whole case is done, nothing active to report
            known_members = [m for m in group if m.key in known_before]
            if not known_members:
                continue

            new_comments: list[Comment] = []
            for member in known_members:
                last_time = parse_dt(self.state.last_comment_time(member.key))
                for c in self._comments(member.key, comment_cache):
                    if self.cfg.human_only and not c.is_human:
                        continue
                    if parse_dt(c.created) > last_time:
                        new_comments.append(c)

            if new_comments:
                new_comments.sort(key=lambda c: c.created)
                primary = self._primary(group, bc_keys)
                self._send_progress(primary, group, new_comments)

        # -- Advance pointers + statuses for known members ------------------
        for key, issue in issues.items():
            if key in known_before:
                comments = self._comments(key, comment_cache)
                if comments:
                    newest = comments[-1]
                    self.state.set_last_comment(key, newest.id, newest.created)
                self.state.set_status_category(key, issue.status_category)

        self.state.mark_initialized()
        self.state.save()
        log("Cycle complete.")

    # -- actions ------------------------------------------------------------
    def _send_progress(self, primary: Issue, group: list[Issue], new_comments: list[Comment]) -> None:
        keys = ", ".join(i.key for i in group)
        log(f"Progress update for {keys} ({len(new_comments)} new comment(s)).")
        subject, body = self.summarizer.progress_update(primary, group, new_comments)
        self.mailer.send(subject, body, self.cfg.jira_base_url, [(i.key, i.summary) for i in group])

    def _send_rca(self, primary: Issue, group: list[Issue], cache: dict[str, list[Comment]]) -> None:
        keys = ", ".join(i.key for i in group)
        log(f"RCA for closed case {keys}.")
        all_comments: list[Comment] = []
        for member in group:
            all_comments.extend(self._comments(member.key, cache))
        all_comments.sort(key=lambda c: c.created)
        subject, body = self.summarizer.rca(primary, group, all_comments)
        self.mailer.send(subject, body, self.cfg.jira_base_url, [(i.key, i.summary) for i in group])

    # -- helpers ------------------------------------------------------------
    def _baseline(self, issue: Issue, cache: dict[str, list[Comment]]) -> None:
        comments = self._comments(issue.key, cache)
        if comments:
            newest = comments[-1]
            self.state.set_last_comment(issue.key, newest.id, newest.created)
        else:
            self.state.set_last_comment(issue.key, None, None)
        self.state.set_status_category(issue.key, issue.status_category)
        if issue.is_done:
            self.state.mark_rca_sent(issue.key)
        log(f"Baselined {issue.key} (status={issue.status}).")

    def _comments(self, key: str, cache: dict[str, list[Comment]]) -> list[Comment]:
        if key not in cache:
            cache[key] = self.jira.get_comments(key)
        return cache[key]

    @staticmethod
    def _group_of(key: str, groups: list[list[Issue]]) -> list[Issue]:
        for group in groups:
            if any(m.key == key for m in group):
                return group
        return []

    @staticmethod
    def _primary(group: list[Issue], bc_keys: set[str]) -> Issue:
        active_bc = [m for m in group if m.key in bc_keys and not m.is_done]
        if active_bc:
            return active_bc[0]
        bc = [m for m in group if m.key in bc_keys]
        return bc[0] if bc else group[0]


def _send_test_email() -> int:
    if not config.dry_run:
        missing = [k for k, v in {
            "SMTP_HOST": config.smtp_host,
            "SMTP_FROM": config.smtp_from,
            "EMAIL_RECIPIENTS": ",".join(config.recipients),
        }.items() if not v]
        if missing:
            log(f"Cannot send test email, missing: {', '.join(missing)}")
            return 1
    mailer = Mailer(config)
    body = (
        "<p>This is a <strong>test email</strong> from the Jira Business-Critical "
        "Watcher. If you can read this, SMTP is configured correctly.</p>"
    )
    log(f"Sending test email (DRY_RUN={config.dry_run}) to {', '.join(config.recipients) or '(none)'}...")
    try:
        mailer.send("[Test] Jira BC Watcher SMTP check", body, config.jira_base_url, [])
    except Exception as exc:  # noqa: BLE001
        log(f"SMTP send failed: {exc}")
        return 1
    log("Test email step completed." if config.dry_run else "Test email sent.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Jira business-critical watcher")
    parser.add_argument("--loop", action="store_true", help="run continuously using POLL_INTERVAL_MINUTES")
    parser.add_argument("--test-email", action="store_true", help="send one sample email to verify SMTP, then exit")
    args = parser.parse_args()

    _force_utf8_output()

    if args.test_email:
        return _send_test_email()

    problems = config.validate()
    if problems:
        log("Configuration problems found:")
        for p in problems:
            log(f"  - {p}")
        log("Fix these in your .env file (copy .env.example) and try again.")
        return 1

    log(
        f"Mode={'LOOP' if args.loop else 'ONCE'} | DRY_RUN={config.dry_run} | "
        f"projects={','.join(config.projects)} | priority='{config.priority}'"
    )
    watcher = Watcher()

    if not args.loop:
        watcher.run_cycle()
        return 0

    interval = max(1, config.poll_interval_minutes) * 60
    log(f"Looping every {config.poll_interval_minutes} minute(s). Ctrl+C to stop.")
    while True:
        try:
            watcher.run_cycle()
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            log(f"Cycle error: {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
