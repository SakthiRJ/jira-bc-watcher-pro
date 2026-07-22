"""Configuration loaded from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Config:
    # Jira
    jira_base_url: str = os.getenv("JIRA_BASE_URL", "https://aphinity.atlassian.net").rstrip("/")
    jira_email: str = os.getenv("JIRA_EMAIL", "")
    jira_api_token: str = os.getenv("JIRA_API_TOKEN", "")
    projects: list[str] = field(default_factory=lambda: _list("JIRA_PROJECTS", "CON,T3,CL"))
    priority: str = os.getenv("JIRA_PRIORITY", "Business Critical")

    # Polling
    poll_interval_minutes: int = int(os.getenv("POLL_INTERVAL_MINUTES", "5"))
    closed_lookback_days: int = int(os.getenv("CLOSED_LOOKBACK_DAYS", "3"))
    human_only: bool = _bool("HUMAN_ONLY", True)

    # AI (Groq)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")

    # Email
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_use_tls: bool = _bool("SMTP_USE_TLS", True)
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    recipients: list[str] = field(default_factory=lambda: _list("EMAIL_RECIPIENTS", ""))

    # Behaviour
    dry_run: bool = _bool("DRY_RUN", True)
    state_file: str = os.getenv("STATE_FILE", "state.json")

    def validate(self) -> list[str]:
        """Return a list of human-readable problems (empty means OK)."""
        problems: list[str] = []
        if not self.jira_email or not self.jira_api_token:
            problems.append("JIRA_EMAIL and JIRA_API_TOKEN are required.")
        if not self.projects:
            problems.append("JIRA_PROJECTS must list at least one project key.")
        if not self.groq_api_key:
            problems.append("GROQ_API_KEY is required for AI summaries.")
        if not self.dry_run:
            if not (self.smtp_host and self.smtp_from and self.recipients):
                problems.append(
                    "SMTP_HOST, SMTP_FROM and EMAIL_RECIPIENTS are required when DRY_RUN is false."
                )
        return problems


config = Config()
