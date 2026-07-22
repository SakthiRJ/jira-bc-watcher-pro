"""OpenAI-compatible chat-completions provider.

Covers Groq (default), OpenAI, and Azure OpenAI-style endpoints that expose
``POST {base_url}/chat/completions`` and accept a ``response_format`` of
``json_object``. Selecting one is purely a matter of base_url + model + key.
"""
from __future__ import annotations

import requests

from bcwatcher.llm.base import LLMError, LLMProvider, loads_lenient


class OpenAICompatibleProvider(LLMProvider):
    def complete_json(self, system: str, user: str) -> dict:
        s = self.settings
        try:
            resp = requests.post(
                f"{s.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {s.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": s.model,
                    "temperature": s.temperature,
                    "max_tokens": s.max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=s.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError(f"{self.name} request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMError(f"{self.name} returned HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name} returned an unexpected response shape: {exc}") from exc

        return loads_lenient(content)
