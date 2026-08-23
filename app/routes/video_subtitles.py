"""Subtitle Studio endpoints.

Subtitle Studio is required to work with no project, and the routes make that
structural: nothing here takes a project id except `attach`, which is the
explicit "Add to Project" action. Cues belong to whoever made them; connecting
them to a project is a separate decision.

    GET  /api/video/subtitles/styles          presets + the style vocabularies
    GET  /api/video/subtitles/formats         what export can write
    POST /api/video/subtitles/transcribe      upload video or audio -> cues
    POST /api/video/subtitles/from-script     a written script -> timed cues
    POST /api/video/subtitles/import          an existing .srt/.vtt -> cues
    POST /api/video/subtitles/edit/*          update, insert, delete, split,
                                              merge, shift, search-replace
    POST /api/video/subtitles/normalize       re-split to the reading limits
    POST /api/video/subtitles/export          -> a file in object storage
    GET  /api/video/subtitles/files           this user's exported files
    GET  /api/video/subtitles/files/{id}/download?format=srt|vtt|txt
    POST /api/video/subtitles/attach          -> a track on a project
    GET  /api/video/subtitles/tracks?project_id=

**Every edit takes the whole track and returns the whole track.** Deliberately
not a per-cue patch API: a split or a merge renumbers everything after it, so
an endpoint addressing "cue 14" would be describing a track the client no
longer has. A subtitle track is a few hundred cues; sending it is cheap, and
the alternative is a class of index-drift bug that only appears under fast
editing.

The edits themselves are pure functions in `app/services/video/subtitles.py`.
They live there rather than in the frontend so a future generator and any
repair of an imported file get the same behaviour, and so "what does splitting
a cue do to its timing" has exactly one answer.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.models.video_subtitle import SUBTITLE_SOURCES, VideoSubtitle
from app.schemas.video_subtitles import (
    AttachRequest,
    CueDelete,
    CueInsert,
    CueMerge,
    CueShift,
    CueSplit,
    CueUpdate,
    EditResult,
    ExportFormat,
    ExportRequest,
    NormalizeRequest,
    ScriptRequest,
    ScriptResult,
    SearchReplace,
    StyleOptions,
    SubtitleFile,
    SubtitleTrack,
    TranscribeResult,
)
from app.services.storage.base import StorageError
from app.services.video import assets as asset_service
from app.services.video import projects as project_service
from app.services.video import subtitles as engine
from app.services.video import transcription as transcription_service
from app.services.video.metering import UsageLimitExceeded
from app.services.video.providers import MediaProviderConfigError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video/subtitles", tags=["subtitle-studio"])


def _http(exc: Exception) -> HTTPException:
    """Map a service error onto a status code.

    The distinctions that matter to the user: a provider that is not configured
    is 503 (their admin has to fix it), a quota is 429 (come back later), and
    anything about the file or the edit is 422 (change something and retry).
    """
    if isinstance(exc, UsageLimitExceeded):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, MediaProviderConfigError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, asset_service.AssetNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, StorageError):
        return HTTPException(
            status_code=502,
            detail="The file store could not be reached. Try again in a moment.",
        )
    return HTTPException(status_code=422, detail=str(exc))


def _cues(payload) -> list[dict]:
    """The request's cue list as plain dicts, which is what the engine takes."""
    return [cue.model_dump() for cue in payload.cues]


def _result(cues: list[dict], replacements: int | None = None) -> EditResult:
    return EditResult(
        cues=cues,
        duration_seconds=engine.total_duration(cues),
        cue_count=len(cues),
        replacements=replacements,
    )


def _edit(operation) -> EditResult:
    """Run an engine operation, turning its refusal into a 422 with a reason."""
    try:
        return _result(operation())
    except engine.SubtitleEditError as exc:
        raise _http(exc) from exc


def _file(asset: VideoAsset) -> SubtitleFile:
    meta = asset.meta or {}
    return SubtitleFile(
        id=asset.id,
        project_id=asset.project_id,
        title=asset.title,
        filename=asset.filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        url=f"{settings.backend_url}/api/storage/o/{asset.token}",
        created_at=asset.created_at,
        format=meta.get("format") or "srt",
        cue_count=int(meta.get("cue_count") or 0),
        duration_seconds=float(meta.get("duration_seconds") or 0.0),
        language=meta.get("language"),
    )


