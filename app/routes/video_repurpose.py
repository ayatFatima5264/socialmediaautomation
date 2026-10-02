"""Smart Repurpose endpoints.

    GET  /api/video/repurpose/targets    the platforms this cuts for
    POST /api/video/repurpose/analyze    a long video -> candidate moments
    POST /api/video/repurpose/shorts     reviewed moments -> new projects

**Three steps, and the middle one is a human.** Analyse changes nothing but a
cached transcript; creating projects is a separate call the user makes after
editing the moments; exporting is them pressing Export in the editor. Nothing
here renders and nothing here publishes.

**The source is read, never written.** `analyze` stores its transcript on the
source asset's `meta` so a second visit does not pay for transcription again —
that is the only write it makes, and it adds a key rather than changing
anything the asset already had. The source *project*, if one was named, is
never touched at all: it is recorded on each short as provenance and otherwise
only read for its name.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.api_errors import provider_http_error
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.video_repurpose import (
    AnalyzeRequest,
    AnalyzeResult,
    CreateShortsRequest,
    CreateShortsResult,
    Moment,
    RepurposeOptions,
    RepurposeTarget,
    ShortRead,
)
from app.services.video import assets as asset_service
from app.services.video import projects as project_service
from app.services.video import repurpose as service
from app.services.video import timeline as tl
from app.services.video import transcription as transcription_service
from app.services.video.metering import UsageLimitExceeded
from app.services.video.providers import (
    MediaProviderConfigError,
    get_transcription_provider,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video/repurpose", tags=["repurpose"])


def _http(exc: Exception) -> HTTPException:
    """Map a service error onto a status code.

    A provider fault is handed to `app.api_errors`, the single place that
    decides status and message, so an outage answers the same here as it does
    in every other route. The rest are service-level refusals about the request
    and keep their own codes.
    """
    if isinstance(exc, asset_service.AssetNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    return provider_http_error(exc) or HTTPException(status_code=422, detail=str(exc))


@router.get("/targets", response_model=RepurposeOptions)
def targets(user: User = Depends(get_current_user)) -> RepurposeOptions:
    # Whether the *configured* provider can actually run, not which ones exist.
    # Building it is the probe: the constructor raises when its key is missing,
    # which is exactly the condition the banner is there to report.
    try:
        available = get_transcription_provider() is not None
    except MediaProviderConfigError:
        available = False
    except Exception:  # noqa: BLE001 — a provider probe must not fail the page
        logger.warning("Transcription provider probe failed", exc_info=True)
        available = False

    return RepurposeOptions(
        targets=[RepurposeTarget(**entry) for entry in service.targets()],
        min_clip_seconds=service.MIN_CLIP_SECONDS,
        max_clip_seconds=service.MAX_CLIP_SECONDS,
        default_moment_count=service.DEFAULT_MOMENT_COUNT,
        transcription_available=available,
    )


@router.post("/analyze", response_model=AnalyzeResult)
async def analyze(
    body: AnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AnalyzeResult:
    """Transcribe a long video and propose the sections worth cutting.

    **Cached on the asset.** Transcription costs money and the words do not
    change, so a second visit reuses the stored transcript and only re-runs the
    moment detection. `force` re-transcribes.

    Creates nothing. The result is a list the user edits before any project
    exists.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=body.asset_id)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    if not asset.content_type.startswith(("video/", "audio/")):
        raise HTTPException(
            status_code=422,
            detail="Repurpose needs a video or an audio recording to work from.",
        )

    cached = (asset.meta or {}).get("repurpose") or {}
    segments = cached.get("segments") if not body.force else None
    language = cached.get("language", "")
    duration = float(asset.duration_seconds or cached.get("duration") or 0.0)

    if not segments:
        try:
            data, content_type = asset_service.read_asset(asset)
        except asset_service.AssetError as exc:
            raise _http(exc) from exc

        try:
            result = await transcription_service.transcribe(
                db,
                user_id=user.id,
                data=data,
                filename=asset.filename or "source.mp4",
                content_type=content_type,
                language=body.language,
                # The file is already an asset — storing it again would be a
                # second copy of a video we are specifically not copying.
                store_source=False,
            )
        except transcription_service.TranscriptionError as exc:
            raise _http(exc) from exc
        except (MediaProviderConfigError, UsageLimitExceeded) as exc:
            raise _http(exc) from exc

        # `transcribe` returns cues; they carry the same start/end/text a
        # segment does, which is all the moment finder reads.
        segments = [
            {"start": cue["start"], "end": cue["end"], "text": cue["text"]}
            for cue in (result.get("cues") or [])
        ]
        language = result.get("language") or ""
        duration = duration or float(result.get("duration_seconds") or 0.0)

        asset.meta = {
            **(asset.meta or {}),
            "repurpose": {
                "segments": segments,
                "language": language,
                "duration": duration,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        # The JSON column is mutated in place; without this SQLAlchemy does not
        # see the change and the cache is never written.
        flag_modified(asset, "meta")
        db.commit()

    if not segments:
        raise HTTPException(
            status_code=422,
            detail="Nothing could be transcribed from that file, so there is "
            "nothing to cut.",
        )

    duration = duration or max(float(row.get("end") or 0) for row in segments)

    try:
        moments = await service.find_moments(
            segments=segments, duration=duration, count=body.count
        )
    except service.RepurposeError as exc:
        raise _http(exc) from exc

    stored = (asset.meta or {}).get("repurpose") or {}

    return AnalyzeResult(
        asset_id=asset.id,
        duration_seconds=round(duration, 2),
        language=language,
        moments=[Moment(**moment) for moment in moments],
        overlaps=[list(pair) for pair in service.overlaps(moments)],
        segment_count=len(segments),
        analyzed_at=stored.get("analyzed_at"),
        cached=bool(cached.get("segments")) and not body.force,
    )


@router.post("/shorts", response_model=CreateShortsResult, status_code=201)
def create_shorts(
    body: CreateShortsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CreateShortsResult:
    """Turn reviewed moments into new projects — one per moment per platform.

    Every short is an ordinary project: it opens in the Video Editor, every
    clip on it can be moved and trimmed, and it exports through the same
    renderer as anything else. Nothing is rendered here and nothing is
    published.

    The source project is untouched. A moment that will not fit its target is
    skipped with a reason rather than silently truncated, because a clip cut to
    sixty seconds mid-sentence is not what the user reviewed.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=body.asset_id)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    unknown = [key for key in body.targets if key not in service.TARGETS_BY_KEY]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown platform: {', '.join(unknown)}."
        )

    source_project = None
    if body.source_project_id is not None:
        try:
            source_project = project_service.get_project(
                db, user_id=user.id, project_id=body.source_project_id
            )
        except project_service.ProjectError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    segments = ((asset.meta or {}).get("repurpose") or {}).get("segments") or []

    shorts: list[ShortRead] = []
    skipped: list[dict] = []

    for moment in body.moments:
        payload = moment.model_dump()
        for target in body.targets:
            try:
                project = service.create_short(
                    db,
                    user_id=user.id,
                    moment=payload,
                    target=target,
                    source_asset=asset,
                    segments=segments,
                    source_project=source_project,
                )
            except (service.RepurposeError, project_service.ProjectError) as exc:
                skipped.append(
                    {
                        "title": payload.get("title") or "Clip",
                        "target": target,
                        "reason": str(exc),
                    }
                )
                db.rollback()
                continue

            shorts.append(
                ShortRead(
                    project_id=project.id,
                    name=project.name,
                    platform=project.platform,
                    aspect_ratio=project.aspect_ratio,
                    width=project.width,
                    height=project.height,
                    duration_seconds=tl.duration(tl.normalize(project.timeline)),
                    target=target,
                    moment=payload,
                    editor_path=f"/video/projects/{project.id}/edit",
                )
            )

    if not shorts and skipped:
        raise HTTPException(
            status_code=422,
            detail=skipped[0]["reason"],
        )

    return CreateShortsResult(shorts=shorts, skipped=skipped)
