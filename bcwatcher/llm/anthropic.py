"""Anthropic (Claude) Messages API provider.

Ready to use the moment an ANTHROPIC_API_KEY is available; switch to it by
setting ``LLM_PROVIDER=anthropic``. Anthropic has no ``response_format`` flag,
so the prompt instructs JSON-only output and we parse leniently.
"""
from __future__ import annotations

import requests

from bcwatcher.llm.base import LLMError, LLMProvider, loads_lenient

_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    def complete_json(self, system: str, user: str) -> dict:
        s = self.settings
        system_json = system + "\nReturn ONLY a single valid JSON object. No prose, no code fences."
        try:
            resp = requests.post(
                f"{s.base_url}/messages",
                headers={
                    "x-api-key": s.api_key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                    "Content-Type": "application/json",
                },
                json={
                    "model": s.model,
                    "max_tokens": s.max_tokens,
                    "temperature": s.temperature,
                    "system": system_json,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=s.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError(f"anthropic request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMError(f"anthropic returned HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            blocks = resp.json()["content"]
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"anthropic returned an unexpected response shape: {exc}") from exc

        return loads_lenient(text)