def _track(track: VideoSubtitle) -> SubtitleTrack:
    return SubtitleTrack(
        id=track.id,
        project_id=track.project_id,
        language=track.language,
        label=track.label,
        source=track.source,
        is_primary=track.is_primary,
        cue_count=track.cue_count,
        duration_seconds=track.duration_seconds,
        style=track.style or {},
        cues=track.cues or [],
        created_at=track.created_at,
        updated_at=track.updated_at,
    )


# ---------------------------------------------------------------------------
# Styles and formats
# ---------------------------------------------------------------------------


@router.get("/styles", response_model=StyleOptions)
def styles(user: User = Depends(get_current_user)) -> StyleOptions:
    """The presets and the vocabularies the style panel builds its controls from.

    Served rather than hardcoded in the frontend because the renderer has to
    understand every value the editor can produce.
    """
    return StyleOptions(
        presets=[engine.preset(key) for key in engine.SUBTITLE_PRESETS],
        default_preset=engine.DEFAULT_PRESET,
        **engine.style_vocabularies(),
    )


@router.get("/formats", response_model=list[ExportFormat])
def formats(user: User = Depends(get_current_user)) -> list[ExportFormat]:
    return [
        ExportFormat(
            key=key,
            label=spec["label"],
            extension=spec["extension"],
            content_type=spec["content_type"],
        )
        for key, spec in transcription_service.EXPORT_FORMATS.items()
    ]


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


