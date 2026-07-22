"""Preflight checks - run before the first full test.

    python -m bcwatcher.preflight            # config + connectivity
    python -m bcwatcher.preflight --no-net    # config only (offline)

Validates configuration and each tenant, then (unless --no-net) checks Jira
auth, the LLM provider key/model, and SMTP (when DRY_RUN is off). Prints a
PASS/WARN/FAIL report and exits non-zero if anything is a hard FAIL, so it can
gate a deployment.
"""
from __future__ import annotations

import smtplib
import sys

from bcwatcher import tenants
from bcwatcher.config import config

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _jira_check(tenant) -> tuple[str, str]:
    if not (tenant.jira_base_url and tenant.jira_email and tenant.jira_api_token):
        return FAIL, "missing Jira base_url/email/api_token"
    try:
        import requests

        resp = requests.get(
            f"{tenant.jira_base_url}/rest/api/3/myself",
            auth=(tenant.jira_email, tenant.jira_api_token),
            headers={"Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code == 200:
            who = (resp.json() or {}).get("displayName", "authenticated")
            return PASS, f"authenticated as {who}"
        return FAIL, f"HTTP {resp.status_code} from /myself"
    except Exception as exc:  # noqa: BLE001 - report any connectivity failure
        return FAIL, f"connection error: {exc}"


def _smtp_check() -> tuple[str, str]:
    if config.dry_run:
        return WARN, "DRY_RUN is on; SMTP not used (emails print to console)"
    if not config.smtp_host:
        return FAIL, "SMTP_HOST is required when DRY_RUN is off"
    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as server:
            if config.smtp_use_tls:
                server.starttls()
            if config.smtp_user:
                server.login(config.smtp_user, config.smtp_password)
        return PASS, f"connected to {config.smtp_host}:{config.smtp_port}"
    except Exception as exc:  # noqa: BLE001
        return FAIL, f"SMTP error: {exc}"


def collect(check_net: bool = True) -> list[tuple[str, str, str]]:
    """Return a list of (check, status, detail)."""
    results: list[tuple[str, str, str]] = []

    problems = config.validate()
    if problems:
        for p in problems:
            results.append(("config", FAIL, p))
    else:
        results.append(("config", PASS, "base configuration looks valid"))

    llm = config.llm_settings()
    if llm.api_key and llm.model:
        results.append(("llm", PASS, f"provider={llm.provider} model={llm.model}"))
    else:
        results.append(("llm", FAIL, f"provider={llm.provider} missing api key or model"))

    loaded = tenants.load_tenants()
    results.append(("tenants", PASS, f"{len(loaded)} tenant(s) loaded"))
    for tenant in loaded:
        for problem in tenant.validate():
            results.append((f"tenant:{tenant.id}", FAIL, problem))
        if check_net and tenant.active:
            status, detail = _jira_check(tenant)
            results.append((f"jira:{tenant.id}", status, detail))

    if check_net:
        status, detail = _smtp_check()
        results.append(("smtp", status, detail))

    return results


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    check_net = "--no-net" not in argv

    print("BC Watcher preflight")
    print("=" * 60)
    results = collect(check_net=check_net)
    worst_fail = False
    for check, status, detail in results:
        print(f"[{status:4}] {check:16} {detail}")
        if status == FAIL:
            worst_fail = True
    print("=" * 60)
    if worst_fail:
        print("RESULT: FAIL - fix the items above before the full test.")
        return 1
    print("RESULT: OK - ready for the full test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
