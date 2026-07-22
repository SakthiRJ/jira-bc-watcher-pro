"""Demo helper to reliably trigger emails on camera. Does NOT modify Jira.

Progress update (replays a ticket's latest comment as if it were new):
    python demo_trigger.py CON-2084

RCA (replays a real, recently-closed business-critical ticket as a fresh close):
    python demo_trigger.py --rca            # auto-picks a recently closed BC case
    python demo_trigger.py --rca CON-2085   # or name one

Both run a single watcher cycle afterwards.
"""
import sys

from bcwatcher.config import config
from bcwatcher.jira_client import JiraClient
from bcwatcher.state import State
from bcwatcher.watcher import Watcher, _force_utf8_output, log


def _progress(key: str) -> int:
    jira = JiraClient(config)
    comments = jira.get_comments(key)
    if not comments:
        log(f"{key} has no comments to replay. Pick a ticket with comments.")
        return 1
    state = State(config.state_file)
    if len(comments) >= 2:
        prev = comments[-2]
        state.set_last_comment(key, prev.id, prev.created)
    else:
        state.set_last_comment(key, None, None)
    state.save()
    log(f"Set {key} so its latest comment counts as new. Running one cycle (DRY_RUN={config.dry_run})...")
    Watcher().run_cycle()
    return 0


def _rca(key: str | None) -> int:
    jira = JiraClient(config)
    closed = jira.business_critical_recently_closed()
    if not closed:
        log("No recently-closed business-critical tickets within CLOSED_LOOKBACK_DAYS. "
            "Increase CLOSED_LOOKBACK_DAYS in .env or close a BC ticket first.")
        return 1
    if key:
        target = next((i for i in closed if i.key == key), None)
        if target is None:
            log(f"{key} is not in the recently-closed set. Available: {', '.join(i.key for i in closed)}")
            return 1
    else:
        target = closed[0]
    # Make it look like it just transitioned from open to closed and was never RCA'd.
    state = State(config.state_file)
    state.set_status_category(target.key, "indeterminate")
    state.set_rca_sent(target.key, False)
    state.save()
    log(f"Set {target.key} as a fresh closure. Running one cycle (DRY_RUN={config.dry_run})...")
    Watcher().run_cycle()
    return 0


def main() -> int:
    _force_utf8_output()
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--rca":
        return _rca(args[1].strip() if len(args) > 1 else None)
    return _progress(args[0].strip())


if __name__ == "__main__":
    raise SystemExit(main())
