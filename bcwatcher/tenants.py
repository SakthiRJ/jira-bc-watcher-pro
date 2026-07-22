"""Multi-tenant configuration.

A tenant is one company/Jira instance the watcher serves: its Jira connection,
scope (projects + priorities), grouping policy (with per-project overrides),
recipients, and schedule. Tenants are read from ``TENANTS_FILE`` (JSON); when
that file is absent, a single ``default`` tenant is synthesized from the existing
``.env``/`Config` so single-tenant deployments and the first test run need no
extra setup.

The datastore stays flat-file for now; SQLite/Postgres are drop-in backends
later (see docs). Secrets in the tenant file are resolved via ``bcwatcher.secrets``
so tokens are never stored in plaintext.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from bcwatcher import secrets
from bcwatcher.config import config
from bcwatcher.grouping import DEFAULT_POLICY, GroupingPolicy


@dataclass
class TenantSchedule:
    poll_interval_minutes: int = 5
    eod_hour: int = 19
    eod_minute: int = 0
    digest_enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict | None) -> "TenantSchedule":
        data = data or {}
        return cls(
            poll_interval_minutes=max(1, int(data.get("poll_interval_minutes", 5))),
            eod_hour=min(23, max(0, int(data.get("eod_hour", 19)))),
            eod_minute=min(59, max(0, int(data.get("eod_minute", 0)))),
            digest_enabled=bool(data.get("digest_enabled", True)),
        )


@dataclass
class Tenant:
    id: str
    name: str
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    projects: list[str]
    priorities: list[str]
    closed_lookback_days: int = 3
    grouping: GroupingPolicy = DEFAULT_POLICY
    grouping_overrides: dict[str, GroupingPolicy] = field(default_factory=dict)
    recipients: dict[str, list[str]] = field(default_factory=dict)
    schedule: TenantSchedule = field(default_factory=TenantSchedule)
    active: bool = True

    # -- config-compatible surface (so a Tenant can drive JiraClient etc.) --
    @property
    def priority(self) -> str:
        return self.priorities[0] if self.priorities else "Business Critical"

    def grouping_for(self, project: str) -> GroupingPolicy:
        return self.grouping_overrides.get(project, self.grouping)

    def validate(self) -> list[str]:
        problems: list[str] = []
        prefix = f"tenant '{self.id}'"
        if not self.id:
            problems.append("A tenant is missing an 'id'.")
        if not self.jira_base_url:
            problems.append(f"{prefix}: jira base_url is required.")
        if not self.jira_email or not self.jira_api_token:
            problems.append(f"{prefix}: jira email and api_token are required.")
        if not self.projects:
            problems.append(f"{prefix}: at least one project is required.")
        if not self.priorities:
            problems.append(f"{prefix}: at least one priority is required.")
        return problems

    def public_dict(self) -> dict:
        """Serialisable view with secrets redacted (for the API)."""
        return {
            "id": self.id,
            "name": self.name,
            "active": self.active,
            "jira_base_url": self.jira_base_url,
            "jira_email": self.jira_email,
            "jira_api_token": "***" if self.jira_api_token else "",
            "projects": self.projects,
            "priorities": self.priorities,
            "closed_lookback_days": self.closed_lookback_days,
            "grouping": vars(self.grouping),
            "grouping_overrides": {p: vars(pol) for p, pol in self.grouping_overrides.items()},
            "recipients": self.recipients,
            "schedule": vars(self.schedule),
        }

    @classmethod
    def from_dict(cls, data: dict, secrets_key: str | None = None) -> "Tenant":
        jira = data.get("jira") or {}
        overrides = {
            project: GroupingPolicy.from_dict(pol)
            for project, pol in (data.get("grouping_overrides") or {}).items()
        }
        priorities = [str(p).strip() for p in (data.get("priorities") or []) if str(p).strip()]
        return cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", data.get("id", ""))).strip(),
            jira_base_url=str(jira.get("base_url", "")).rstrip("/"),
            jira_email=secrets.resolve_secret(jira.get("email", ""), secrets_key),
            jira_api_token=secrets.resolve_secret(jira.get("api_token", ""), secrets_key),
            projects=[str(p).strip() for p in (data.get("projects") or []) if str(p).strip()],
            priorities=priorities or ["Business Critical"],
            closed_lookback_days=int(data.get("closed_lookback_days", 3)),
            grouping=GroupingPolicy.from_dict(data.get("grouping")),
            grouping_overrides=overrides,
            recipients={k: list(v) for k, v in (data.get("recipients") or {}).items()},
            schedule=TenantSchedule.from_dict(data.get("schedule")),
            active=bool(data.get("active", True)),
        )


def default_tenant() -> Tenant:
    """Single tenant synthesized from the global Config/.env (back-compat)."""
    return Tenant(
        id="default",
        name="Default",
        jira_base_url=config.jira_base_url,
        jira_email=config.jira_email,
        jira_api_token=config.jira_api_token,
        projects=list(config.projects),
        priorities=list(config.priorities) or [config.priority],
        closed_lookback_days=config.closed_lookback_days,
        grouping=DEFAULT_POLICY,
        grouping_overrides={},
        recipients={
            "default": list(config.recipients),
            "support": list(config.recipients_support),
            "dev": list(config.recipients_dev),
            "manager": list(config.recipients_manager),
            "leadership": list(config.recipients_leadership),
            "rca": list(config.recipients_rca),
        },
        schedule=TenantSchedule(poll_interval_minutes=config.poll_interval_minutes),
        active=True,
    )


def load_tenants(path: str | None = None, secrets_key: str | None = None) -> list[Tenant]:
    """Load tenants from the JSON file, or a single default tenant if absent."""
    path = path or config.tenants_file
    key = secrets_key if secrets_key is not None else config.secrets_key
    if not path or not os.path.exists(path):
        return [default_tenant()]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return [default_tenant()]
    entries = raw.get("tenants", raw) if isinstance(raw, dict) else raw
    tenants = [Tenant.from_dict(entry, key) for entry in entries]
    return tenants or [default_tenant()]


def active_tenants(path: str | None = None) -> list[Tenant]:
    return [t for t in load_tenants(path) if t.active]


def get_tenant(tenant_id: str, path: str | None = None) -> Tenant | None:
    for tenant in load_tenants(path):
        if tenant.id == tenant_id:
            return tenant
    return None
