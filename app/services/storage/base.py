"""Object storage abstraction — the seam between Video Studio and a bucket.

Video Studio produces bytes the database has no business holding: uploaded
source footage, voice-over MP3s, rendered MP4s, thumbnails. A single 60-second
1080p render is tens of megabytes; a container's local disk is wiped on every
deploy. Both of those are answered by putting the bytes in object storage and
keeping only a *key* on the row.

Everything above this module — models, routes, the frontend — knows two things
and nothing else: the `storage_key` a write returned, and that
`storage.url_for(key)` produces something a browser (or a social platform's
fetcher) can GET. Which vendor is behind that is one setting.

---- Why URLs are indirected --------------------------------------------------
A presigned R2 URL expires, so it must never be persisted on a row. A public
bucket URL does not expire, but then the bucket is public. Rather than force
that choice into the data model, every asset is addressed by OUR stable URL
(``/api/storage/o/{token}``) and the storage layer decides per request whether
that redirects to a public object or to a freshly signed one. Rotating the
bucket, going public, or moving vendor never invalidates a stored URL.
"""
from __future__ import annotations

import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class StorageError(RuntimeError):
    """A storage operation failed (network, credentials, missing object)."""


class StorageConfigError(StorageError):
    """The selected backend is not configured (missing bucket or credentials)."""


class ObjectNotFound(StorageError):
    """No object exists at that key.

    Separate from StorageError so a caller can tell "the file is gone" from
    "the bucket is unreachable" — the first is a 404 to the user, the second is
    a 502, and collapsing them makes an outage look like a deleted file.
    """


@dataclass(frozen=True)
class StoredObject:
    """What a successful write hands back.

    `key` is the only durable handle. `size_bytes` and `content_type` are
    echoed so a caller can persist them without re-reading the object.
    """

    key: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class ObjectMetadata:
    """What the store knows about an object without downloading it.

    Exists so an integrity check ("does the row's size still match the
    bucket?") and a conditional-GET header do not require pulling a 40 MB
    render back through the API process.

    `etag` and `last_modified` are None on backends that do not report them.
    """

    key: str
    content_type: str
    size_bytes: int
    last_modified: datetime | None = None
    etag: str | None = None


def extension_for(content_type: str) -> str:
    """A file extension for a MIME type, without the dot. Never empty.

    Keys carry an extension purely so a downloaded file opens in the right
    application and so a bucket listing is readable by a human — nothing in the
    app parses it back.
    """
    known = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mp4": "m4a",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/webm": "weba",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/webm": "webm",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
        "text/vtt": "vtt",
        "application/x-subrip": "srt",
        "text/plain": "txt",
        "application/json": "json",
    }
    if content_type in known:
        return known[content_type]
    guessed = mimetypes.guess_extension(content_type or "") or ".bin"
    return guessed.lstrip(".")


class ObjectStorage(ABC):
    """The contract every backend implements.

    Deliberately seven methods: write, read, delete, existence, metadata, a
    URL that serves the object now, and an explicitly time-boxed private URL.
    Anything richer (multipart uploads, lifecycle rules, copy-in-place) belongs
    to a specific backend and would make swapping one out a rewrite rather
    than a setting.
    """

    #: Stable identifier, reported by /health and the storage info endpoint.
    name: str = "base"

    @abstractmethod
    def put(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> StoredObject:
        """Write bytes at `key`, overwriting any object already there."""
        raise NotImplementedError

    @abstractmethod
    def get(self, key: str) -> tuple[bytes, str]:
        """Read an object back as (bytes, content_type).

        Raises ObjectNotFound when there is nothing at `key`.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove an object. Deleting a key that is already gone is a no-op."""
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stat(self, key: str) -> ObjectMetadata:
        """Size, type and modification time, without downloading the bytes.

        Raises ObjectNotFound when there is nothing at `key`.
        """
        raise NotImplementedError

    @abstractmethod
    def url_for(self, key: str, *, download_name: str | None = None) -> str:
        """A URL that serves this object right now.

        May be short-lived — callers must fetch it, not store it. The durable
        address of an asset is its row's ``/api/storage/o/{token}`` URL, which
        resolves through here on every request.
        """
        raise NotImplementedError

    @abstractmethod
    def signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_name: str | None = None,
    ) -> str:
        """A URL that expires, regardless of whether the bucket is public.

        Distinct from `url_for` on purpose. `url_for` answers "how do I serve
        this now" and will happily return a permanent public URL when the
        bucket has one. This one is for the cases where a time box is the
        point — handing a user a download link, or letting a platform fetch an
        asset once — and it must never return something permanent.
        """
        raise NotImplementedError
