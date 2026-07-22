# Jira Business-Critical Watcher - Dashboard Edition

An AI-assisted watcher for Jira Cloud (`aphinity.atlassian.net`). It polls the
**business-critical** tickets in the `CON`, `T3`, and `CL` projects and:

- serves a **live web dashboard** (`http://127.0.0.1:5000`) showing every case
  with its Description, AI-generated Current Status, Last Update and What's next,
- runs the scan automatically on a **configurable timer** (set from the dashboard
  with no restart needed),
- sends a **consolidated end-of-day digest email** at a configurable time,
- emails a **real-time AI progress update** to stakeholders whenever a case gets
  a new human comment, and
- emails an **AI-written Root Cause Analysis (RCA)** when a case is closed.

A T3 support ticket and its linked CON development ticket are treated as a
**single case**. CON sub-tickets that belong to the same Epic are collapsed to
the Epic key only - so the display always shows the Epic (e.g. `CON-2004 + T3-1412`),
never a long list of individual sub-tickets.

## How it works

Each run ("cycle"):

1. Runs one JQL: `project in (CON, T3, CL) AND priority = "Business Critical" AND statusCategory != Done`
   plus a second query for tickets closed in the last few days.
2. Pulls in any linked in-scope partner tickets and groups linked tickets into
   one logical case (union-find over Jira issue links).
3. For a case with a **new human comment** since the last cycle, an LLM (via
   Groq) writes a short stakeholder update, which is emailed.
4. For a case whose ticket just moved to a Done status, the LLM writes an RCA,
   which is emailed.

State is kept in `state.json` so the same comment is never emailed twice. The
first time it sees any ticket it records a silent baseline, so it never floods
stakeholders with historical activity. It only emails on genuinely new activity
after that.

## Requirements

- Python 3.13 (this repo uses a local virtual environment in `.venv`).
- A Jira API token, a Groq API key, and SMTP details for sending mail.

> Note on this machine: the `python` on PATH is a broken 3.11 install. Use
> `C:\python.exe` (3.13) as the base interpreter, which is what the `.venv`
> below was created from.

## Setup

1. Create the virtual environment and install dependencies (already done if
   `.venv` exists):

```powershell
C:\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. Create your config:

```powershell
Copy-Item .env.example .env
```

3. Edit `.env` and fill in:
   - `JIRA_EMAIL` + `JIRA_API_TOKEN` (create the token at
     https://id.atlassian.com/manage-profile/security/api-tokens).
   - `GROQ_API_KEY` (and optionally `GROQ_MODEL`).
   - `SMTP_*` and `EMAIL_RECIPIENTS` for the stakeholder mailing list.
   - Keep `DRY_RUN=true` for your first runs; emails are printed to the console
     / `watcher.log` instead of being sent. Set it to `false` when ready.

## Running the dashboard (recommended)

Start the dashboard - this is the only process you need to keep running:

```powershell
.\.venv\Scripts\python.exe app.py
```

Then open **http://127.0.0.1:5000** in your browser. The dashboard:

- scans automatically on the configured interval,
- shows every case with Description / Current Status / Last Update / What's next,
- lets you change the scan interval and EOD digest time from the Settings panel
  (takes effect immediately, no restart needed),
- has a **Scan now** button to trigger an immediate scan, and
- has a **Send digest now** button to email the consolidated snapshot on demand.

Output is appended to `dashboard.log`.

## Auto-start at logon (Windows Task Scheduler)

Register the dashboard to start automatically when you log on:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_dashboard_task.ps1
```

- Start it immediately after registering: `Start-ScheduledTask -TaskName "JiraBCDashboard"`.
- Remove it: `Unregister-ScheduledTask -TaskName "JiraBCDashboard" -Confirm:$false`.

## Running without the dashboard (legacy single-cycle mode)

```powershell
.\.venv\Scripts\python.exe watcher.py        # one cycle
.\.venv\Scripts\python.exe watcher.py --loop # continuous loop
```

## Demo / video script (AI adoption challenge)

1. Show `.env` with `POLL_INTERVAL_MINUTES=1` and `DRY_RUN=true`, and start
   `watcher.py --loop`. First cycle baselines silently.
2. Add a comment to a real business-critical ticket (e.g. `CON-2084`). Within a
   minute, show the AI-composed progress update appear in `watcher.log`
   (or the stakeholder inbox once `DRY_RUN=false`).
3. Show the next cycle staying silent because there is no new comment.
4. Move a business-critical test ticket to a Done status. Show the AI-written
   RCA appear on the next cycle.

## Configuration reference

See `.env.example` for every setting. Key ones:

| Setting | Meaning |
|---|---|
| `JIRA_PROJECTS` | Scope projects (default `CON,T3,CL`). |
| `JIRA_PRIORITY` | Priority that marks a case business critical (default `Business Critical`). |
| `POLL_INTERVAL_MINUTES` | Loop interval / scheduler cadence. |
| `CLOSED_LOOKBACK_DAYS` | How far back to look for freshly closed tickets. |
| `HUMAN_ONLY` | Only comments from real people trigger emails (skips Automation/bots). |
| `DRY_RUN` | Print emails instead of sending them. |

Dashboard settings (stored in `settings.json`, editable live from the UI):

| Setting | Meaning |
|---|---|
| `poll_interval_minutes` | How often the auto-scan runs (default 5). |
| `realtime_emails` | Email each new comment as it arrives. |
| `rca_emails` | Email an RCA when a case closes. |
| `digest_enabled` | Send the consolidated end-of-day digest email. |
| `eod_hour` / `eod_minute` | Time to send the daily digest (24 h clock, default 19:00). |

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask dashboard + embedded APScheduler (scan timer + EOD digest). |
| `scanner.py` | Core scan logic; writes `results.json` for the dashboard. |
| `digest.py` | End-of-day consolidated digest email. |
| `emailfmt.py` | HTML email formatter (Description, Current Status, Last Update, What's next). |
| `store.py` | Persists `settings.json` and `results.json`. |
| `grouping.py` | Groups linked tickets into cases; rolls CON sub-tickets up to their Epic. |
| `jira_client.py` | Jira REST client (search, comments, linked issues). |
| `summarizer.py` | Groq AI progress + RCA generation. |
| `mailer.py` | SMTP sender with dry-run mode. |
| `state.py` | Persistent per-ticket state in `state.json`. |
| `config.py` | Loads and validates configuration from `.env`. |
| `watcher.py` | Legacy single-cycle / loop runner (no dashboard). |
| `setup_dashboard_task.ps1` | Registers dashboard as a Windows logon task. |
| `run_dashboard.ps1` | Runner script used by the scheduled task. |
| `setup_task.ps1` / `run_watcher.ps1` | Legacy Task Scheduler setup for `watcher.py`. |
