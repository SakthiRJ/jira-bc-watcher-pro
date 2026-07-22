"""Provider-layer tests: factory selection, request shaping, JSON parsing, and
error handling. All HTTP is monkeypatched so no network is used."""
from __future__ import annotations

import pytest
import requests

from bcwatcher.config import Config
from bcwatcher.llm import (
    AnthropicProvider,
    LLMError,
    OpenAICompatibleProvider,
    build_provider,
    loads_lenient,
)
from bcwatcher.llm import anthropic as anthropic_mod
from bcwatcher.llm import openai_compatible as oai_mod


class FakeResp:
    def __init__(self, status_code=200, payload=None, text="", raise_json=False):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._payload


# -- loads_lenient ----------------------------------------------------------

def test_loads_lenient_plain_fenced_and_prose():
    assert loads_lenient('{"a": 1}') == {"a": 1}
    assert loads_lenient('```json\n{"a": 1}\n```') == {"a": 1}
    assert loads_lenient('Here you go:\n{"a": 1}\nthanks') == {"a": 1}


def test_loads_lenient_rejects_garbage():
    with pytest.raises(LLMError):
        loads_lenient("no json here")
    with pytest.raises(LLMError):
        loads_lenient("")


# -- factory ----------------------------------------------------------------

@pytest.mark.parametrize("provider,cls", [
    ("groq", OpenAICompatibleProvider),
    ("openai", OpenAICompatibleProvider),
    ("azure", OpenAICompatibleProvider),
    ("anthropic", AnthropicProvider),
    ("claude", AnthropicProvider),
])
def test_build_provider_selects_class(provider, cls):
    cfg = Config()
    cfg.llm_provider = provider
    assert isinstance(build_provider(cfg), cls)


# -- OpenAI-compatible provider --------------------------------------------

def _oai_settings():
    cfg = Config()
    cfg.llm_provider = "groq"
    cfg.groq_api_key = "k"
    return cfg.llm_settings()


def test_openai_compatible_parses_content(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp(payload={"choices": [{"message": {"content": '{"current_status": "ok"}'}}]})

    monkeypatch.setattr(oai_mod.requests, "post", fake_post)
    out = OpenAICompatibleProvider(_oai_settings()).complete_json("sys", "user")
    assert out == {"current_status": "ok"}
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["temperature"] == 0
    assert captured["json"]["response_format"] == {"type": "json_object"}


def test_openai_compatible_http_error_raises(monkeypatch):
    monkeypatch.setattr(oai_mod.requests, "post", lambda *a, **k: FakeResp(status_code=500, text="boom"))
    with pytest.raises(LLMError):
        OpenAICompatibleProvider(_oai_settings()).complete_json("s", "u")


def test_openai_compatible_network_error_raises(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(oai_mod.requests, "post", boom)
    with pytest.raises(LLMError):
        OpenAICompatibleProvider(_oai_settings()).complete_json("s", "u")


def test_openai_compatible_bad_shape_raises(monkeypatch):
    monkeypatch.setattr(oai_mod.requests, "post", lambda *a, **k: FakeResp(payload={"unexpected": True}))
    with pytest.raises(LLMError):
        OpenAICompatibleProvider(_oai_settings()).complete_json("s", "u")


# -- Anthropic provider -----------------------------------------------------

def _anthropic_settings():
    cfg = Config()
    cfg.llm_provider = "anthropic"
    cfg.anthropic_api_key = "k"
    return cfg.llm_settings()


def test_anthropic_parses_content_and_headers(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResp(payload={"content": [{"type": "text", "text": '{"subject": "[RCA] x"}'}]})

    monkeypatch.setattr(anthropic_mod.requests, "post", fake_post)
    out = AnthropicProvider(_anthropic_settings()).complete_json("sys", "user")
    assert out == {"subject": "[RCA] x"}
    assert captured["url"].endswith("/messages")
    assert captured["headers"]["x-api-key"] == "k"
    assert "anthropic-version" in captured["headers"]


def test_anthropic_http_error_raises(monkeypatch):
    monkeypatch.setattr(anthropic_mod.requests, "post", lambda *a, **k: FakeResp(status_code=401, text="no"))
    with pytest.raises(LLMError):
        AnthropicProvider(_anthropic_settings()).complete_json("s", "u")