@router.post("/transcribe", response_model=TranscribeResult)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    translate_to_english: bool = Form(default=False),
    provider: str | None = Form(default=None),
    style_key: str | None = Form(default=None),
    store_source: bool = Form(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TranscribeResult:
    """Upload a video or an audio file and get timed cues back.

    No project is involved. The uploaded media is kept as an asset by default
    so the cue editor can play it back while the timing is checked — subtitles
    edited without hearing them are subtitles edited blind.
    """
    raw = await file.read()

    try:
        result = await transcription_service.transcribe(
            db,
            user_id=user.id,
            data=raw,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            language=language or None,
            translate_to_english=translate_to_english,
            provider_name=provider or None,
            style=engine.preset(style_key) if style_key else None,
            store_source=store_source,
        )
    except (
        transcription_service.TranscriptionError,
        UsageLimitExceeded,
        MediaProviderConfigError,
    ) as exc:
        raise _http(exc) from exc

    return TranscribeResult(**result)


@router.post("/from-script", response_model=ScriptResult)
def from_script(
    body: ScriptRequest, user: User = Depends(get_current_user)
) -> ScriptResult:
    """Time a written script into cues, with no audio and no transcription.

    The timing is an *estimate* when no duration is given — there is no
    recording to measure against — and `estimated` says so, because presenting
    a guess as a measurement is the one thing this path must not do.
    """
    cues = engine.cues_from_script(
        body.text,
        duration_seconds=body.duration_seconds,
        wpm=body.words_per_minute,
        style=engine.preset(body.style_key) if body.style_key else None,
    )
    if not cues:
        raise HTTPException(
            status_code=422, detail="There is no text to turn into subtitles."
        )

    return ScriptResult(
        cues=cues,
        duration_seconds=engine.total_duration(cues),
        estimated=not body.duration_seconds,
    )


@router.post("/import", response_model=EditResult)
async def import_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EditResult:
    """Open an existing .srt or .vtt for editing.

    Parsing is deliberately tolerant — a subtitle file that came from another
    tool is exactly the file most likely to be slightly malformed, and refusing
    it is not a service to anyone.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="That file is empty.")
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail="That subtitle file is unusually large."
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Subtitle files from older tools are routinely Latin-1.
        text = raw.decode("latin-1", errors="replace")

    cues = engine.parse(text)
    if not cues:
        raise HTTPException(
            status_code=422,
            detail=(
                "No subtitles could be read from that file. It should be an "
                "SRT or WebVTT file."
            ),
        )
    return _result(cues)


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


@router.post("/normalize", response_model=EditResult)
def normalize(body: NormalizeRequest, user: User = Depends(get_current_user)) -> EditResult:
    """Sort, de-overlap and clean a track. Safe to run on any edit."""
    return _result(engine.normalize(_cues(body)))


@router.post("/edit/update", response_model=EditResult)
def edit_update(body: CueUpdate, user: User = Depends(get_current_user)) -> EditResult:
    return _edit(
        lambda: engine.update_cue(
            _cues(body), body.index, start=body.start, end=body.end, text=body.text
        )
    )


@router.post("/edit/insert", response_model=EditResult)
def edit_insert(body: CueInsert, user: User = Depends(get_current_user)) -> EditResult:
    return _edit(
        lambda: engine.insert_cue(
            _cues(body),
            index=body.index,
            text=body.text,
            start=body.start,
            end=body.end,
        )
    )


@router.post("/edit/delete", response_model=EditResult)
def edit_delete(body: CueDelete, user: User = Depends(get_current_user)) -> EditResult:
    return _edit(lambda: engine.delete_cue(_cues(body), body.index))


@router.post("/edit/split", response_model=EditResult)
def edit_split(body: CueSplit, user: User = Depends(get_current_user)) -> EditResult:
    return _edit(
        lambda: engine.split_cue(
            _cues(body),
            body.index,
            at_seconds=body.at_seconds,
            at_character=body.at_character,
        )
    )


@router.post("/edit/merge", response_model=EditResult)
def edit_merge(body: CueMerge, user: User = Depends(get_current_user)) -> EditResult:
    return _edit(lambda: engine.merge_cues(_cues(body), body.indices))


@router.post("/edit/shift", response_model=EditResult)
def edit_shift(body: CueShift, user: User = Depends(get_current_user)) -> EditResult:
    """Move the whole track — for audio that starts late, or a trimmed intro."""
    return _edit(lambda: engine.shift(_cues(body), body.offset_seconds))


@router.post("/edit/search-replace", response_model=EditResult)
def edit_search_replace(
    body: SearchReplace, user: User = Depends(get_current_user)
) -> EditResult:
    try:
        cues, count = engine.search_replace(
            _cues(body),
            find=body.find,
            replace=body.replace,
            case_sensitive=body.case_sensitive,
            whole_word=body.whole_word,
        )
    except engine.SubtitleEditError as exc:
        raise _http(exc) from exc
    return _result(cues, replacements=count)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.post("/export", response_model=SubtitleFile, status_code=201)
def export(
    body: ExportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubtitleFile:
    """Write the track to object storage as an SRT, VTT or TXT file.

    Stored rather than streamed so it appears in the user's library and can be
    attached to a project later. A subtitle file is small, but "small files may
    go in the database" is exactly the exception that grows until the rule is
    meaningless — this goes through the same storage layer as a rendered video.
    """
    project_id = None
    if body.project_id is not None:
        try:
            project = project_service.get_project(
                db, user_id=user.id, project_id=body.project_id
            )
        except project_service.ProjectError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        project_id = project.id

    try:
        asset = transcription_service.export_asset(
            db,
            user_id=user.id,
            cues=_cues(body),
            fmt=body.format,
            title=body.title,
            language=body.language,
            project_id=project_id,
        )
    except (transcription_service.TranscriptionError, asset_service.AssetError) as exc:
        raise _http(exc) from exc

    return _file(asset)


@router.get("/files", response_model=list[SubtitleFile])
def files(
    project_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SubtitleFile]:
    rows = asset_service.user_assets(
        db, user_id=user.id, kind="subtitle", project_id=project_id, limit=limit
    )
    return [_file(row) for row in rows]


@router.get("/files/{asset_id}/download")
def download(
    asset_id: int,
    format: str = Query(default="srt", pattern="^(srt|vtt|txt)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Download a stored subtitle file, converting between formats on demand.

    An exported SRT can be downloaded as VTT without a second export, because
    the cues travel on the asset's metadata — so the three formats are three
    views of one track rather than three files to keep in step.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    meta = asset.meta or {}
    cues = meta.get("cues")

    if not cues:
        # An older export, or one whose cues were not kept: re-read the stored
        # file. Reparsing is exact for SRT and VTT; a .txt has no timings, so
        # that one can only be handed back as it is.
        try:
            data, _ = asset_service.read_asset(asset)
        except asset_service.AssetError as exc:
            raise _http(exc) from exc
        cues = engine.parse(data.decode("utf-8", "replace"))

    if not cues:
        raise HTTPException(
            status_code=422,
            detail=(
                "This file has no timed cues, so it can only be downloaded in "
                "the format it was exported as."
            ),
        )

    try:
        text, content_type, extension = transcription_service.render(cues, format)
    except transcription_service.TranscriptionError as exc:
        raise _http(exc) from exc

    stem = (asset.title or "subtitles").rsplit(".", 1)[0][:60] or "subtitles"
    body = text.encode("utf-8")

    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{stem}.{extension}"',
            "Content-Length": str(len(body)),
            # Per-user and freshly rendered — nothing in front of the API
            # should be caching it.
            "Cache-Control": "private, max-age=0, no-store",
        },
    )


@router.delete("/files/{asset_id}", status_code=204)
def delete_file(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc
    asset_service.delete_asset(db, asset)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Tracks on a project
# ---------------------------------------------------------------------------


@router.post("/attach", response_model=SubtitleTrack)
def attach(
    body: AttachRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubtitleTrack:
    """Add the track to a project — the "Add to Project" action.

    The project is looked up scoped to the signed-in user, so this cannot write
    subtitles into somebody else's video.

    `track_id` replaces a track the studio previously created rather than
    adding a second one; editing and re-attaching is the normal loop, and
    without it a project accumulates a copy per save.
    """
    try:
        project = project_service.get_project(
            db, user_id=user.id, project_id=body.project_id
        )
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    cues = engine.normalize(_cues(body))
    if not cues:
        raise HTTPException(status_code=422, detail="There are no subtitles to add.")

    source = body.source if body.source in SUBTITLE_SOURCES else "manual"

    track: VideoSubtitle | None = None
    if body.track_id is not None:
        track = db.scalars(
            select(VideoSubtitle).where(
                VideoSubtitle.id == body.track_id,
                VideoSubtitle.project_id == project.id,
            )
        ).first()
        if track is None:
            raise HTTPException(status_code=404, detail="That subtitle track does not exist.")

    if track is None:
        # A project is created with one empty track. Filling that in is what
        # the user means by "add subtitles", so reuse it rather than leaving an
        # empty track next to a full one.
        #
        # Matched on *emptiness first*, not on language. `create_project` seeds
        # that track as "en-US", so attaching a track labelled "en" — which is
        # what a transcription provider reports — matched nothing, created a
        # second track, and left the empty one holding the `is_primary` flag.
        # An empty track has no language commitment; whatever is attached
        # decides what it is.
        candidates = list(
            db.scalars(
                select(VideoSubtitle)
                .where(VideoSubtitle.project_id == project.id)
                .order_by(VideoSubtitle.id)
            ).all()
        )

        # Prefer a track already in this language — re-attaching a language
        # should replace it rather than add a second copy of it.
        track = next(
            (row for row in candidates if row.language == body.language), None
        )
        if track is None:
            track = next((row for row in candidates if not row.cue_count), None)
        elif track.cue_count and any(not row.cue_count for row in candidates):
            # This language is already filled in, but there is still an unused
            # track — use that instead of stranding it.
            track = next(row for row in candidates if not row.cue_count)

    if track is None:
        track = VideoSubtitle(project_id=project.id, is_primary=False)
        db.add(track)

    track.language = body.language
    track.label = body.label
    track.source = source
    track.cues = cues
    track.style = engine.clean_style(body.style)
    track.cue_count = len(cues)
    track.duration_seconds = engine.total_duration(cues)

    # Exactly one primary per project — it is the track that gets burned in.
    others = db.scalars(
        select(VideoSubtitle).where(VideoSubtitle.project_id == project.id)
    ).all()
    if not any(other.is_primary and other is not track for other in others):
        track.is_primary = True

    db.commit()
    db.refresh(track)

    # The project's duration may now be longer than its timeline — captions can
    # exist before any media does.
    project.duration_seconds = project_service.project_duration(db, project)
    db.commit()

    return _track(track)


@router.get("/tracks", response_model=list[SubtitleTrack])
def tracks(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SubtitleTrack]:
    try:
        project = project_service.get_project(
            db, user_id=user.id, project_id=project_id
        )
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    rows = db.scalars(
        select(VideoSubtitle)
        .where(VideoSubtitle.project_id == project.id)
        .order_by(VideoSubtitle.is_primary.desc(), VideoSubtitle.id)
    ).all()
    return [_track(row) for row in rows]
