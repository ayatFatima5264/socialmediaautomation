"""Asset ingest — bytes in, a durable, addressable VideoAsset row out.

Every file that enters Video Studio goes through `store_asset`, whether it came
from a browser upload, a voice synthesis, a subtitle export or a finished
render. One door means one place that:

  * writes to object storage and records which backend took it,
  * probes the file so duration and dimensions are measured, not claimed,
  * meters the bytes,
  * and rolls the object back if the database row cannot be written.

That last point is the reason this is a module and not four call sites. A row
without an object is a broken asset the user can see; an object without a row is
an invisible bill. Neither is acceptable, so the write order is
object-then-row, with a compensating delete when the row fails.
"""
from __future__ import annotations

import hashlib
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.video_asset import ASSET_KINDS, VideoAsset
from app.services.storage import build_key, get_storage
from app.services.storage.base import StorageError
from app.services.video import metering
from app.services.video.ffmpeg import FFmpegError, probe_bytes
from app.services.storage.base import extension_for

logger = logging.getLogger(__name__)


class AssetError(RuntimeError):
    """An asset could not be stored or read."""


class AssetNotFound(AssetError):
    """No such asset — or it belongs to somebody else.

    One exception for both, for the same reason projects have one: telling them
    apart confirms that an id exists.
    """


# Content types Video Studio accepts on ingest. Wider than the publishing
# whitelist in routes/media.py because this library holds working files, not
# only things a platform will fetch — but still a closed list, so this cannot
# become a general-purpose file host.
ACCEPTED_TYPES = {
    # video
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    # audio
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/aac",
    "audio/ogg",
    "audio/webm",
    "audio/flac",
    # images
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    # subtitles and text
    "text/vtt",
    "application/x-subrip",
    "text/plain",
}

# Kinds whose duration and dimensions are worth measuring. Probing a subtitle
# file would only ever fail.
_PROBEABLE = {"upload", "voice", "music", "video", "image", "render"}


def max_upload_bytes() -> int:
    return settings.video_max_upload_mb * 1024 * 1024


def digest(data: bytes) -> str:
    """The SHA-256 of some bytes, hex — an asset's content identity.

    SHA-256 rather than something faster because this is also what decides
    whether two files are "the same" for the user. A collision here would
    silently hand somebody a different video than the one they uploaded, which
    is not a trade worth a few milliseconds on a file we are about to send over
    the network anyway.
    """
    return hashlib.sha256(data).hexdigest()


def find_duplicate(
    db: Session, *, user_id: int, kind: str, checksum: str
) -> VideoAsset | None:
    """This user's existing asset with these exact bytes, if there is one.

    Scoped to the user deliberately. Two accounts uploading the same stock clip
    keep their own copies: sharing the object would make one user's delete take
    away another's file, and would leak the fact that somebody else has it.

    Matched on `kind` as well as the digest because the kind decides where the
    object lives and how the library groups it — the same MP3 added once as a
    voice-over and once as a music bed is two different things to the studio,
    even though the bytes are identical.
    """
    if not checksum:
        return None
    return db.scalars(
        select(VideoAsset)
        .where(
            VideoAsset.user_id == user_id,
            VideoAsset.kind == kind,
            VideoAsset.checksum == checksum,
        )
        .order_by(VideoAsset.id)
        .limit(1)
    ).first()


def normalize_content_type(raw: str | None, filename: str | None = None) -> str:
    """A bare, lowercase MIME type, guessed from the name when absent.

    Browsers send `audio/mpeg; codecs=...` and, for less common types, nothing
    at all — an .srt upload routinely arrives as an empty string.
    """
    value = (raw or "").split(";")[0].strip().lower()
    if value and value != "application/octet-stream":
        return value

    name = (filename or "").lower()
    by_extension = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".srt": "application/x-subrip",
        ".vtt": "text/vtt",
        ".txt": "text/plain",
    }
    for extension, mime in by_extension.items():
        if name.endswith(extension):
            return mime
    return value or "application/octet-stream"


