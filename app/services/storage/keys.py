"""Storage key layout.

Keys are built in exactly one place so the bucket stays browsable and so a
future lifecycle rule ("expire renders older than 90 days") can be written
against a prefix rather than against a database query.

    users/{user_id}/{kind}/{token}.{ext}

`kind` mirrors VideoAsset.kind (upload, voice, music, subtitle, image, video,
thumbnail, render). The token is unguessable and unique, so a key is never
reused and an overwrite is impossible by accident — which is what lets objects
be cached immutably.
"""
from __future__ import annotations

import re
import secrets

from app.services.storage.base import extension_for

# Kinds allowed in a key. A typo here would scatter objects across prefixes
# that no lifecycle rule covers, so the set is closed.
KINDS = (
    "upload",
    "voice",
    "music",
    "subtitle",
    "image",
    "video",
    "thumbnail",
    "render",
)

_SAFE = re.compile(r"[^a-z0-9]+")


def new_token() -> str:
    """The unguessable id shared by the storage key and the public URL."""
    return secrets.token_urlsafe(24)


def build_key(
    *,
    user_id: int,
    kind: str,
    content_type: str,
    token: str | None = None,
) -> tuple[str, str]:
    """Return `(key, token)` for a new object.

    The token is returned rather than parsed back out of the key: the read
    route looks assets up by token, and deriving one from a string is exactly
    the kind of coupling that breaks when the layout changes.
    """
    safe_kind = _SAFE.sub("-", (kind or "upload").lower()).strip("-") or "upload"
    if safe_kind not in KINDS:
        safe_kind = "upload"

    token = token or new_token()
    ext = extension_for(content_type)
    return f"users/{user_id}/{safe_kind}/{token}.{ext}", token
