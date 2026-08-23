"""Storage backend selection — the single switch point for where bytes live.

Mirrors app/services/providers/factory.py: one function returns the configured
implementation, and every caller takes what it is given.

    STORAGE_BACKEND=auto      R2 when its credentials are set, else the database
    STORAGE_BACKEND=r2        Cloudflare R2; a missing credential is an error
    STORAGE_BACKEND=database  bytes in Postgres (development only)

`auto` is the default so a fresh clone runs with no configuration at all, while
a production deploy that sets the four R2 variables is upgraded by that alone.
The instance is cached because building an R2 client sets up a connection pool
that should outlive one request.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings
from app.services.storage import r2 as r2_module
from app.services.storage.base import ObjectStorage, StorageConfigError
from app.services.storage.database import DatabaseStorage
from app.services.storage.r2 import R2Storage

logger = logging.getLogger(__name__)

#: Backend identifiers the API advertises.
available_backends: list[str] = ["r2", "database"]


def _select(name: str) -> ObjectStorage:
    name = (name or "auto").lower()

    if name == "auto":
        if r2_module.is_configured():
            return R2Storage()
        logger.warning(
            "STORAGE_BACKEND=auto and Cloudflare R2 is not configured — "
            "falling back to database storage. This is for development only; "
            "set the R2_* variables before deploying Video Studio."
        )
        return DatabaseStorage()

    if name == "r2":
        return R2Storage()

    if name == "database":
        return DatabaseStorage()

    raise StorageConfigError(
        f"Unknown storage backend {name!r}. "
        f"Available: auto, {', '.join(available_backends)}"
    )


@lru_cache
def get_storage() -> ObjectStorage:
    """The configured object store. Cached for the life of the process."""
    backend = _select(settings.storage_backend)
    logger.info("Object storage backend: %s", backend.name)
    return backend


def reset_storage_cache() -> None:
    """Drop the cached backend. For tests that change configuration."""
    get_storage.cache_clear()
