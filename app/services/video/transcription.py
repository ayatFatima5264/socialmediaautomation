"""Subtitle Studio's service layer — media in, timed cues out.

Subtitle Studio is required to work with no project, so nothing here takes one.
It takes a user and a file (or a script) and returns cues; connecting those to a
project is a separate, explicit action.

Three things live here rather than in a provider or a route:

  * **Getting to something transcribable.** A 200 MB screen recording cannot be
    posted to a speech API that caps uploads at 24 MB, and 199 MB of that file
    is pixels the model never looks at. The audio is extracted and downmixed
    first, which routinely takes two orders of magnitude off — the difference
    between a video being transcribable and not.
  * **Turning a transcript into subtitles.** They are not the same thing. A
    speech model returns whatever length of segment it felt like; the reading
    limits that make those into cues are applied in `subtitles.py`, and this
    module is what connects the two.
  * **Metering and storage.** Every transcription records the seconds it
    consumed, and the uploaded media is stored so the editor can play it back
    while the timing is being checked — which is the difference between editing
    subtitles and guessing at them.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.video_asset import VideoAsset
from app.services.video import assets as asset_service
from app.services.video import metering
from app.services.video import subtitles as subtitle_engine
from app.services.video.ffmpeg import FFmpegError, extract_audio, probe_bytes
from app.services.video.providers import (
    MediaProviderConfigError,
    MediaProviderError,
    Transcript,
    get_transcription_provider,
)

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """A transcription was refused or failed. The message is user-facing."""


# What can be dropped on the Subtitle Studio. Wider than the publishing
# whitelist because this is a working file, not something a platform fetches —
# but still a closed list, so this cannot become a general-purpose file host.
ACCEPTED_MEDIA = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
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
}

# The kind a stored upload is filed under, so the media library groups it with
# like things rather than lumping every transcription source together.
def _asset_kind(content_type: str) -> str:
    return "video" if content_type.startswith("video/") else "upload"


def transcription_limit_bytes() -> int:
    return settings.transcription_max_upload_mb * 1024 * 1024


def prepare_audio(data: bytes, *, content_type: str, filename: str) -> tuple[bytes, str, str]:
    """Reduce a file to something the speech API will accept.

    Returns `(audio_bytes, content_type, filename)`.

    Video always goes through ffmpeg — there is no reason to upload pixels to a
    speech model. Audio is passed through untouched when it is already small
    enough, and downmixed to 16 kHz mono when it is not: that is the sample
    rate Whisper resamples to anyway, so the conversion loses nothing the model
    would have used.

    Raises TranscriptionError when the file still will not fit, which is a
    refusal the user can act on ("trim it") rather than a 413 from a vendor.
    """
    limit = transcription_limit_bytes()
    is_video = content_type.startswith("video/")

    if not is_video and len(data) <= limit:
        return data, content_type, filename

    suffix = Path(filename).suffix or (".mp4" if is_video else ".bin")
    source_fd, source_path = tempfile.mkstemp(suffix=suffix, prefix="autosocial_stt_src_")
    os.close(source_fd)
    target_path = Path(source_path).with_suffix(".stt.mp3")

    try:
        Path(source_path).write_bytes(data)
        try:
            extract_audio(source_path, target_path)
        except FFmpegError as exc:
            raise TranscriptionError(str(exc)) from exc

        reduced = target_path.read_bytes()
        if len(reduced) > limit:
            raise TranscriptionError(
                f"Even as compressed audio this file is "
                f"{len(reduced) / (1024 * 1024):.0f} MB, above the "
                f"{settings.transcription_max_upload_mb} MB the transcription "
                f"service accepts. Split it into shorter pieces."
            )

        logger.info(
            "Prepared %s for transcription: %d bytes -> %d bytes",
            filename, len(data), len(reduced),
        )
        return reduced, "audio/mpeg", f"{Path(filename).stem}.mp3"
    finally:
        Path(source_path).unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)


async def transcribe(
    db: Session,
    *,
    user_id: int,
    data: bytes,
    filename: str,
    content_type: str,
    language: str | None = None,
    translate_to_english: bool = False,
    provider_name: str | None = None,
    style: dict | None = None,
    store_source: bool = True,
    project_id: int | None = None,
) -> dict:
    """Transcribe a media file and return cues plus what produced them.

    `store_source` keeps the uploaded media as an asset. On by default because
    the cue editor needs to play the audio back to check timing — subtitles
    edited without hearing them are subtitles edited blind.
    """
    if not data:
        raise TranscriptionError("That file is empty.")

    content_type = asset_service.normalize_content_type(content_type, filename)
    if content_type not in ACCEPTED_MEDIA:
        raise TranscriptionError(
            f"{content_type} files cannot be transcribed. Upload a video or an "
            f"audio recording."
        )

    ceiling = asset_service.max_upload_bytes()
    if len(data) > ceiling:
        raise TranscriptionError(
            f"That file is {len(data) / (1024 * 1024):.0f} MB. The limit is "
            f"{settings.video_max_upload_mb} MB."
        )

    # Measure before anything expensive: the allowance is checked against the
    # real length, and a file we cannot decode is rejected here rather than by
    # the vendor after an upload.
    try:
        info = probe_bytes(data, suffix=Path(filename).suffix or ".bin")
    except FFmpegError as exc:
        raise TranscriptionError(str(exc)) from exc

    if not info.has_audio:
        raise TranscriptionError(
            "That file has no audio track, so there is nothing to transcribe."
        )

    metering.check_allowance(
        db,
        user_id=user_id,
        metric="transcription_seconds",
        requested=info.duration_seconds,
    )

    try:
        provider = get_transcription_provider(provider_name)
    except MediaProviderConfigError:
        # Not flattened into TranscriptionError: a missing key is the
        # operator's problem and the route answers 503 for it, which is a
        # different message from "there is something wrong with your file".
        raise

    audio, audio_type, audio_name = prepare_audio(
        data, content_type=content_type, filename=filename
    )

    try:
        transcript: Transcript = await provider.transcribe(
            audio=audio,
            filename=audio_name,
            content_type=audio_type,
            language=language,
            word_timestamps=True,
            translate_to_english=translate_to_english,
        )
    except MediaProviderConfigError:
        raise
    except MediaProviderError as exc:
        raise TranscriptionError(str(exc)) from exc

    cues = subtitle_engine.cues_from_transcript(transcript, style=style)
    if not cues:
        raise TranscriptionError(
            "No speech was found in that file. Check that someone is speaking "
            "and that the audio is not silent."
        )

    source_asset: VideoAsset | None = None
    if store_source:
        try:
            source_asset = asset_service.store_asset(
                db,
                user_id=user_id,
                kind=_asset_kind(content_type),
                data=data,
                content_type=content_type,
                title=Path(filename).stem[:200] or "Transcription source",
                filename=filename,
                project_id=project_id,
                meta={"source": "subtitle_studio"},
                probe=False,
                duration_seconds=info.duration_seconds or None,
                width=info.width,
                height=info.height,
            )
        except asset_service.AssetError:
            # The transcript is the thing the user waited for. Failing to keep
            # a playback copy is worth logging, not worth throwing the cues
            # away over.
            logger.exception("Could not store the transcription source for user %s", user_id)

    metering.record(
        db,
        user_id=user_id,
        metric="transcription_seconds",
        quantity=transcript.duration_seconds or info.duration_seconds,
        source="subtitle_studio",
        project_id=project_id,
        meta={"provider": transcript.provider, "model": transcript.model},
    )

    return {
        "cues": cues,
        "text": transcript.text,
        # Whisper reports a language *name* ("English"), not a code. Passed
        # through as-is rather than guessed at — a wrong code is worse than a
        # readable name.
        "language": transcript.language,
        "duration_seconds": transcript.duration_seconds or info.duration_seconds,
        "provider": transcript.provider,
        "model": transcript.model,
        "word_count": len(transcript.words),
        "words": [
            {"start": w.start, "end": w.end, "word": w.word} for w in transcript.words
        ],
        "source_asset_id": source_asset.id if source_asset else None,
        "source_url": (
            f"{settings.backend_url}/api/storage/o/{source_asset.token}"
            if source_asset
            else None
        ),
        "translated": translate_to_english,
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

# Format -> how it is written, what it is, and what to call the file.
EXPORT_FORMATS: dict[str, dict] = {
    "srt": {
        "writer": subtitle_engine.to_srt,
        "content_type": "application/x-subrip",
        "extension": "srt",
        "label": "SubRip (.srt)",
    },
    "vtt": {
        "writer": subtitle_engine.to_vtt,
        "content_type": "text/vtt",
        "extension": "vtt",
        "label": "WebVTT (.vtt)",
    },
    "txt": {
        "writer": subtitle_engine.to_txt,
        "content_type": "text/plain",
        "extension": "txt",
        "label": "Plain text (.txt)",
    },
}


def render(cues: list[dict], fmt: str) -> tuple[str, str, str]:
    """Write cues in one format. Returns `(text, content_type, extension)`."""
    spec = EXPORT_FORMATS.get((fmt or "").lower())
    if spec is None:
        raise TranscriptionError(
            f"{fmt!r} is not a subtitle format this can write "
            f"({', '.join(EXPORT_FORMATS)})."
        )
    if not cues:
        raise TranscriptionError("There are no subtitles to export yet.")

    return spec["writer"](cues), spec["content_type"], spec["extension"]


def export_asset(
    db: Session,
    *,
    user_id: int,
    cues: list[dict],
    fmt: str,
    title: str | None = None,
    project_id: int | None = None,
    language: str | None = None,
    commit: bool = True,
) -> VideoAsset:
    """Write cues to object storage as a subtitle file.

    Goes through `assets.store_asset` like every other file, so the bytes land
    in the bucket and the row keeps only a key — a subtitle file is small, but
    "small files may go in the database" is exactly the exception that grows
    until the rule is meaningless.
    """
    text, content_type, extension = render(cues, fmt)
    stem = (title or "subtitles").strip()[:60] or "subtitles"

    return asset_service.store_asset(
        db,
        user_id=user_id,
        kind="subtitle",
        data=text.encode("utf-8"),
        content_type=content_type,
        title=f"{stem}.{extension}",
        filename=f"{stem}.{extension}",
        project_id=project_id,
        meta={
            "format": extension,
            "cue_count": len(cues),
            "duration_seconds": subtitle_engine.total_duration(cues),
            "language": language,
            # The cues themselves, so a downloaded file can be reopened for
            # editing without re-parsing it out of SRT.
            "cues": cues,
        },
        probe=False,
        commit=commit,
    )
