"""Object storage for Video Studio. See base.py for the contract and why."""
from app.services.storage.base import (
    ObjectMetadata,
    ObjectNotFound,
    ObjectStorage,
    StorageConfigError,
    StorageError,
    StoredObject,
    extension_for,
)
from app.services.storage.factory import (
    available_backends,
    get_storage,
    reset_storage_cache,
)
from app.services.storage.keys import KINDS, build_key, new_token

__all__ = [
    "ObjectStorage",
    "StoredObject",
    "ObjectMetadata",
    "StorageError",
    "StorageConfigError",
    "ObjectNotFound",
    "extension_for",
    "get_storage",
    "reset_storage_cache",
    "available_backends",
    "build_key",
    "new_token",
    "KINDS",
]
