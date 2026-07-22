"""Config resolvers: audience recipient routing and provider selection."""
from __future__ import annotations

from bcwatcher.config import Config


def test_audience_recipients_only_includes_configured():
    cfg = Config()
    cfg.recipients_support = ["support@x.com"]
    cfg.recipients_dev = []
    cfg.recipients_manager = ["mgr@x.com", "mgr2@x.com"]
    cfg.recipients_leadership = []
    assert cfg.audience_recipients() == {
        "support": ["support@x.com"],
        "manager": ["mgr@x.com", "mgr2@x.com"],
    }


def test_audience_recipients_empty_when_none_configured():
    cfg = Config()
    cfg.recipients_support = []
    cfg.recipients_dev = []
    cfg.recipients_manager = []
    cfg.recipients_leadership = []
    assert cfg.audience_recipients() == {}


def test_llm_settings_defaults_to_groq():
    cfg = Config()
    cfg.llm_provider = "groq"
    cfg.groq_api_key = "k"
    s = cfg.llm_settings()
    assert s.provider == "groq"
    assert s.api_key == "k"
    assert s.temperature == 0


def test_llm_generic_override_wins():
    cfg = Config()
    cfg.llm_provider = "groq"
    cfg.groq_api_key = "groqkey"
    cfg.llm_api_key = "override"
    assert cfg.llm_settings().api_key == "override"