def store_asset(
    db: Session,
    *,
    user_id: int,
    kind: str,
    data: bytes,
    content_type: str,
    title: str | None = None,
    filename: str | None = None,
    project_id: int | None = None,
    meta: dict | None = None,
    probe: bool = True,
    duration_seconds: float | None = None,
    width: int | None = None,
    height: int | None = None,
    dedupe: bool = False,
    commit: bool = True,
) -> VideoAsset:
    """Write bytes to object storage and record them as a VideoAsset.

    `duration_seconds` / `width` / `height` override probing — used when the
    producer already knows them exactly (a synthesizer that measured its own
    output, a renderer that chose the canvas size) so the file is not decoded
    twice.

    `dedupe` returns this user's existing asset when the bytes are already in
    their library, instead of storing a second copy. It is **opt-in**, because
    it is only ever right for a file the user is *adding*:

      * The Media Library and the music uploader pass True — dropping the same
        clip in twice should not be billed twice, and the user's intent is "I
        want this file available", which an existing row already satisfies.
      * Voice-overs, renders and subtitle exports pass False (the default).
        Regenerating a take with identical settings produces identical bytes,
        and handing back the previous take would make "Regenerate" look broken
        and would lose the new take's own metadata.

    The digest is computed and stored either way, so an asset written before
    anyone asked for dedupe is still a candidate for the next one.

    Raises AssetError for anything the caller should report: an empty file, a
    rejected type, an oversized upload, or a storage failure.
    """
    if kind not in ASSET_KINDS:
        raise AssetError(f"Unknown asset kind {kind!r}.")
    if not data:
        raise AssetError("That file is empty.")

    limit = max_upload_bytes()
    if len(data) > limit:
        raise AssetError(
            f"That file is {len(data) / (1024 * 1024):.0f} MB. The limit is "
            f"{settings.video_max_upload_mb} MB."
        )

    content_type = normalize_content_type(content_type, filename)
    if content_type not in ACCEPTED_TYPES:
        raise AssetError(
            f"{content_type} files cannot be added to Video Studio."
        )

    # ---- identify -------------------------------------------------------
    # Before probing and before touching the bucket: a file the user already
    # has should cost neither an ffmpeg decode nor a PUT.
    checksum = digest(data)
    if dedupe:
        existing = find_duplicate(
            db, user_id=user_id, kind=kind, checksum=checksum
        )
        if existing is not None:
            # Attach it to the project this call was for, if it is not in one.
            # Re-adding a library file to the project you are working on should
            # do the obvious thing; moving it out of a *different* project it is
            # already in would be an edit nobody asked for.
            if project_id is not None and existing.project_id is None:
                existing.project_id = project_id
                if commit:
                    db.commit()
                    db.refresh(existing)
                else:
                    db.flush()
            logger.info(
                "Reused asset %s for user %s instead of storing a duplicate",
                existing.id, user_id,
            )
            return existing

    # ---- measure --------------------------------------------------------
    if probe and kind in _PROBEABLE and duration_seconds is None:
        try:
            info = probe_bytes(
                data, suffix=f".{extension_for(content_type)}"
            )
            duration_seconds = info.duration_seconds or None
            width = width or info.width
            height = height or info.height
        except FFmpegError as exc:
            # A file ffmpeg cannot decode is not a file the renderer can use,
            # so this is a rejection rather than a missing-metadata warning.
            raise AssetError(str(exc)) from exc

    # ---- store ----------------------------------------------------------
    storage = get_storage()
    key, token = build_key(user_id=user_id, kind=kind, content_type=content_type)

    try:
        stored = storage.put(
            key=key, data=data, content_type=content_type, filename=filename
        )
    except StorageError as exc:
        raise AssetError(f"Could not store that file: {exc}") from exc

    asset = VideoAsset(
        user_id=user_id,
        project_id=project_id,
        kind=kind,
        title=(title or filename or "Untitled")[:200],
        filename=filename,
        token=token,
        storage_key=stored.key,
        storage_backend=storage.name,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        checksum=checksum,
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        meta=meta or {},
    )
    db.add(asset)

    try:
        if commit:
            db.commit()
            db.refresh(asset)
        else:
            db.flush()
    except Exception:
        # The object is already in the bucket. Leaving it there would be an
        # invisible, unreferenced cost that nothing will ever clean up.
        db.rollback()
        try:
            storage.delete(stored.key)
        except StorageError:
            logger.exception("Orphaned storage object %s after a failed insert", stored.key)
        raise

    metering.record(
        db,
        user_id=user_id,
        metric="storage_bytes",
        quantity=stored.size_bytes,
        source=f"asset:{kind}",
        project_id=project_id,
        meta={"content_type": content_type},
        commit=commit,
    )

    logger.info(
        "Stored %s asset %s (%s, %d bytes) for user %s via %s",
        kind, token[:8], content_type, stored.size_bytes, user_id, storage.name,
    )
    return asset


