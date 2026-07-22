# First full test runbook

This is the step-by-step for the first end-to-end test of the watcher. It runs
single-tenant on flat files with your `.env` - no database, no OAuth.

## 1. Environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # then edit .env
```

Fill in `.env`:
- `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
- `JIRA_PROJECTS`, `JIRA_PRIORITY` (or `JIRA_PRIORITIES`)
- an LLM key: `GROQ_API_KEY` (default provider) and `LLM_PROVIDER=groq`
- keep `DRY_RUN=true` for the first pass so emails print to the console instead
  of being sent.

## 2. Preflight (validate everything)

```powershell
.\.venv\Scripts\python.exe -m bcwatcher.preflight            # config + connectivity
.\.venv\Scripts\python.exe -m bcwatcher.preflight --no-net    # config only (offline)
```

Every line must read `PASS` (or `WARN` for SMTP while `DRY_RUN=true`). Fix any
`FAIL` before continuing. This checks configuration, each tenant, the LLM
key/model, and Jira authentication.

## 3. Dry-run scan + dashboard

```powershell
.\.venv\Scripts\python.exe -m bcwatcher.app
```

Open http://127.0.0.1:5000 and:
- Click **Scan now**. Confirm business-critical cases appear with Description,
  Current Status, Last Update, and What's next.
- Check the console: any "sent" email is printed in full (DRY RUN) instead of
  going out.
- Add yourself under **Notification subscriptions** (realtime + rca + digest)
  and trigger another scan to see routing.
- When a case closes, confirm its RCA appears under **Pending RCA approvals**
  and is NOT emailed until you approve it.
- Click **Send digest now** and open the preview link.

## 4. Live emails

When the dry run looks right, set `DRY_RUN=false` and provide SMTP settings
(`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`). Re-run the
preflight - the `smtp` check should now be `PASS` - then repeat step 3 with a
small recipient list before wider rollout.

## 5. Multiple companies (optional)

Copy `tenants.example.json` to `tenants.json`, set `TENANTS_FILE=tenants.json`,
and put each company's Jira connection, projects, priorities, grouping policy,
and recipients there. Use `env:` or `enc:` references for tokens (never plaintext
secrets). `GET /api/tenants` shows the loaded tenants with secrets redacted.

Note: this release scans the single active/default tenant. Running scans for
several tenants concurrently (per-tenant schedulers and state) is the next step
and does not change the config format above.

## Runtime files (safe to delete to reset state)

`state.json`, `results.json`, `settings.json`, `subscriptions.json`,
`rca_queue.json`, `dry_run_email.html`. All are gitignored and regenerated.
