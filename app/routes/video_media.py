"""Media Library endpoints — one screen over every file the studio can use.

    GET    /api/video/media            search, filter and page the library
    POST   /api/video/media/upload     add a file (de-duplicated)
    PATCH  /api/video/media/{id}       rename
    POST   /api/video/media/{id}/attach   add to a project
    POST   /api/video/media/{id}/detach   take out of a project, keep the file
    DELETE /api/video/media/{id}       delete, refusing if it is in use
    GET    /api/video/media/uploads    the post composer's images
    POST   /api/video/media/uploads/import   bring one into Video Studio

Every route is authenticated and every query is scoped to the signed-in user.
There is no endpoint here that takes a user id — the public read for an asset
is `GET /api/storage/o/{token}`, which lives in routes/video.py and is public
for the reason documented there.

**Two things this router is careful about.**

*Deleting is guarded, not blocked.* `DELETE` refuses with 409 and lists what is
using the file. The client shows that list and can retry with `?force=true`.
Refusing outright would make the library a place files accumulate and can never
leave; deleting silently would let somebody empty a project they were mid-way
through without ever seeing a warning.

*Uploading de-duplicates.* The same file added twice returns the row from the
first time and stores nothing new, so the response is 200 rather than 201 —
"here it is", not "created". A client that wants to know can compare the id.
"""
from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.schemas.video_media import (
    AssetUsage,
    MediaFilter,
    MediaImport,
    MediaItem,
    MediaList,
    MediaRename,
    UploadItem,
    UploadList,
)
from app.services.storage.base import StorageError
from app.services.video import assets as asset_service
from app.services.video import media as media_service
from app.services.video import projects as project_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video/media", tags=["media-library"])


def _http(exc: Exception) -> HTTPException:
    """Map a service error onto a status code.

    409 for "in use" specifically: it is not a bad request — the request was
    understood and is valid — it conflicts with the current state, and the
    client is expected to resolve it and retry with `force`.
    """
    if isinstance(exc, media_service.MediaInUse):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, asset_service.AssetNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, StorageError):
        return HTTPException(
            status_code=502,
            detail="The file store could not be reached. Try again in a moment.",
        )
    return HTTPException(status_code=422, detail=str(exc))


def _asset_url(asset: VideoAsset) -> str:
    """The durable address of an asset — ours, never the bucket's.

    Same construction as routes/video.py uses, and for the reason documented
    there: a presigned URL expires and a public bucket URL pins the row to
    whichever backend produced it.
    """
    return f"{settings.backend_url}/api/storage/o/{asset.token}"


def _item(asset: VideoAsset, usage: list[dict] | None = None) -> MediaItem:
    return MediaItem(
        id=asset.id,
        project_id=asset.project_id,
        kind=asset.kind,
        title=asset.title,
        filename=asset.filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        duration_seconds=asset.duration_seconds,
        width=asset.width,
        height=asset.height,
        url=_asset_url(asset),
        created_at=asset.created_at,
        usage=[AssetUsage(**entry) for entry in (usage or [])],
    )


# ---------------------------------------------------------------------------
# The library
# ---------------------------------------------------------------------------


