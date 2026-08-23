"""Music Library endpoints.

    GET    /api/video/music              search and filter the library
    GET    /api/video/music/facets       moods, genres, durations, suggestions
    POST   /api/video/music/upload       add your own track
    POST   /api/video/music/{id}/add     add a track to a project
    DELETE /api/video/music/{id}         delete one of your uploads
    GET    /api/video/music/credits/{project_id}   the credits a project owes

The library is independent of any project: browsing, previewing and uploading
all work with nothing open, and only `add` takes a project id. That is the same
shape Voice Studio has, and for the same reason — people collect music before
they have a video to put it in.

**The licence is enforced here, not just displayed.** `POST /{id}/add` refuses
a track whose licence does not permit commercial use, with 403 and the reason.
The listing still returns those tracks, marked `can_use: false`, so the user can
see what exists and why they cannot have it — a library that silently hides
results looks broken, and a rule the UI merely draws is a rule that stops being
enforced the first time somebody calls the API directly.

**Search reaches the provider only when it needs to.** The catalogue is a cache
of Openverse results; a query the cache already answers well does not go out to
the network. See `_should_discover`.
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
from app.models.music_track import MusicTrack
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.schemas.video_music import (
    AudioLayerRead,
    FacetOption,
    MusicFacets,
    ProjectCredits,
    TrackAdd,
    TrackList,
    TrackRead,
)
from app.services.storage.base import StorageError
from app.services.video import assets as asset_service
from app.services.video import music as music_service
from app.services.video import projects as project_service
from app.services.video.metering import UsageLimitExceeded

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video/music", tags=["music-library"])

# Below this many local matches, a search is worth sending to the provider.
# Above it, the cache is already giving the user a page to look at and a
# network round trip would only add latency to a screen that is not empty.
DISCOVER_THRESHOLD = 12


def _http(exc: Exception) -> HTTPException:
    """Map a service error onto a status code.

    403 for a licence refusal specifically. It is not a malformed request (422)
    and not a missing thing (404) — it is a request the server understood and
    will not perform, permanently, and no amount of retrying or reformatting
    changes that.
    """
    if isinstance(exc, music_service.LicenseRefused):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, music_service.TrackNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, UsageLimitExceeded):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, StorageError):
        return HTTPException(
            status_code=502,
            detail="The file store could not be reached. Try again in a moment.",
        )
    return HTTPException(status_code=422, detail=str(exc))


def _track_url(db: Session, track: MusicTrack) -> str | None:
    """Where the player should load this track from.

    An upload resolves to our own storage URL; a catalogue track to the
    source's. One field on the response either way, so the player never has to
    branch on where a track came from.
    """
    if track.asset_id is not None:
        asset = db.get(VideoAsset, track.asset_id)
        if asset is not None:
            return f"{settings.backend_url}/api/storage/o/{asset.token}"
        # The asset is gone but the row is not. Returning None gives the UI a
        # track it can show and cannot play, which is the truth.
        return None
    return track.stream_url


def _blocked_reason(track: MusicTrack) -> str | None:
    """Why this track cannot be used, in a sentence, or None if it can.

    Written server-side so the explanation cannot drift from the rule that
    actually refuses the request.
    """
    if track.can_use:
        return None
    if not track.is_active:
        return "This track is no longer available from its source."
    label = music_service.LICENSE_LABELS.get(track.license, track.license)
    return (
        f"Licensed {label}. Videos made here are for business use, which this "
        f"licence does not allow."
    )


def _read(db: Session, track: MusicTrack) -> TrackRead:
    return TrackRead(
        id=track.id,
        title=track.title,
        artist=track.artist,
        source=track.source,
        mood=track.mood,
        genre=track.genre,
        duration_seconds=track.duration_seconds,
        bpm=track.bpm,
        tags=list(track.tags or []),
        license=track.license,
        license_label=music_service.LICENSE_LABELS.get(track.license, track.license),
        license_url=track.license_url,
        attribution=track.attribution,
        source_url=track.source_url,
        can_use=track.can_use,
        requires_attribution=track.needs_attribution,
        blocked_reason=_blocked_reason(track),
        credit=track.credit_line(),
        url=_track_url(db, track),
        content_type=track.content_type,
        size_bytes=track.size_bytes,
        is_hosted=track.asset_id is not None,
        is_owned=track.user_id is not None,
        created_at=track.created_at,
    )


def _should_discover(search: str | None, local_total: int) -> bool:
    """Whether this search is worth sending to the provider.

    Only for an actual text search — browsing by mood or genre is a question
    about what the library already holds, and answering it by fetching more is
    how a filter turns into an unbounded crawl.
    """
    return bool((search or "").strip()) and local_total < DISCOVER_THRESHOLD


# ---------------------------------------------------------------------------
# Browsing
# ---------------------------------------------------------------------------


@router.get("", response_model=TrackList)
async def list_tracks(
    search: str | None = Query(default=None, max_length=200),
    mood: str | None = None,
    genre: str | None = None,
    duration: str | None = None,
    source: str | None = Query(default=None, pattern="^(uploads|catalogue)$"),
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TrackList:
    """A page of the music library.

    A text search that the local catalogue answers thinly is sent on to
    Openverse, whose results are cached and folded into the same query. That is
    what makes the library useful on a fresh deployment, where the catalogue
    starts empty — and it costs nothing on the searches that are already
    covered.

    A provider search that fails is not an error here: `music.fetch_openverse`
    returns an empty list and logs, and the user gets the local results. A music
    screen that goes down because a third party is slow is a worse outcome than
    a short list.
    """
    rows, total = music_service.search_tracks(
        db,
        user_id=user.id,
        search=search,
        mood=mood,
        genre=genre,
        duration=duration,
        source=source,
        limit=limit,
        offset=offset,
    )

    searched = False
    # Only on the first page. Paging through results should not keep firing
    # provider searches — the user is reading, not asking again.
    if offset == 0 and source != "uploads" and _should_discover(search, total):
        await music_service.discover(db, search or "", page_size=limit)
        searched = True
        rows, total = music_service.search_tracks(
            db,
            user_id=user.id,
            search=search,
            mood=mood,
            genre=genre,
            duration=duration,
            source=source,
            limit=limit,
            offset=offset,
        )

    return TrackList(
        items=[_read(db, row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        searched_catalogue=searched,
    )


@router.get("/facets", response_model=MusicFacets)
def facets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MusicFacets:
    """The filter options, with live counts, plus starter searches.

    The counts are of what this user can see. A mood with nothing behind it is
    returned at zero rather than omitted, so the filter row is a stable shape
    that does not reflow as the catalogue fills in.
    """
    data = music_service.facets(db, user_id=user.id)
    return MusicFacets(
        moods=[FacetOption(**entry) for entry in data["moods"]],
        genres=[FacetOption(**entry) for entry in data["genres"]],
        durations=[FacetOption(**entry) for entry in data["durations"]],
        total=data["total"],
        uploads=data["uploads"],
        catalogue=data["catalogue"],
        suggestions=music_service.suggested_queries(),
    )


@router.get("/{track_id}", response_model=TrackRead)
def get_track(
    track_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TrackRead:
    try:
        track = music_service.get_track(db, user_id=user.id, track_id=track_id)
    except music_service.MusicError as exc:
        raise _http(exc) from exc
    return _read(db, track)


# ---------------------------------------------------------------------------
# Uploading
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=TrackRead, status_code=201)
async def upload_track(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    artist: str | None = Form(default=None),
    mood: str | None = Form(default=None),
    genre: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    attribution: str | None = Form(default=None),
    confirmed_rights: bool = Form(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TrackRead:
    """Add your own music to the library.

    `confirmed_rights` must be true. It is the user stating they hold or have
    been granted the right to use this audio — without it there is nothing
    separating an upload from a copyrighted track somebody found, and this
    library's premise is that it never holds one of those. The claim, and any
    source they name, are recorded on the row.

    Refused before the file is read when the box is unticked, so an
    unauthorised upload never reaches storage at all.
    """
    if not confirmed_rights:
        raise HTTPException(
            status_code=422,
            detail=(
                "Confirm you have the right to use this track before uploading it."
            ),
        )

    data = await file.read()

    try:
        track = music_service.upload_track(
            db,
            user_id=user.id,
            data=data,
            content_type=file.content_type or "",
            filename=file.filename,
            title=title,
            artist=artist,
            mood=mood,
            genre=genre,
            source_url=source_url,
            attribution=attribution,
            confirmed_rights=confirmed_rights,
        )
    except (music_service.MusicError, asset_service.AssetError, UsageLimitExceeded) as exc:
        raise _http(exc) from exc

    return _read(db, track)


@router.delete("/{track_id}", status_code=204)
def delete_track(
    track_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Delete one of your uploaded tracks, and its audio.

    Catalogue tracks are refused: they are shared, so one account deleting one
    would take it out of everybody's library.
    """
    try:
        track = music_service.get_track(db, user_id=user.id, track_id=track_id)
        music_service.delete_track(db, user_id=user.id, track=track)
    except music_service.MusicError as exc:
        raise _http(exc) from exc
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Using a track
# ---------------------------------------------------------------------------