def get_asset(db: Session, *, user_id: int, asset_id: int) -> VideoAsset:
    """One asset, scoped to its owner.

    Ownership is part of the query rather than a check after the fetch — the
    same rule `projects.get_project` follows, and for the same reason.
    """
    asset = db.scalars(
        select(VideoAsset).where(
            VideoAsset.id == asset_id, VideoAsset.user_id == user_id
        )
    ).first()
    if asset is None:
        raise AssetNotFound("That file does not exist.")
    return asset


def get_asset_by_token(db: Session, token: str) -> VideoAsset:
    """One asset by its public token. Deliberately NOT scoped to a user.

    This is what the public read route uses. A social platform fetching an
    asset to publish it arrives with no credentials of ours, so the unguessable
    token — not a session — is the boundary. It is 32 bytes of `secrets`
    output, the same construction `media_assets` has used in production.
    """
    asset = db.scalars(select(VideoAsset).where(VideoAsset.token == token)).first()
    if asset is None:
        raise AssetNotFound("That file does not exist.")
    return asset


def read_asset(asset: VideoAsset) -> tuple[bytes, str]:
    """The bytes behind an asset, from whichever backend holds them."""
    try:
        return get_storage().get(asset.storage_key)
    except StorageError as exc:
        raise AssetError(str(exc)) from exc


def asset_metadata(asset: VideoAsset):
    """What the bucket says about this asset's object, without downloading it.

    Used to verify a row against reality — a `size_bytes` that no longer
    matches means the object was replaced or truncated, which is worth knowing
    before a render tries to use it.
    """
    try:
        return get_storage().stat(asset.storage_key)
    except StorageError as exc:
        raise AssetError(str(exc)) from exc


def download_url(asset: VideoAsset, *, expires_in: int | None = None) -> str:
    """A time-boxed URL that downloads this asset under its own filename."""
    try:
        return get_storage().signed_url(
            asset.storage_key,
            expires_in=expires_in,
            download_name=asset.filename or f"{asset.kind}.{asset.content_type.split('/')[-1]}",
        )
    except StorageError as exc:
        raise AssetError(str(exc)) from exc


def delete_asset(db: Session, asset: VideoAsset, *, commit: bool = True) -> None:
    """Remove an asset and the object behind it.

    The row goes first. An object left behind costs storage; a row pointing at
    a deleted object is a broken link in the user's library, and of the two, the
    silent cost is the recoverable one.
    """
    key = asset.storage_key
    db.delete(asset)
    if commit:
        db.commit()

    try:
        get_storage().delete(key)
    except StorageError:
        logger.exception("Could not delete storage object %s", key)


def user_assets(
    db: Session,
    *,
    user_id: int,
    kind: str | None = None,
    project_id: int | None = None,
    limit: int = 100,
) -> list[VideoAsset]:
    """A user's assets, newest first. Scoped by kind and/or project."""
    query = select(VideoAsset).where(VideoAsset.user_id == user_id)
    if kind:
        query = query.where(VideoAsset.kind == kind)
    if project_id is not None:
        query = query.where(VideoAsset.project_id == project_id)
    # `id` breaks the tie. `created_at` alone is not enough: its resolution is
    # one second on SQLite, so two voice-overs generated in the same second
    # come back in arbitrary order — and "newest first" that reshuffles on
    # every reload is worse than no ordering at all.
    query = query.order_by(
        VideoAsset.created_at.desc(), VideoAsset.id.desc()
    ).limit(min(limit, 500))
    return list(db.scalars(query).all())


# ---------------------------------------------------------------------------
# Media Library queries
# ---------------------------------------------------------------------------
# `user_assets` above answers "the newest N of this kind", which is what the
# studios' side panels want. The library screen needs something else: several
# kinds at once, a text search, a stable sort the user chose, and a total so
# the page can say "24 of 310". Kept here rather than in the route so a picker
# dialog and the full-page library ask the same question the same way.