@router.get("", response_model=MediaList)
def list_media(
    filter: str = Query(default="all", max_length=40),
    search: str | None = Query(default=None, max_length=200),
    project_id: int | None = None,
    unassigned: bool = False,
    sort: str = Query(default="newest", max_length=20),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaList:
    """A page of this user's files.

    `filter` is a tab key ("images", "videos", …), not a raw storage kind — see
    MEDIA_FILTERS. The mapping lives server-side so the tabs can be regrouped
    without shipping a frontend, and so an unknown key degrades to "everything"
    rather than to an empty page.

    Usage is resolved for the page in one pass, not per item.
    """
    kinds = media_service.kinds_for_filter(filter)

    rows = asset_service.search_assets(
        db,
        user_id=user.id,
        kinds=kinds,
        search=search,
        project_id=project_id,
        unassigned=unassigned,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    total = asset_service.count_assets(
        db,
        user_id=user.id,
        kinds=kinds,
        search=search,
        project_id=project_id,
        unassigned=unassigned,
    )

    usage = media_service.usage_for(db, [row.id for row in rows])

    return MediaList(
        items=[_item(row, usage.get(row.id)) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        filters=[
            MediaFilter(**entry) for entry in media_service.facets(db, user_id=user.id)
        ],
        storage_bytes=asset_service.storage_used(db, user_id=user.id),
    )


@router.post("/upload", response_model=MediaItem)
async def upload_media(
    file: UploadFile = File(...),
    kind: str = Form(default="upload"),
    title: str | None = Form(default=None),
    project_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaItem:
    """Add a file to the library.

    De-duplicated: the same bytes uploaded twice return the existing asset and
    store nothing new. The status stays 200 rather than 201 for exactly that
    reason — this endpoint does not promise it created anything.

    `kind` is taken from the form rather than sniffed, because the same MP3 is
    a voice-over, a music bed or a plain upload depending on what the user is
    doing with it, and the file cannot say which.
    """
    if project_id is not None:
        # Validated before the bytes are read: rejecting a 200 MB upload after
        # streaming it because the project id was wrong is a waste of the
        # user's connection.
        try:
            project_service.get_project(db, user_id=user.id, project_id=project_id)
        except project_service.ProjectError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    data = await file.read()

    try:
        asset = asset_service.store_asset(
            db,
            user_id=user.id,
            kind=kind,
            data=data,
            content_type=file.content_type or "",
            title=title or file.filename,
            filename=file.filename,
            project_id=project_id,
            dedupe=True,
            meta={"source": "media_library"},
        )
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    usage = media_service.usage_for(db, [asset.id])
    return _item(asset, usage.get(asset.id))


@router.patch("/{asset_id}", response_model=MediaItem)
def rename_media(
    asset_id: int,
    body: MediaRename,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaItem:
    """Give a file a name a human chose. The original filename is kept."""
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
        media_service.rename(db, asset, title=body.title)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    usage = media_service.usage_for(db, [asset.id])
    return _item(asset, usage.get(asset.id))


@router.post("/{asset_id}/attach", response_model=MediaItem)
def attach_media(
    asset_id: int,
    project_id: int = Query(..., description="The project to add this file to."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaItem:
    """Make a library file available inside a project.

    Deliberately does not place it on the timeline — the same rule voice-overs
    follow. Adding a clip to a project makes it reachable there; where it sits
    is an editing decision.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
        project = project_service.get_project(
            db, user_id=user.id, project_id=project_id
        )
        project_service.attach_asset(db, project=project, asset=asset)
    except (asset_service.AssetError, project_service.ProjectError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    usage = media_service.usage_for(db, [asset.id])
    return _item(asset, usage.get(asset.id))


@router.post("/{asset_id}/detach", response_model=MediaItem)
def detach_media(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaItem:
    """Take a file out of a project without deleting it.

    A separate endpoint from DELETE on purpose. "Remove from this project" and
    "throw this file away" are different intentions, and a library that
    conflates them loses somebody's footage the first time they tidy up.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
        media_service.detach(db, asset)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    usage = media_service.usage_for(db, [asset.id])
    return _item(asset, usage.get(asset.id))


@router.delete("/{asset_id}", status_code=204)
def delete_media(
    asset_id: int,
    force: bool = Query(
        default=False,
        description="Delete even though projects are using this file.",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Delete a file. 409 with the list of users if it is in a project.

    The references are `ON DELETE SET NULL`, so a forced delete leaves the
    scene or layer in place and empty — a hole the user can fill, rather than
    structure that silently disappeared.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
        media_service.delete(db, asset, force=force)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# The rest of AutoSocial's media library
# ---------------------------------------------------------------------------


@router.get("/uploads", response_model=UploadList)
def list_uploads(
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=60, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadList:
    """Images already uploaded from the post composer.

    Listed here so somebody who uploaded a product photo for a post last week
    can put it in a video without finding the original file again.

    They are shown as a separate source rather than merged into the library,
    because they are not Video Studio assets: they cannot be deleted from here
    (a scheduled post may still be pointing at one) and they have to be
    imported before the studio can use them.
    """
    rows, total = media_service.list_uploads(
        db, user_id=user.id, search=search, limit=limit, offset=offset
    )
    imported = media_service.imported_media_ids(db, user_id=user.id)

    items = []
    for row in rows:
        items.append(
            UploadItem(
                id=row.id,
                token=row.token,
                # The composer's own public URL, which is already how the rest
                # of the app addresses these. Note that nothing here touches
                # `row.data` — the column is deferred, and reading it would
                # pull every image in the page out of the database.
                url=f"{settings.backend_url}/api/media/{row.token}",
                filename=row.filename,
                content_type=row.content_type,
                size_bytes=row.size_bytes,
                created_at=row.created_at,
                imported_asset_id=imported.get(row.id),
            )
        )

    return UploadList(items=items, total=total, limit=limit, offset=offset)


@router.post("/uploads/import", response_model=MediaItem)
def import_upload(
    body: MediaImport,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MediaItem:
    """Copy a composer upload into Video Studio's library.

    Idempotent through de-duplication: importing the same image twice returns
    the asset made the first time. The `media_assets` row is untouched — the
    composer still needs it, and scheduled posts may already carry its URL.
    """
    if body.project_id is not None:
        try:
            project_service.get_project(
                db, user_id=user.id, project_id=body.project_id
            )
        except project_service.ProjectError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        asset = media_service.import_upload(
            db,
            user_id=user.id,
            media_id=body.media_id,
            project_id=body.project_id,
        )
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    usage = media_service.usage_for(db, [asset.id])
    return _item(asset, usage.get(asset.id))
