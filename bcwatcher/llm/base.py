"""LLM provider abstraction.

A provider takes a system prompt and a user prompt and returns a parsed JSON
object. Concrete providers (OpenAI-compatible, Anthropic) live alongside this
module. Choosing one is a single config switch (see ``config.llm_settings``).

Providers deal ONLY with transport and JSON parsing. All hallucination
guardrails (grounding, sanitisation, deterministic fallbacks) live in
``bcwatcher.guardrails`` so they apply no matter which provider is active.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod

from bcwatcher.config import LLMSettings


class LLMError(Exception):
    """Raised for any transport, HTTP, or response-parsing failure.

    Callers treat this as a transient failure and retry on the next scan cycle
    rather than emitting empty or fabricated content.
    """


def loads_lenient(text: str) -> dict:
    """Parse a JSON object from a model response.

    Tolerates markdown code fences and leading/trailing prose that some models
    add around JSON. Raises LLMError if no JSON object can be recovered.
    """
    if not text:
        raise LLMError("empty response from model")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Drop the opening fence (``` or ```json) and the closing fence.
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[: -3]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError(f"could not parse JSON from response: {exc}") from exc
        raise LLMError("response did not contain a JSON object")


class LLMProvider(ABC):
    """Base class for all providers."""

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    @property
    def name(self) -> str:
        return self.settings.provider

    @property
    def model(self) -> str:
        return self.settings.model

    @abstractmethod
    def complete_json(self, system: str, user: str) -> dict:
        """Return a parsed JSON object for the given prompts, or raise LLMError."""
