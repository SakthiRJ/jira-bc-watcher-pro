"""Secret resolution so tenant credentials are never stored in plaintext config.

A secret value in tenant config can be one of:
  * ``env:VAR_NAME``   -> read from the environment (recommended default)
  * ``enc:<token>``    -> a Fernet-encrypted value, decrypted with SECRETS_KEY
  * anything else      -> used literally (discouraged for real secrets)

Encryption is optional: the ``cryptography`` package and a ``SECRETS_KEY`` are
only needed if you actually use ``enc:`` values. ``env:`` and literal values work
with no extra dependencies, so the first test run needs nothing special.
"""
from __future__ import annotations

import os

ENV_PREFIX = "env:"
ENC_PREFIX = "enc:"


class SecretError(RuntimeError):
    pass


def _fernet(key: str | None):
    if not key:
        raise SecretError("SECRETS_KEY is required to decrypt an 'enc:' secret.")
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise SecretError(
            "The 'cryptography' package is required for 'enc:' secrets. "
            "Install it or use 'env:' / plaintext values."
        ) from exc
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise SecretError("SECRETS_KEY is not a valid Fernet key.") from exc


def resolve_secret(value: str | None, secrets_key: str | None = None) -> str:
    """Resolve a possibly-referenced secret to its plaintext value."""
    if not value:
        return ""
    value = str(value)
    if value.startswith(ENV_PREFIX):
        return os.getenv(value[len(ENV_PREFIX):], "")
    if value.startswith(ENC_PREFIX):
        token = value[len(ENC_PREFIX):]
        key = secrets_key if secrets_key is not None else os.getenv("SECRETS_KEY", "")
        try:
            return _fernet(key).decrypt(token.encode("utf-8")).decode("utf-8")
        except SecretError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalise any decrypt failure
            raise SecretError("Failed to decrypt an 'enc:' secret (wrong key or token).") from exc
    return value


def generate_key() -> str:
    """Generate a new Fernet key (for the CLI / setup docs)."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("utf-8")


def encrypt_value(plaintext: str, secrets_key: str | None = None) -> str:
    """Encrypt a plaintext secret into an ``enc:`` reference."""
    key = secrets_key if secrets_key is not None else os.getenv("SECRETS_KEY", "")
    token = _fernet(key).encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{ENC_PREFIX}{token}"
