"""Voice Studio endpoints.

Voice Studio is required to work with no project, and the routes are shaped to
make that structural rather than a promise: nothing here takes a project id
except `attach`, which is the explicit "Add to Project" action. A voice-over
belongs to the **user**; connecting it to a project is a separate decision, and
the same take can be attached to several projects over its life.

    GET  /api/video/voice/catalogue   voices, languages, styles, providers
    POST /api/video/voice/preview     synthesize a short sample, store nothing
    POST /api/video/voice/generate    synthesize, store, meter -> an asset
    GET  /api/video/voice/takes       this user's voice-overs, newest first
    POST /api/video/voice/segments    split a script into regenerable blocks
    POST /api/video/voice/{id}/attach add a take to a project
    GET  /api/video/voice/{id}/download?format=mp3|wav

**Preview does not touch storage.** It returns the audio inline, base64 in the
JSON. A preview the user rejects must not leave a file in their library or
bytes in a bucket they pay for, and a bucket write plus a signed URL for two
seconds of audio is slower than just sending it.

**Generate always stores.** A take the user waited for is theirs; it goes to
object storage (never Postgres — see app/services/storage) and appears in their
library whether or not they ever attach it to a project.
"""
from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api_errors import provider_http_error
from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.schemas.video_voice import (
    VoiceCatalogue,
    VoiceGenerateRequest,
    VoicePreviewRequest,
    VoicePreviewResult,
    VoiceSegmentRequest,
    VoiceSegmentsResult,
    VoiceTake,
)
from app.services.storage.base import StorageError
from app.services.video import assets as asset_service
from app.services.video import projects as project_service
from app.services.video import voice as voice_service
from app.services.video.ffmpeg import AUDIO_FORMATS, FFmpegError, transcode_audio
from app.services.video.metering import UsageLimitExceeded
from app.services.video.providers import (
    MediaProviderConfigError,
    available_tts_providers,
    get_tts_providers,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video/voice", tags=["voice-studio"])

# How much text a preview will speak. A preview exists to answer "is this the
# right voice", which the first couple of sentences settle — and synthesizing
# 5,000 characters the user is about to change is a waste of their time and of
# somebody's compute.
PREVIEW_CHARACTERS = 240


def _http(exc: Exception) -> HTTPException:
    """Map a service error onto a status code.

    The distinction that matters: a provider that is not configured is 503
    (the operator has to fix it), a request the user can correct is 422, and a
    quota is 429. Collapsing those into 500 is what makes a studio unusable —
    the user cannot tell "try shorter text" from "come back later".
    """
    if isinstance(exc, asset_service.AssetNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, StorageError):
        return HTTPException(
            status_code=502,
            detail="The file store could not be reached. Try again in a moment.",
        )
    # Provider faults — 503 unconfigured, 429 quota, 502 failed — are decided in
    # one place so they read the same here as in every other route.
    return provider_http_error(exc) or HTTPException(status_code=422, detail=str(exc))


def _take(asset: VideoAsset) -> VoiceTake:
    """One voice-over, shaped for the studio.

    The settings that produced it travel with it, so "Regenerate" can start
    from what made this take rather than from whatever the panel happens to
    show now.
    """
    meta = asset.meta or {}
    return VoiceTake(
        id=asset.id,
        project_id=asset.project_id,
        title=asset.title,
        filename=asset.filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        duration_seconds=asset.duration_seconds or 0.0,
        url=f"{settings.backend_url}/api/storage/o/{asset.token}",
        created_at=asset.created_at,
        text=meta.get("text") or "",
        voice_id=meta.get("voice_id") or "",
        provider=meta.get("provider") or "",
        style=meta.get("style") or voice_service.DEFAULT_STYLE,
        rate=float(meta.get("rate") or 1.0),
        pitch=float(meta.get("pitch") or 1.0),
        volume=float(meta.get("volume") or 1.0),
        segment_index=meta.get("segment_index"),
        word_marks=meta.get("word_marks") or [],
    )


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


@router.get("/catalogue", response_model=VoiceCatalogue)
async def catalogue(user: User = Depends(get_current_user)) -> VoiceCatalogue:
    """Everything the panel needs to render its controls.

    One request rather than four, because the language list is derived from the
    voices and the two must never disagree — a language with no voices behind
    it is a dead end in a dropdown.

    A provider whose key is missing drops out silently instead of failing the
    whole call, so a deployment with only edge-tts configured still gets a full
    catalogue. `providers` reports which ones actually answered, so the UI can
    say what is available rather than implying all of them are.
    """
    voices = await voice_service.list_voices()

    if not voices:
        # Not an empty dropdown with no explanation: this is a deployment
        # problem and the operator is the one who can fix it.
        raise HTTPException(
            status_code=503,
            detail=(
                "No voice provider is available. Check TTS_PROVIDER and its "
                "credentials, or configure a local server with "
                "CUSTOM_TTS_BASE_URL."
            ),
        )

    return VoiceCatalogue(
        voices=[
            {
                "id": v.id,
                "provider": v.provider,
                "label": v.label,
                "language": v.language,
                "language_label": v.language_label,
                "gender": v.gender,
                "supports_prosody": v.supports_prosody,
                "styles": list(v.styles),
            }
            for v in voices
        ],
        languages=voice_service.languages_from(voices),
        styles=voice_service.style_options(),
        providers=[p.name for p in get_tts_providers()],
        available_providers=list(available_tts_providers),
        max_characters=settings.tts_max_characters,
        preview_characters=PREVIEW_CHARACTERS,
        default_style=voice_service.DEFAULT_STYLE,
    )


@router.post("/segments", response_model=VoiceSegmentsResult)
def segments(
    body: VoiceSegmentRequest, user: User = Depends(get_current_user)
) -> VoiceSegmentsResult:
    """Split a script into the blocks that can be regenerated one at a time.

    Server-side so the studio and any future generator agree on where a
    section starts and ends — two implementations of "what is a paragraph"
    would put takes out of step with the text they came from.
    """
    found = voice_service.split_segments(body.text or "")
    return VoiceSegmentsResult(
        segments=found,
        characters=len(body.text or ""),
        max_characters=settings.tts_max_characters,
    )


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


@router.post("/preview", response_model=VoicePreviewResult)
async def preview(
    body: VoicePreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoicePreviewResult:
    """Speak a short sample. Nothing is stored.

    The audio comes back base64 in the JSON rather than as a URL: there is no
    object to point a URL at, and creating one for a sample the user is about
    to discard is exactly the litter this avoids.
    """
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=422, detail="Enter some text to preview a voice."
        )

    truncated = len(text) > PREVIEW_CHARACTERS
    sample = text[:PREVIEW_CHARACTERS]

    try:
        _, details = await voice_service.synthesize(
            db,
            user_id=user.id,
            text=sample,
            voice_id=body.voice_id,
            rate=body.rate,
            pitch=body.pitch,
            volume=body.volume,
            style=body.style,
            save=False,
        )
    except (voice_service.VoiceError, UsageLimitExceeded, MediaProviderConfigError) as exc:
        raise _http(exc) from exc

    return VoicePreviewResult(
        audio_base64=base64.b64encode(details["audio"]).decode("ascii"),
        content_type=details["content_type"],
        duration_seconds=details["duration_seconds"],
        provider=details["provider"],
        voice_id=details["voice_id"],
        style=details["style"],
        effective_rate=details["effective_rate"],
        effective_pitch=details["effective_pitch"],
        characters=details["characters"],
        truncated=truncated,
    )


@router.post("/generate", response_model=VoiceTake, status_code=201)
async def generate(
    body: VoiceGenerateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceTake:
    """Generate a voice-over, store it, and return it as a take.

    `project_id` is optional and defaults to None — a voice-over made here
    belongs to the user's library and gains a project only when they say so.

    `segment_index` records which block of a longer script this take covers, so
    regenerating one section produces a take the UI can put back in the right
    place rather than a loose file.
    """
    try:
        asset, _ = await voice_service.synthesize(
            db,
            user_id=user.id,
            text=body.text,
            voice_id=body.voice_id,
            rate=body.rate,
            pitch=body.pitch,
            volume=body.volume,
            style=body.style,
            project_id=body.project_id,
            title=body.title,
            save=True,
            extra_meta=(
                {"segment_index": body.segment_index}
                if body.segment_index is not None
                else None
            ),
        )
    except (voice_service.VoiceError, UsageLimitExceeded, MediaProviderConfigError) as exc:
        raise _http(exc) from exc
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    return _take(asset)


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


@router.get("/takes", response_model=list[VoiceTake])
def takes(
    project_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[VoiceTake]:
    """This user's voice-overs, newest first. Never anybody else's."""
    rows = asset_service.user_assets(
        db, user_id=user.id, kind="voice", project_id=project_id, limit=limit
    )
    return [_take(row) for row in rows]


@router.post("/{asset_id}/attach", response_model=VoiceTake)
def attach(
    asset_id: int,
    project_id: int = Query(..., description="The project to add this voice-over to."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VoiceTake:
    """Add a take to a project — the "Add to Project" action.

    Both the asset and the project are looked up scoped to the signed-in user,
    so this cannot move somebody else's audio into your project or yours into
    theirs.

    Deliberately does NOT place the audio on the timeline. Adding a voice-over
    makes it available in the project; where it sits is an editing decision.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
        project = project_service.get_project(
            db, user_id=user.id, project_id=project_id
        )
    except (asset_service.AssetError, project_service.ProjectError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    project_service.attach_asset(db, project=project, asset=asset)
    return _take(asset)


@router.delete("/{asset_id}", status_code=204)
def delete_take(
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


@router.get("/{asset_id}/download")
def download(
    asset_id: int,
    format: str = Query(default="mp3", pattern="^(mp3|wav)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Download a take as MP3 or WAV.

    A provider gives us exactly one format — edge-tts returns MP3, Groq returns
    WAV — so one of these two always needs converting. That happens here, with
    ffmpeg, on demand: storing both copies of every take would double the
    storage bill for a file most people download once, and offering only the
    format the provider happened to produce would be the studio deciding what
    the user is allowed to have.

    Requires a session, unlike the public asset route: this is a download for
    the person who made it, not a URL a social platform fetches.
    """
    try:
        asset = asset_service.get_asset(db, user_id=user.id, asset_id=asset_id)
        data, content_type = asset_service.read_asset(asset)
    except asset_service.AssetError as exc:
        raise _http(exc) from exc

    spec = AUDIO_FORMATS[format]
    source_suffix = (asset.filename or "").rsplit(".", 1)[-1] or (
        "wav" if "wav" in content_type else "mp3"
    )

    try:
        converted = transcode_audio(data, source_suffix=source_suffix, target=format)
    except FFmpegError as exc:
        logger.exception("Could not convert take %s to %s", asset.id, format)
        raise HTTPException(
            status_code=502,
            detail=(
                f"Could not convert this voice-over to {format.upper()}. "
                f"The original is still available to download."
            ),
        ) from exc

    # A filename built from the title, not from the token — the user is saving
    # this to a folder and "voiceover-Xk3p9.mp3" is not a name they can find.
    stem = "".join(
        char if char.isalnum() or char in " -_" else "" for char in (asset.title or "voiceover")
    ).strip() or "voiceover"
    filename = f"{stem[:60]}.{spec['extension']}"

    return Response(
        content=converted,
        media_type=spec["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(converted)),
            # A take is immutable, but this response is per-user — it must not
            # be cached by anything in front of the API.
            "Cache-Control": "private, max-age=0, no-store",
        },
    )
