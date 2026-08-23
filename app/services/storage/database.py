"""Database-backed object storage — development only.

Implements the same contract as R2 so every feature works on a fresh clone with
no bucket configured. See app/models/storage_object.py for why this must not be
used in production.

Sessions are opened per call rather than taken from the request: `ObjectStorage`
is deliberately free of FastAPI dependencies so a background renderer can use
the identical object.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.database import SessionLocal
from app.models.storage_object import StorageObject
from app.services.storage.base import (
    ObjectMetadata,
    ObjectNotFound,
    ObjectStorage,
    StorageError,
    StoredObject,
)

logger = logging.getLogger(__name__)


class DatabaseStorage(ObjectStorage):
    name = "database"

    def put(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> StoredObject:
        with SessionLocal() as db:
            row = db.scalars(
                select(StorageObject).where(StorageObject.key == key)
            ).first()
            if row is None:
                row = StorageObject(key=key)
                db.add(row)
            row.content_type = content_type
            row.filename = filename
            row.size_bytes = len(data)
            row.data = data
            db.commit()

        return StoredObject(key=key, content_type=content_type, size_bytes=len(data))

    def get(self, key: str) -> tuple[bytes, str]:
        with SessionLocal() as db:
            row = db.scalars(
                select(StorageObject).where(StorageObject.key == key)
            ).first()
            if row is None:
                raise ObjectNotFound(f"No stored object at {key!r}.")
            return row.data, row.content_type

    def stat(self, key: str) -> ObjectMetadata:
        """Metadata without loading `data`.

        The column list is explicit so a stat of a 40 MB object does not pull
        40 MB out of Postgres — which is the entire point of having a stat.
        """
        with SessionLocal() as db:
            row = db.execute(
                select(
                    StorageObject.content_type,
                    StorageObject.size_bytes,
                    StorageObject.created_at,
                ).where(StorageObject.key == key)
            ).first()
            if row is None:
                raise ObjectNotFound(f"No stored object at {key!r}.")
            content_type, size_bytes, created_at = row
            return ObjectMetadata(
                key=key,
                content_type=content_type,
                size_bytes=int(size_bytes or 0),
                last_modified=created_at,
                etag=None,
            )

    def exists(self, key: str) -> bool:
        with SessionLocal() as db:
            return (
                db.scalars(
                    select(StorageObject.id).where(StorageObject.key == key)
                ).first()
                is not None
            )

    def delete(self, key: str) -> None:
        with SessionLocal() as db:
            row = db.scalars(
                select(StorageObject).where(StorageObject.key == key)
            ).first()
            if row is not None:
                db.delete(row)
                db.commit()

    def url_for(self, key: str, *, download_name: str | None = None) -> str:
        """There is no direct URL — the bytes are in a table.

        The read route detects this backend and streams from `get()` instead of
        redirecting, so this is only ever reached by code that asks for a URL
        without going through the route. Raising is better than returning
        something that 404s later.
        """
        raise StorageError(
            "The database storage backend serves objects through "
            "/api/storage/o/{token}; it has no direct object URL."
        )

    def signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_name: str | None = None,
    ) -> str:
        """Also unavailable — there is nothing to sign against.

        A stand-in that returned the streaming route would be a URL that never
        expires, quietly turning the one backend meant for development into the
        one with no time box on its links.
        """
        raise StorageError(
            "The database storage backend cannot issue signed URLs. "
            "Configure Cloudflare R2 (STORAGE_BACKEND=r2) for private links."
        )