@router.post("/{track_id}/add", response_model=AudioLayerRead, status_code=201)
async def add_to_project(
    track_id: int,
    body: TrackAdd,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AudioLayerRead:
    """Add a track to a project as a music layer.

    The licence, the credit line and the source are written onto the layer so
    the obligation stays with the project even if the catalogue row changes
    later.

    A catalogue track is fetched into our own storage first. It has to be: the
    renderer only reads inputs from object storage, so a layer that pointed at
    somebody else's URL was attached, credited, and silent in the export. Doing
    it here rather than at render time means the failure — a dead link, a
    removed track — surfaces while the user is still choosing.

    Refused with 403 if the licence does not permit commercial use.
    """
    try:
        track = music_service.get_track(db, user_id=user.id, track_id=track_id)
        project = project_service.get_project(
            db, user_id=user.id, project_id=body.project_id
        )
    except music_service.MusicError as exc:
        raise _http(exc) from exc
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        # Before the licence check writes anything: a track we cannot fetch is
        # not one we should be recording a credit for.
        track = await music_service.ensure_stored(db, track=track, user_id=user.id)
        layer = music_service.add_to_project(
            db,
            user_id=user.id,
            track=track,
            project=project,
            volume=body.volume,
            ducking=body.ducking,
            loop=body.loop,
            fade_in=body.fade_in,
            fade_out=body.fade_out,
        )
    except music_service.MusicError as exc:
        raise _http(exc) from exc

    return AudioLayerRead.model_validate(layer)


@router.get("/credits/{project_id}", response_model=ProjectCredits)
def project_credits(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectCredits:
    """The credit lines this project's music obliges it to show.

    Read from the project's audio layers, not from the catalogue, so the
    obligation survives a track being withdrawn. Only licences that actually
    require attribution produce a line — listing CC0 tracks too would bury the
    ones that matter.
    """
    project = None
    try:
        project = project_service.get_project(
            db, user_id=user.id, project_id=project_id
        )
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ProjectCredits(
        project_id=project.id,
        credits=music_service.project_credits(db, project.id),
    )