# What each sort option means, as columns rather than as a string the route
# interpolates — an ORDER BY built from user input is how a query becomes an
# injection.
ASSET_SORTS = {
    "newest": (VideoAsset.created_at.desc(), VideoAsset.id.desc()),
    "oldest": (VideoAsset.created_at.asc(), VideoAsset.id.asc()),
    "name": (VideoAsset.title.asc(), VideoAsset.id.asc()),
    "largest": (VideoAsset.size_bytes.desc(), VideoAsset.id.desc()),
    "longest": (VideoAsset.duration_seconds.desc().nullslast(), VideoAsset.id.desc()),
}
DEFAULT_ASSET_SORT = "newest"


def _library_query(
    *,
    user_id: int,
    kinds: list[str] | None,
    search: str | None,
    project_id: int | None,
    unassigned: bool,
):
    """The WHERE clause shared by the listing and its count.

    One builder for both so a filter can never apply to the rows and not to the
    total — a library that says "12 of 300" while showing 12 filtered results
    out of 40 is worse than showing no total at all.
    """
    query = select(VideoAsset).where(VideoAsset.user_id == user_id)

    if kinds:
        query = query.where(VideoAsset.kind.in_(kinds))

    if search:
        # Both the display title and the original filename: people look for
        # "the one called beach" and for "IMG_4821.MOV", and only one of those
        # is the title.
        pattern = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(VideoAsset.title).like(pattern),
                func.lower(func.coalesce(VideoAsset.filename, "")).like(pattern),
            )
        )

    # `unassigned` and `project_id` are different questions, and both are
    # asked: the library's "Not in a project" filter, and a project's own
    # media panel. They are mutually exclusive, so `project_id` wins when a
    # caller sends both rather than returning the empty intersection.
    if project_id is not None:
        query = query.where(VideoAsset.project_id == project_id)
    elif unassigned:
        query = query.where(VideoAsset.project_id.is_(None))

    return query


def search_assets(
    db: Session,
    *,
    user_id: int,
    kinds: list[str] | None = None,
    search: str | None = None,
    project_id: int | None = None,
    unassigned: bool = False,
    sort: str = DEFAULT_ASSET_SORT,
    limit: int = 60,
    offset: int = 0,
) -> list[VideoAsset]:
    """A page of the library, filtered and sorted. Always one user's."""
    query = _library_query(
        user_id=user_id,
        kinds=kinds,
        search=search,
        project_id=project_id,
        unassigned=unassigned,
    )
    order = ASSET_SORTS.get(sort) or ASSET_SORTS[DEFAULT_ASSET_SORT]
    query = query.order_by(*order).limit(min(limit, 200)).offset(max(offset, 0))
    return list(db.scalars(query).all())


def count_assets(
    db: Session,
    *,
    user_id: int,
    kinds: list[str] | None = None,
    search: str | None = None,
    project_id: int | None = None,
    unassigned: bool = False,
) -> int:
    """How many rows the same filters match, ignoring the page."""
    query = _library_query(
        user_id=user_id,
        kinds=kinds,
        search=search,
        project_id=project_id,
        unassigned=unassigned,
    )
    return int(
        db.scalar(select(func.count()).select_from(query.subquery())) or 0
    )


def kind_counts(db: Session, *, user_id: int) -> dict[str, int]:
    """How many assets this user has of each kind, plus a `total`.

    One grouped query rather than one per kind: the library's filter bar shows
    a count on all eight tabs, and eight COUNT(*) round trips to render a row
    of chips is the kind of thing that makes a page feel slow for no reason.

    Every known kind is present in the result, at zero if the user has none —
    so the UI renders a stable set of tabs rather than one that appears and
    disappears as files are added.
    """
    counts = {kind: 0 for kind in ASSET_KINDS}
    rows = db.execute(
        select(VideoAsset.kind, func.count(VideoAsset.id))
        .where(VideoAsset.user_id == user_id)
        .group_by(VideoAsset.kind)
    ).all()
    for kind, total in rows:
        counts[kind] = int(total or 0)
    counts["total"] = sum(counts[kind] for kind in ASSET_KINDS)
    return counts


def storage_used(db: Session, *, user_id: int) -> int:
    """Total bytes this user's library occupies.

    Summed from the rows rather than from the bucket: the bucket holds every
    user's objects, and listing it to add up one account's would be a full scan
    on every page load.
    """
    return int(
        db.scalar(
            select(func.coalesce(func.sum(VideoAsset.size_bytes), 0)).where(
                VideoAsset.user_id == user_id
            )
        )
        or 0
    )
