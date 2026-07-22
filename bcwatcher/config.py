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
class LLMSettings:
    """Resolved settings for the active LLM provider (see Config.llm_settings)."""

    provider: str
    api_key: str
    model: str
    base_url: str
    temperature: float = 0.0
    max_tokens: int = 700
    timeout: int = 60


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

    # AI - active provider selector: groq | openai | azure | anthropic
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    # Generic overrides (take precedence over provider-specific values below)
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "700"))
    llm_timeout: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

    # Groq (default provider, OpenAI-compatible)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")

    # OpenAI / Azure (OpenAI-compatible) - ready for swap when access is available
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    # Anthropic (Claude) - ready for swap when access is available
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    anthropic_base_url: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")

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

    def llm_settings(self) -> "LLMSettings":
        """Resolve the active provider's settings.

        Generic LLM_* overrides win; otherwise provider-specific defaults are used.
        Keeping this in config (not the provider) makes the provider swappable with
        a single env var and keeps all secrets in one place.
        """
        provider = (self.llm_provider or "groq").strip().lower()
        common = {
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
            "timeout": self.llm_timeout,
        }
        if provider in {"anthropic", "claude"}:
            return LLMSettings(
                provider="anthropic",
                api_key=self.llm_api_key or self.anthropic_api_key,
                model=self.llm_model or self.anthropic_model,
                base_url=(self.llm_base_url or self.anthropic_base_url).rstrip("/"),
                **common,
            )
        if provider in {"openai", "azure"}:
            return LLMSettings(
                provider=provider,
                api_key=self.llm_api_key or self.openai_api_key,
                model=self.llm_model or self.openai_model,
                base_url=(self.llm_base_url or self.openai_base_url).rstrip("/"),
                **common,
            )
        # Default: Groq (and any other OpenAI-compatible endpoint).
        return LLMSettings(
            provider="groq",
            api_key=self.llm_api_key or self.groq_api_key,
            model=self.llm_model or self.groq_model,
            base_url=(self.llm_base_url or self.groq_base_url).rstrip("/"),
            **common,
        )

    def validate(self) -> list[str]:
        """Return a list of human-readable problems (empty means OK)."""
        problems: list[str] = []
        if not self.jira_email or not self.jira_api_token:
            problems.append("JIRA_EMAIL and JIRA_API_TOKEN are required.")
        if not self.projects:
            problems.append("JIRA_PROJECTS must list at least one project key.")
        llm = self.llm_settings()
        if not llm.api_key:
            problems.append(f"An API key is required for the '{llm.provider}' LLM provider.")
        if not llm.model:
            problems.append(f"A model name is required for the '{llm.provider}' LLM provider.")
        if not self.dry_run:
            if not (self.smtp_host and self.smtp_from and self.recipients):
                problems.append(
                    "SMTP_HOST, SMTP_FROM and EMAIL_RECIPIENTS are required when DRY_RUN is false."
                )
        return problems


config = Config()
