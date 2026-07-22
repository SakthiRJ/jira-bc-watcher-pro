# Jira Business-Critical Watcher

An AI-assisted watcher for Jira Cloud that keeps stakeholders informed about
**business-critical** tickets without anyone having to babysit the boards.

It polls the business-critical tickets in a configurable set of Jira projects and:

- serves a **live web dashboard** (`http://127.0.0.1:5000`) showing every case
  with its Description, AI-generated Current Status, Last Update and What's next,
- runs the scan automatically on a **configurable timer** (set from the dashboard,
  no restart needed),
- sends a **consolidated end-of-day digest email** at a configurable time,
- emails a **real-time AI progress update** to stakeholders whenever a case gets
  a new human comment, and
- emails an **AI-written Root Cause Analysis (RCA)** when a case is closed.

Linked tickets are treated as a **single case**: a support ticket and its linked
development ticket are collapsed together, and sub-tickets that belong to the same
Epic are rolled up to the Epic key. The display always shows the Epic (e.g.
`CON-2004 + T3-1412`) instead of a long list of individual sub-tickets.

> **Status: productization baseline.** This repo is being evolved from a
> single-tenant prototype into an on-prem, multi-company product in phased steps.
> The durable architecture notes and per-phase sign-off records live in
> [`docs/`](docs/). Today it runs as a single-process app with flat-file state and
> a single Groq-backed LLM; multi-tenancy, a swappable LLM provider with
> guardrails, per-project grouping policies, and a database backend are on the
> roadmap (see [Roadmap](#roadmap)).

## How it works

Each run ("cycle"):

1. Runs one JQL over the configured scope, e.g.
   `project in (CON, T3, CL) AND priority = "Business Critical" AND statusCategory != Done`,
   plus a second query for tickets closed in the last few days.
2. Pulls in any linked in-scope partner tickets and groups them into one logical
   case (union-find over Jira issue links, with same-Epic sub-tickets rolled up).
3. For a case with a **new human comment** since the last cycle, an LLM (via Groq)
   writes a short stakeholder update, which is emailed.
4. For a case whose ticket just moved to a Done status, the LLM writes an RCA,
   which is emailed.

State is kept in `state.json` so the same comment is never emailed twice. The first
time it sees any ticket it records a silent baseline, so it never floods
stakeholders with historical activity; it only emails on genuinely new activity
after that. If the AI or email step fails for one case, that case is retried on the
next cycle and the rest of the scan still completes.

## Requirements

- Python 3.13 (this repo uses a local virtual environment in `.venv`).
- A Jira API token, a Groq API key, and SMTP details for sending mail.

## Setup

1. Create the virtual environment and install runtime dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. Create your config:

```powershell
Copy-Item .env.example .env
```

3. Edit `.env` and fill in:
   - `JIRA_BASE_URL` (e.g. `https://your-company.atlassian.net`).
   - `JIRA_EMAIL` + `JIRA_API_TOKEN` (create the token at
     https://id.atlassian.com/manage-profile/security/api-tokens).
   - `JIRA_PROJECTS` + `JIRA_PRIORITY` to define what counts as a business-critical
     case for your organisation.
   - `GROQ_API_KEY` (and optionally `GROQ_MODEL`).
   - `SMTP_*` and `EMAIL_RECIPIENTS` for the stakeholder mailing list.
   - Keep `DRY_RUN=true` for your first runs; emails are printed to the console
     instead of being sent. Set it to `false` when ready.

## Running the dashboard (recommended)

Start the dashboard - this is the only process you need to keep running. Run it as
a module from the repo root:

```powershell
.\.venv\Scripts\python.exe -m bcwatcher.app
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
powershell -ExecutionPolicy Bypass -File .\scripts\setup_dashboard_task.ps1
```

- Start it immediately after registering: `Start-ScheduledTask -TaskName "JiraBCDashboard"`.
- Remove it: `Unregister-ScheduledTask -TaskName "JiraBCDashboard" -Confirm:$false`.

The helper scripts in `scripts/` resolve the repo root automatically, so they work
from wherever the task runs them.

## Running without the dashboard (legacy single-cycle mode)

```powershell
.\.venv\Scripts\python.exe -m bcwatcher.watcher        # one cycle
.\.venv\Scripts\python.exe -m bcwatcher.watcher --loop # continuous loop
```

## Configuration reference

See `.env.example` for every setting. Key ones:

| Setting | Meaning |
|---|---|
| `JIRA_BASE_URL` | Your Jira Cloud base URL. |
| `JIRA_EMAIL` / `JIRA_API_TOKEN` | Credentials for the Jira REST API. |
| `JIRA_PROJECTS` | Scope projects (default `CON,T3,CL`). |
| `JIRA_PRIORITY` | Priority that marks a case business critical (default `Business Critical`). |
| `POLL_INTERVAL_MINUTES` | Loop interval / scheduler cadence. |
| `CLOSED_LOOKBACK_DAYS` | How far back to look for freshly closed tickets. |
| `HUMAN_ONLY` | Only comments from real people trigger emails (skips Automation/bots). |
| `LLM_PROVIDER` | Active AI provider: `groq` (default), `openai`, `azure`, or `anthropic`. |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` / `LLM_TIMEOUT_SECONDS` | Deterministic, bounded output (defaults 0 / 700 / 60). |
| `GROQ_*` / `OPENAI_*` / `ANTHROPIC_*` | Per-provider API key, model, and base URL. |
| `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` | Optional generic overrides that win over the per-provider values. |
| `SMTP_*` / `SMTP_FROM` / `EMAIL_RECIPIENTS` | Mail delivery and recipient list. |
| `DRY_RUN` | Print emails instead of sending them. |
| `STATE_FILE` | Path to the per-ticket state file (default `state.json`). |

Dashboard settings (stored in `settings.json`, editable live from the UI):

| Setting | Meaning |
|---|---|
| `poll_interval_minutes` | How often the auto-scan runs (default 5). |
| `realtime_emails` | Email each new comment as it arrives. |
| `rca_emails` | Email an RCA when a case closes. |
| `digest_enabled` | Send the consolidated end-of-day digest email. |
| `eod_hour` / `eod_minute` | Time to send the daily digest (24 h clock, default 19:00). |

## Development

Install the dev dependencies (adds pytest and ruff on top of the runtime deps):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run the test suite and linter from the repo root:

```powershell
.\.venv\Scripts\python.exe -m pytest       # unit + fault-injection tests
.\.venv\Scripts\python.exe -m ruff check . # lint
```

`pyproject.toml` holds the pytest and ruff config. The same two checks run in CI on
every push and pull request (`.github/workflows/ci.yml`).

> Application code is a Python package (`bcwatcher/`), so always run and import it
> as a module (`python -m bcwatcher.app`), never by path (`python app.py`).

## Project structure

```
jira-bc-watcher-pro/
├─ bcwatcher/                 # application package
│  ├─ app.py                  # Flask dashboard + embedded APScheduler (scan timer + EOD digest)
│  ├─ scanner.py              # core scan logic; writes results.json for the dashboard
│  ├─ digest.py               # end-of-day consolidated digest email
│  ├─ emailfmt.py             # HTML email formatter (Description, Status, Last Update, What's next)
│  ├─ store.py                # persists settings.json and results.json
│  ├─ grouping.py             # groups linked tickets into cases; rolls sub-tickets up to their Epic
│  ├─ jira_client.py          # Jira REST client (search, comments, linked issues)
│  ├─ summarizer.py           # extract -> validate -> render (progress + RCA)
│  ├─ guardrails.py           # anti-hallucination validation (grounding, sanitisation)
│  ├─ llm/                    # pluggable LLM providers (Groq, OpenAI/Azure, Anthropic)
│  ├─ mailer.py               # SMTP sender with dry-run mode
│  ├─ state.py                # persistent per-ticket state in state.json
│  ├─ config.py               # loads and validates configuration from .env
│  ├─ watcher.py              # legacy single-cycle / loop runner (no dashboard)
│  ├─ demo_trigger.py         # demo helper for the AI adoption walkthrough
│  └─ templates/dashboard.html
├─ scripts/                   # Windows helper scripts
│  ├─ run_dashboard.ps1       # runner used by the dashboard scheduled task
│  ├─ setup_dashboard_task.ps1# registers the dashboard as a Windows logon task
│  ├─ run_watcher.ps1         # runner used by the legacy watcher task
│  └─ setup_task.ps1          # legacy Task Scheduler setup for the watcher
├─ tests/                     # pytest suite (grouping, state, scanner fault-injection)
├─ docs/                      # architecture notes + phase sign-off records
├─ .github/workflows/ci.yml   # lint + test CI
├─ requirements.txt / requirements-dev.txt
└─ pyproject.toml             # pytest + ruff config
```

## Roadmap

The full phased plan (with testing and sign-off gates per phase) is tracked in
[`docs/`](docs/). At a high level:

- **Phase 0 (done)** - reliability hardening, test suite, CI, and this package
  reorganization as the productization baseline.
- **Phase 1 (done)** - swappable `LLMProvider` (Groq now, Claude/OpenAI by config)
  with strict extract/validate/render guardrails to prevent hallucinations and cut
  token usage. Switch provider with the single `LLM_PROVIDER` env var.
- **Phase 2+** - recipient-tailored emails (support, dev, manager, leadership), an
  engineering RCA-approval workflow, per-project configurable grouping,
  multi-tenant configuration, a database backend, and additional channels such as
  Microsoft Teams.
