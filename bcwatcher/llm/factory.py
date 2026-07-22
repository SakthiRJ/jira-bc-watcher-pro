"""Build the active LLM provider from configuration."""
from __future__ import annotations

from bcwatcher.config import Config
from bcwatcher.llm.anthropic import AnthropicProvider
from bcwatcher.llm.base import LLMProvider
from bcwatcher.llm.openai_compatible import OpenAICompatibleProvider


def build_provider(config: Config) -> LLMProvider:
    settings = config.llm_settings()
    if settings.provider in {"anthropic", "claude"}:
        return AnthropicProvider(settings)
    # groq, openai, azure, and any other OpenAI-compatible endpoint
    return OpenAICompatibleProvider(settings)
