"""Secret resolution: literal, env, and Fernet-encrypted values."""
from __future__ import annotations

import pytest

from bcwatcher import secrets


def test_literal_value_passthrough():
    assert secrets.resolve_secret("plain-token") == "plain-token"


def test_empty_returns_empty():
    assert secrets.resolve_secret("") == ""
    assert secrets.resolve_secret(None) == ""


def test_env_reference(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "from-env")
    assert secrets.resolve_secret("env:MY_TOKEN") == "from-env"


def test_env_missing_is_empty(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    assert secrets.resolve_secret("env:NOPE") == ""


def test_encrypt_roundtrip():
    key = secrets.generate_key()
    enc = secrets.encrypt_value("s3cr3t", key)
    assert enc.startswith("enc:")
    assert secrets.resolve_secret(enc, key) == "s3cr3t"


def test_enc_without_key_raises():
    with pytest.raises(secrets.SecretError):
        secrets.resolve_secret("enc:whatever", "")


def test_enc_with_wrong_key_raises():
    key = secrets.generate_key()
    enc = secrets.encrypt_value("s3cr3t", key)
    other = secrets.generate_key()
    with pytest.raises(secrets.SecretError):
        secrets.resolve_secret(enc, other)
