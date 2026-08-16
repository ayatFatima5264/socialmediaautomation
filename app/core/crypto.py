"""Encryption at rest for the OAuth tokens stored in `social_accounts`.

A connected account's access/refresh token is a bearer credential: anyone
holding it can post as that user until it expires. Storing them in plaintext
means a database dump — a backup, a misconfigured replica, a leaked connection
string — hands over every connected account at once. So they are encrypted
before they reach the database and decrypted only in the process that is about
to call the platform API.

**Key.** Fernet (AES-128-CBC + HMAC-SHA256), keyed from `TOKEN_ENCRYPTION_KEY`.
Never hardcoded and never defaulted: the key lives only in the environment.
The setting accepts a comma-separated list so a key can be rotated — the first
key encrypts, every key is tried when decrypting — which is what lets old rows
keep working while new ones use the new key.

**No key configured.** Values pass through unencrypted, exactly as they were
stored before this module existed. That is deliberate: a deploy that has not yet
set the variable keeps working rather than losing every connection, and local
development and tests need no key. A one-line warning says so at startup.

**Existing plaintext.** Ciphertext carries the `enc:v1:` marker, so a value
without it is known-plaintext from before encryption was switched on and is
returned as-is. `encrypt_existing_tokens()` (run at startup) rewrites those rows
in place, so the plaintext path exists only until the first boot with a key set.

Nothing here ever logs a token, a key, or a ciphertext.
"""
from __future__ import annotations

import logging

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.config import settings

logger = logging.getLogger(__name__)

# Marks a value this module produced. Its absence means the value predates
# encryption (or was written with no key configured) and is plaintext.
PREFIX = "enc:v1:"

_fernet = None
_fernet_loaded = False


def _keys() -> list[str]:
    raw = settings.token_encryption_key or ""
    return [key.strip() for key in raw.split(",") if key.strip()]


def _cipher():
    """The MultiFernet built from the configured keys, or None if unconfigured.

    Built once. A malformed key is reported as unconfigured rather than raised,
    because raising here would take down every request that touches a connected
    account — the same failure mode as no key at all, but harder to diagnose.
    """
    global _fernet, _fernet_loaded
    if _fernet_loaded:
        return _fernet

    _fernet_loaded = True
    keys = _keys()
    if not keys:
        logger.warning(
            "TOKEN_ENCRYPTION_KEY is not set — OAuth tokens will be stored in "
            "plaintext. Set it to enable encryption at rest."
        )
        return None

    try:
        from cryptography.fernet import Fernet, MultiFernet
    except ImportError:  # pragma: no cover — cryptography is a hard requirement
        logger.error(
            "cryptography is not installed — OAuth tokens cannot be encrypted."
        )
        return None

    try:
        _fernet = MultiFernet([Fernet(key.encode("utf-8")) for key in keys])
    except (ValueError, TypeError):
        # The key itself is never logged, only the fact that it did not parse.
        logger.error(
            "TOKEN_ENCRYPTION_KEY is not a valid Fernet key (expected a 32-byte "
            "urlsafe-base64 value) — tokens will be stored in plaintext."
        )
        _fernet = None
    return _fernet


def reset_cache() -> None:
    """Forget the cached cipher so a changed key takes effect. For tests."""
    global _fernet, _fernet_loaded
    _fernet = None
    _fernet_loaded = False


def is_enabled() -> bool:
    """True when a usable key is configured."""
    return _cipher() is not None


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(value: str | None) -> str | None:
    """Encrypt a token for storage. Returns it unchanged if no key is set."""
    if value is None or value == "":
        return value
    if is_encrypted(value):
        return value  # already encrypted — don't double-wrap
    cipher = _cipher()
    if cipher is None:
        return value
    return PREFIX + cipher.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str | None) -> str | None:
    """Decrypt a stored token.

    Plaintext (no marker) is returned as-is — that is a row written before
    encryption was enabled. A marked value that will not decrypt returns None
    rather than raising: this runs inside SQLAlchemy's result handling, so
    raising would fail every query that loads the account instead of the one
    operation that actually needs the token. `effective_status` reports an
    account with no usable token as needing reconnection, which is the honest
    outcome when the key that wrote it is gone.
    """
    if not value or not is_encrypted(value):
        return value

    cipher = _cipher()
    if cipher is None:
        logger.error(
            "A stored token is encrypted but no valid TOKEN_ENCRYPTION_KEY is "
            "configured — the affected accounts must be reconnected."
        )
        return None

    try:
        from cryptography.fernet import InvalidToken
    except ImportError:  # pragma: no cover
        return None

    try:
        return cipher.decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        logger.error(
            "A stored token could not be decrypted with the configured key — "
            "the affected account must be reconnected."
        )
        return None


class EncryptedString(TypeDecorator):
    """A Text column whose value is encrypted on the way in and out.

    Declared on the model, so every read and write in the app is covered without
    a single call site changing: `account.access_token` still reads as the real
    token, and assigning to it still stores ciphertext.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: D102, ANN001
        return encrypt(value)

    def process_result_value(self, value, dialect):  # noqa: D102, ANN001
        return decrypt(value)
