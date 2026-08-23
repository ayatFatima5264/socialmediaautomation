"""The Media Library — one view over every file Video Studio can use.

`assets.py` is the ingest door and the query layer. This module is the part
that makes those rows a *library*: it says where a file is being used, refuses
to delete one that is holding a project together, and brings in the images the
rest of AutoSocial already has.

Three things live here and nowhere else.

**Usage.** An asset can be referenced from five places — a scene's visual, a
scene's voice-over, an audio layer, a subtitle track, and a project's
thumbnail. `usage_for` answers "where is this used" for a whole page of assets
in five queries rather than five per asset, because the library grid shows a
"used in 2 projects" badge on every card and the naive version is a hundred
round trips to draw one screen.

**Deleting.** A file in use is not deleted by accident. `delete` refuses and
names what is using it; the caller can pass `force=True` once the user has been
told. The references are all `ON DELETE SET NULL`, so a forced delete leaves
the scene or the layer in place with nothing in it — a hole the user can fill,
rather than a scene that vanished.

**Importing.** AutoSocial already has a media library: `media_assets`, the
images uploaded from the post composer, which live as bytes in Postgres and are
published by URL. Video Studio's assets live in object storage. The two cannot
be one table without either putting rendered video in Postgres or rewriting how
the composer publishes, so instead an import copies an image across, once,
through the normal ingest path with de-duplication on. Importing the same photo
into the studio twice produces one object and one row — the second import
returns the first one's asset.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from app.models.media_asset import MediaAsset
from app.models.video_asset import VideoAsset
from app.models.video_audio import VideoAudio
from app.models.video_project import VideoProject
from app.models.video_scene import VideoScene
from app.models.video_subtitle import VideoSubtitle
from app.services.video import assets as asset_service
from app.services.video.assets import AssetError, AssetNotFound  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)


class MediaInUse(AssetError):
    """The asset is referenced by a project and was not deleted.

    Carries the references so the caller can tell the user what will break
    rather than only that something will.
    """

    def __init__(self, message: str, references: list[dict]):
        super().__init__(message)
        self.references = references


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

# Every table that can point at an asset, and the column that does it. Written
# once as data so a new reference cannot be added to the schema and forgotten
# here — the delete guard and the "in use" badge both read this list, and a
# missing entry would silently make both wrong.
_REFERENCES = (
    (VideoScene, VideoScene.asset_id, "scene", "visual"),
    (VideoScene, VideoScene.voice_asset_id, "scene", "voice-over"),
    (VideoAudio, VideoAudio.asset_id, "audio", "audio layer"),
    (VideoSubtitle, VideoSubtitle.asset_id, "subtitle", "subtitle track"),
    (VideoProject, VideoProject.thumbnail_asset_id, "project", "thumbnail"),
)


def usage_for(db: Session, asset_ids: list[int]) -> dict[int, list[dict]]:
    """Where each of these assets is referenced.

    Returns `{asset_id: [{project_id, project_name, role}, ...]}`, with an
    empty list for an asset nothing uses. Five grouped queries total,
    regardless of how many assets are asked about — see the module docstring.

    The project *name* is joined in rather than looked up afterwards, because
    "used in Summer Launch" is what the user needs to decide whether deleting
    is safe; "used in project 47" is not.
    """
    usage: dict[int, list[dict]] = {asset_id: [] for asset_id in asset_ids}
    if not asset_ids:
        return usage

    for model, column, _kind, role in _REFERENCES:
        if model is VideoProject:
            # The project's own thumbnail — no join, the project is the row.
            # Joining VideoProject to itself here would be a self-join
            # SQLAlchemy has to be told how to alias, for no gain.
            statement = select(column, VideoProject.id, VideoProject.name)
        else:
            statement = (
                select(column, model.project_id, VideoProject.name)
                .join(VideoProject, VideoProject.id == model.project_id)
            )

        rows = db.execute(statement.where(column.in_(asset_ids))).all()

        for asset_id, project_id, project_name in rows:
            if asset_id is None:
                continue
            entry = {
                "project_id": int(project_id),
                "project_name": project_name,
                "role": role,
            }
            bucket = usage.setdefault(int(asset_id), [])
            # The same asset used as the visual of three scenes in one project
            # is one line, not three — the badge answers "which projects", and
            # repeating a project name three times reads as a bug.
            if not any(
                existing["project_id"] == entry["project_id"]
                and existing["role"] == entry["role"]
                for existing in bucket
            ):
                bucket.append(entry)

    return usage


def delete(
    db: Session, asset: VideoAsset, *, force: bool = False
) -> None:
    """Delete an asset, refusing by default if a project is using it.

    Raises `MediaInUse` with the references when it refuses. `force=True` is
    the user having seen that list and said yes anyway; the references become
    NULL and the projects keep their structure.
    """
    references = usage_for(db, [asset.id]).get(asset.id) or []

    if references and not force:
        names = sorted({reference["project_name"] for reference in references})
        listed = ", ".join(f"“{name}”" for name in names[:3])
        if len(names) > 3:
            listed += f" and {len(names) - 3} more"
        raise MediaInUse(
            f"“{asset.title}” is used in {listed}. Deleting it will leave those "
            f"places empty.",
            references,
        )

    asset_service.delete_asset(db, asset)


def detach(db: Session, asset: VideoAsset) -> VideoAsset:
    """Take an asset out of a project without deleting it.

    The mirror of `projects.attach_asset`. The file stays in the user's
    library — this is "remove from this project", not "throw away", and the
    two must not be the same button.
    """
    asset.project_id = None
    db.commit()
    db.refresh(asset)
    return asset


def rename(db: Session, asset: VideoAsset, *, title: str) -> VideoAsset:
    """Give an asset a name a human chose.

    Uploads arrive titled `IMG_4821.MOV`, which is not findable six weeks
    later. The original filename is kept on the row either way, so search still
    matches what the camera called it.
    """
    cleaned = (title or "").strip()
    if not cleaned:
        raise AssetError("A file needs a name.")
    asset.title = cleaned[:200]
    db.commit()
    db.refresh(asset)
    return asset


# ---------------------------------------------------------------------------
# The rest of AutoSocial's media library
# ---------------------------------------------------------------------------


def list_uploads(
    db: Session,
    *,
    user_id: int,
    search: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> tuple[list[MediaAsset], int]:
    """The composer's uploaded images, newest first, with the total.

    These are `media_assets` rows — the images the user has already uploaded
    for ordinary posts. Video Studio lists them so somebody who uploaded a
    product photo last week does not have to find the file again to put it in a
    video.

    **`data` is deferred, and that is not an optimisation — it is the
    difference between a page that works and one that does not.** `MediaAsset`
    keeps its bytes in a `LargeBinary` column on the row, so a plain
    `select(MediaAsset)` for sixty images pulls every one of those images into
    this process to render a grid of thumbnails the browser is going to fetch
    by URL anyway. `defer` leaves the column on disk until something actually
    touches it, which nothing here does.
    """
    conditions = [MediaAsset.user_id == user_id]
    if search:
        pattern = f"%{search.strip().lower()}%"
        conditions.append(
            func.lower(func.coalesce(MediaAsset.filename, "")).like(pattern)
        )

    # Counted with its own COUNT over the id column rather than by wrapping the
    # row query in a subquery: a subquery of `select(MediaAsset)` still names
    # every column, `data` included, which puts the bytes back into the plan
    # the defer above just took out of it.
    total = int(
        db.scalar(select(func.count(MediaAsset.id)).where(*conditions)) or 0
    )

    rows = list(
        db.scalars(
            select(MediaAsset)
            .options(defer(MediaAsset.data))
            .where(*conditions)
            .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
            .limit(min(limit, 200))
            .offset(max(offset, 0))
        ).all()
    )
    return rows, total


def imported_media_ids(db: Session, *, user_id: int) -> dict[int, int]:
    """`{media_asset_id: video_asset_id}` for images already imported.

    Lets the uploads listing mark which ones are in Video Studio, so the button
    reads "In your library" instead of offering an import that would just hand
    back the same row.

    Matched on the `media_asset_id` that `import_upload` records in the asset's
    `meta`, **not** by re-hashing the images. Hashing would mean reading every
    upload's bytes out of Postgres on every page load — the exact cost the
    deferred column above exists to avoid.

    The meta is filtered in Python rather than with a JSON path expression
    because those are spelled differently on SQLite and Postgres, and this
    module is not worth making dialect-specific for a dictionary lookup over
    one user's images.
    """
    rows = db.scalars(
        select(VideoAsset)
        .where(
            VideoAsset.user_id == user_id,
            VideoAsset.kind.in_(("image", "upload")),
        )
        .order_by(VideoAsset.id)
    ).all()

    out: dict[int, int] = {}
    for asset in rows:
        media_id = (asset.meta or {}).get("media_asset_id")
        if isinstance(media_id, int):
            # First one wins: a re-import returns the original asset, so the
            # oldest row is the one the button should point at.
            out.setdefault(media_id, asset.id)
    return out


def import_upload(
    db: Session,
    *,
    user_id: int,
    media_id: int,
    project_id: int | None = None,
) -> VideoAsset:
    """Copy a composer upload into Video Studio's library.

    De-duplicated: importing the same image twice returns the asset made the
    first time rather than paying for a second object. That is what makes this
    safe to offer as a plain "Add to Video Studio" button with no warning about
    doing it twice.

    The MediaAsset is left exactly as it is — the composer still needs it, and
    its public URL is on scheduled posts that have not gone out yet.
    """
    upload = db.scalars(
        select(MediaAsset).where(
            MediaAsset.id == media_id, MediaAsset.user_id == user_id
        )
    ).first()
    if upload is None:
        raise AssetNotFound("That upload does not exist.")

    title = (upload.filename or "Uploaded image").rsplit(".", 1)[0][:200]

    return asset_service.store_asset(
        db,
        user_id=user_id,
        kind="image",
        data=upload.data,
        content_type=upload.content_type,
        title=title,
        filename=upload.filename,
        project_id=project_id,
        dedupe=True,
        meta={
            # Where it came from, so the library can say "imported from your
            # uploads" and so a future cleanup can tell an import from a file
            # that only ever existed here.
            "source": "media_library",
            "media_asset_id": upload.id,
            "media_token": upload.token,
        },
    )


# ---------------------------------------------------------------------------
# Facets
# ---------------------------------------------------------------------------

# How the library's filter bar groups kinds. The order is the order of the
# tabs; the label is what the tab says. `kinds` is a list because the UI's
# categories are coarser than the storage kinds — "Video" means both a clip the
# user uploaded and a finished render, and nobody looking for a video thinks of
# those as different tabs.
MEDIA_FILTERS = (
    {"key": "all", "label": "All", "kinds": []},
    {"key": "image", "label": "Images", "kinds": ["image"]},
    {"key": "video", "label": "Videos", "kinds": ["video", "render"]},
    {"key": "audio", "label": "Audio", "kinds": ["upload"]},
    {"key": "voice", "label": "Voice-over", "kinds": ["voice"]},
    {"key": "music", "label": "Music", "kinds": ["music"]},
    {"key": "subtitle", "label": "Subtitles", "kinds": ["subtitle"]},
    {"key": "thumbnail", "label": "Thumbnails", "kinds": ["thumbnail"]},
)

_FILTERS_BY_KEY = {entry["key"]: entry for entry in MEDIA_FILTERS}


def kinds_for_filter(key: str | None) -> list[str]:
    """The storage kinds behind a filter tab. Unknown or "all" means no filter.

    An unknown key returning "everything" rather than "nothing" is deliberate:
    a stale bookmark or an old build asking for a tab that no longer exists
    should show the library, not an empty page that looks like data loss.
    """
    entry = _FILTERS_BY_KEY.get((key or "all").lower())
    return list(entry["kinds"]) if entry else []


def facets(db: Session, *, user_id: int) -> list[dict]:
    """The filter tabs with a live count on each one."""
    counts = asset_service.kind_counts(db, user_id=user_id)
    out = []
    for entry in MEDIA_FILTERS:
        total = (
            counts["total"]
            if not entry["kinds"]
            else sum(counts.get(kind, 0) for kind in entry["kinds"])
        )
        out.append({"key": entry["key"], "label": entry["label"], "count": total})
    return out
