"""Cloudflare R2 — the production object store.

R2 speaks the S3 API, so this is a boto3 client pointed at the account's R2
endpoint. Nothing here is R2-specific beyond that endpoint and the fact that R2
charges no egress, which is why it was chosen over S3 for video delivery.

Reads go one of two ways:
  * `R2_PUBLIC_BASE_URL` set — the bucket (or a custom domain in front of it)
    serves objects directly, and `url_for` returns that permanent URL.
  * unset — the bucket stays private and `url_for` presigns a GET that expires
    after `storage_signed_url_ttl`.

Either way callers reach the object through `/api/storage/o/{token}`, so the
bucket can be flipped between the two without touching a single stored row.
"""
from __future__ import annotations

import logging
from functools import cached_property

from app.config import settings
from app.services.storage.base import (
    ObjectMetadata,
    ObjectNotFound,
    ObjectStorage,
    StorageConfigError,
    StorageError,
    StoredObject,
)

logger = logging.getLogger(__name__)

# What S3 calls a missing object. Checked by code rather than by exception type
# because botocore builds its exception classes dynamically, so
# `except client.exceptions.NoSuchKey` can only be written once a client
# exists — and this module has to be importable without credentials.
_MISSING_CODES = {"404", "NoSuchKey", "NotFound"}


def _is_missing(exc: Exception) -> bool:
    """Is this botocore error 'no such object' rather than a real failure?"""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error") or {}
    status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
    return str(error.get("Code")) in _MISSING_CODES or status == 404


def r2_endpoint() -> str | None:
    """The S3-compatible endpoint for the configured account, if any."""
    if settings.r2_endpoint:
        return settings.r2_endpoint.rstrip("/")
    if settings.r2_account_id:
        return f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    return None


def is_configured() -> bool:
    """Are all four values R2 needs present? Used by the `auto` backend."""
    return bool(
        r2_endpoint()
        and settings.r2_bucket
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
    )


class R2Storage(ObjectStorage):
    name = "r2"

    def __init__(self) -> None:
        if not is_configured():
            raise StorageConfigError(
                "Cloudflare R2 is not configured. Set R2_ACCOUNT_ID (or "
                "R2_ENDPOINT), R2_BUCKET, R2_ACCESS_KEY_ID and "
                "R2_SECRET_ACCESS_KEY."
            )
        self.bucket = settings.r2_bucket
        self.endpoint = r2_endpoint()
        self.public_base = (settings.r2_public_base_url or "").rstrip("/")

    @cached_property
    def _client(self):
        # Imported lazily so the module can be imported (and the factory can
        # report "not configured") on a host where boto3 is absent.
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - packaging problem
            raise StorageConfigError(
                "boto3 is required for the R2 storage backend."
            ) from exc

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            # R2 ignores the region but the SDK insists on one, and it must be
            # this exact value or signing fails.
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    # ---- writes ---------------------------------------------------------

    def put(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> StoredObject:
        extra: dict = {"ContentType": content_type}
        if filename:
            # Quoted so a filename containing a comma or a space cannot split
            # the header into two directives.
            safe = filename.replace('"', "")
            extra["ContentDisposition"] = f'inline; filename="{safe}"'

        try:
            self._client.put_object(
                Bucket=self.bucket, Key=key, Body=data, **extra
            )
        except Exception as exc:  # botocore raises a wide family
            raise StorageError(f"Could not store {key!r} in R2: {exc}") from exc

        return StoredObject(
            key=key, content_type=content_type, size_bytes=len(data)
        )

    # ---- reads ----------------------------------------------------------

    def get(self, key: str) -> tuple[bytes, str]:
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
            body = obj["Body"].read()
        except Exception as exc:
            if _is_missing(exc):
                raise ObjectNotFound(f"No stored object at {key!r}.") from exc
            raise StorageError(f"Could not read {key!r} from R2: {exc}") from exc
        return body, obj.get("ContentType", "application/octet-stream")

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            if _is_missing(exc):
                return False
            # A credentials or network failure is not "the file is not there".
            # Reporting it as absence is how an outage turns into a delete.
            raise StorageError(f"Could not check {key!r} in R2: {exc}") from exc

    def stat(self, key: str) -> ObjectMetadata:
        try:
            head = self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_missing(exc):
                raise ObjectNotFound(f"No stored object at {key!r}.") from exc
            raise StorageError(f"Could not stat {key!r} in R2: {exc}") from exc

        return ObjectMetadata(
            key=key,
            content_type=head.get("ContentType") or "application/octet-stream",
            size_bytes=int(head.get("ContentLength") or 0),
            last_modified=head.get("LastModified"),
            # S3 quotes the etag; the quotes are not part of the value.
            etag=(head.get("ETag") or "").strip('"') or None,
        )

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_missing(exc):
                return  # already gone — the contract says this is a no-op
            raise StorageError(f"Could not delete {key!r} from R2: {exc}") from exc

    def url_for(self, key: str, *, download_name: str | None = None) -> str:
        # A public bucket serves the object directly and permanently, which is
        # what makes repeated platform fetches free. A download name forces a
        # signed URL instead: Content-Disposition can only be overridden as a
        # signed response header.
        if self.public_base and not download_name:
            return f"{self.public_base}/{key}"
        return self.signed_url(key, download_name=download_name)

    def signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        download_name: str | None = None,
    ) -> str:
        params: dict = {"Bucket": self.bucket, "Key": key}
        if download_name:
            # Quoted so a filename containing a comma or a space cannot split
            # the header into two directives.
            safe = download_name.replace('"', "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'

        ttl = int(expires_in or settings.storage_signed_url_ttl)
        # A week is S3's own ceiling for SigV4; anything larger is signed and
        # then rejected at fetch time, which is a confusing way to fail.
        ttl = max(1, min(ttl, 7 * 24 * 3600))

        try:
            return self._client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=ttl
            )
        except Exception as exc:
            raise StorageError(f"Could not sign a URL for {key!r}: {exc}") from exc
