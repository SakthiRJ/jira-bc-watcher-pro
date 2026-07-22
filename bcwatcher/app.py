"""Dashboard + scheduler for the Jira Business-Critical Watcher.

This is the single process you keep running. It:

  * serves a web dashboard (http://127.0.0.1:5000 by default) that lists every
    scanned business-critical case with its Description, Current (AI) Status,
    Last Update and What's next,
  * runs the scan automatically on a timer (interval configurable from the
    dashboard, no restart needed),
  * sends one consolidated end-of-day digest email at a configurable time, and
  * lets you trigger a scan or the digest on demand.

Run it:   python app.py
Then open the URL it prints. Keep this process running (see setup_dashboard_task.ps1
to auto-start it at logon) and the scanning + emailing happen on their own.
"""
from __future__ import annotations

import os
import sys
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from bcwatcher import store
from bcwatcher.config import config
from bcwatcher.digest import send_digest
from bcwatcher.scanner import run_scan

SCAN_JOB_ID = "bc_scan"
DIGEST_JOB_ID = "bc_digest"


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
scheduler = BackgroundScheduler(daemon=True)


# --------------------------------------------------------------------------
# Scheduled jobs
# --------------------------------------------------------------------------
def _scheduled_scan() -> None:
    try:
        run_scan(reason="scheduled")
    except Exception as exc:  # noqa: BLE001 - never kill the scheduler thread
        log(f"Scheduled scan error: {exc}")


def _scheduled_digest() -> None:
    try:
        result = send_digest(scan_first=True, reason="scheduled")
        log(f"End-of-day digest sent (dry_run={result['dry_run']}, open={result['open_cases']}).")
    except Exception as exc:  # noqa: BLE001
        log(f"Scheduled digest error: {exc}")


def apply_schedule(settings: dict) -> None:
    """(Re)configure both jobs from the current settings. Safe to call repeatedly."""
    interval = max(1, int(settings.get("poll_interval_minutes", 5)))
    scheduler.add_job(
        _scheduled_scan,
        trigger="interval",
        minutes=interval,
        id=SCAN_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    if scheduler.get_job(DIGEST_JOB_ID):
        scheduler.remove_job(DIGEST_JOB_ID)
    if settings.get("digest_enabled", True):
        scheduler.add_job(
            _scheduled_digest,
            trigger="cron",
            hour=int(settings.get("eod_hour", 19)),
            minute=int(settings.get("eod_minute", 0)),
            id=DIGEST_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    if settings.get("digest_enabled", True):
        digest_desc = "ON @ %02d:%02d" % (
            int(settings.get("eod_hour", 19)),
            int(settings.get("eod_minute", 0)),
        )
    else:
        digest_desc = "OFF"
    log(f"Schedule applied: scan every {interval} min; digest {digest_desc}.")


def _next_run_iso(job_id: str) -> str | None:
    job = scheduler.get_job(job_id)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/results")
def api_results():
    snapshot = store.load_results()
    snapshot["schedule"] = {
        "next_scan": _next_run_iso(SCAN_JOB_ID),
        "next_digest": _next_run_iso(DIGEST_JOB_ID),
    }
    # Re-read .env so DRY_RUN changes take effect without a restart.
    load_dotenv(override=True)
    snapshot["dry_run"] = os.getenv("DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "on"}
    snapshot["jira_base_url"] = config.jira_base_url
    return jsonify(snapshot)


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        allowed = {
            "poll_interval_minutes",
            "realtime_emails",
            "rca_emails",
            "digest_enabled",
            "eod_hour",
            "eod_minute",
        }
        updates = {k: v for k, v in payload.items() if k in allowed}
        settings = store.save_settings(updates)
        apply_schedule(settings)
        return jsonify({"ok": True, "settings": settings})
    return jsonify(store.load_settings())


@app.route("/api/scan", methods=["POST"])
def api_scan():
    threading.Thread(target=_scheduled_scan, daemon=True).start()
    return jsonify({"ok": True, "message": "Scan started."})


@app.route("/digest-preview")
def digest_preview():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dry_run_email.html")
    if not os.path.exists(path):
        return "<p>No digest preview available yet. Click <b>Send digest now</b> first.</p>", 404
    return open(path, encoding="utf-8").read(), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/digest", methods=["POST"])
def api_digest():
    scan_first = bool((request.get_json(silent=True) or {}).get("scan_first", False))
    try:
        result = send_digest(scan_first=scan_first, reason="manual")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, **result})


# --------------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------------
def _bootstrap() -> None:
    # Clear any stale scanning flag left by a previous crash or forced kill.
    store.set_scanning(False)
    settings = store.load_settings()
    scheduler.start()
    apply_schedule(settings)
    # Kick off an initial scan in the background if we have no snapshot yet.
    if not store.load_results().get("cases"):
        log("No previous snapshot; running an initial scan in the background...")
        threading.Thread(target=_scheduled_scan, daemon=True).start()


def main() -> int:
    _force_utf8_output()
    problems = config.validate()
    if problems:
        log("Configuration problems found:")
        for p in problems:
            log(f"  - {p}")
        log("Fix these in your .env file and try again.")
        return 1

    host = "127.0.0.1"
    port = 5000
    _bootstrap()
    log(f"Dashboard running at http://{host}:{port}  (DRY_RUN={config.dry_run})")
    # use_reloader=False so the scheduler is not started twice.
    app.run(host=host, port=port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
