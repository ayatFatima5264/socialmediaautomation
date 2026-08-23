"""FFmpeg: locating the binary, and reading what a media file actually is.

Video Studio needs two facts about every file that enters it — how long it runs
and, for visual media, how big the frame is. Both must come from the file, not
from what the uploader claimed: a timeline laid out from a wrong duration is
wrong everywhere downstream, and the render limit is meaningless if the length
is self-reported.

**Why not ffprobe.** The project already depends on `imageio-ffmpeg`, which
bundles a static `ffmpeg` binary — that is what MoviePy shells out to for the
existing Reel renderer, and it is the reason this app needs no system package on
Render. It does **not** bundle `ffprobe`. So the facts are parsed out of what
`ffmpeg` prints when asked to decode a file to nowhere, which every build can
do. A system `ffprobe` is used when one happens to be on PATH, because its JSON
is exact and free.

Everything here is blocking. Callers on the event loop must go through
`asyncio.to_thread`, exactly as video_service.py already does for encoding.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    """FFmpeg is unavailable, or failed on a file."""


@lru_cache
def ffmpeg_path() -> str:
    """Absolute path to an ffmpeg binary.

    Prefers the one bundled with imageio-ffmpeg so behaviour is identical on a
    developer's laptop and on Render, where no ffmpeg is installed.
    """
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - only when the wheel is missing
        found = shutil.which("ffmpeg")
        if found:
            return found
        raise FFmpegError(
            "No ffmpeg binary is available. Install imageio-ffmpeg or put "
            "ffmpeg on PATH."
        )


@lru_cache
def ffprobe_path() -> str | None:
    """A system ffprobe, if there is one. None is the normal case."""
    return shutil.which("ffprobe")


@dataclass(frozen=True)
class MediaInfo:
    """What a media file really is."""

    duration_seconds: float
    width: int | None = None
    height: int | None = None
    has_video: bool = False
    has_audio: bool = False

    @property
    def is_video(self) -> bool:
        return self.has_video


# Both of these read ffmpeg's human-readable log, which is stable across
# versions but is not an API — hence one regex per fact and a tolerant caller.
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")
_TIME_RE = re.compile(r"time=\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")
_VIDEO_RE = re.compile(r"Stream #\d+:\d+.*?:\s*Video:.*?,\s*(\d{2,5})x(\d{2,5})")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+.*?:\s*Audio:")


def _hms(hours: str, minutes: str, seconds: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _probe_with_ffprobe(path: Path, probe: str) -> MediaInfo | None:
    """Exact answers from ffprobe's JSON, when a system ffprobe exists."""
    try:
        out = subprocess.run(
            [
                probe,
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            timeout=60,
            check=True,
        ).stdout
        data = json.loads(out)
    except Exception:
        return None

    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = 0.0
    for candidate in (data.get("format", {}).get("duration"), (video or {}).get("duration"), (audio or {}).get("duration")):
        try:
            duration = float(candidate)
            break
        except (TypeError, ValueError):
            continue

    # A still image decodes as a one-frame video stream with no duration. That
    # is not a zero-length video, it is an image — the caller decides how long
    # to show it, so 0.0 is the honest answer.
    return MediaInfo(
        duration_seconds=max(0.0, duration),
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        has_video=video is not None,
        has_audio=audio is not None,
    )


def probe(path: str | Path) -> MediaInfo:
    """Read duration and dimensions from a media file.

    Raises FFmpegError when the file cannot be decoded at all — which is how an
    upload of something that is not media is rejected, rather than being stored
    and failing later inside a render.
    """
    path = Path(path)
    if not path.exists():
        raise FFmpegError(f"No such media file: {path}")

    probe_bin = ffprobe_path()
    if probe_bin:
        info = _probe_with_ffprobe(path, probe_bin)
        if info is not None:
            return info

    # Decode to nothing and read the log. `-f null` runs the whole file, so the
    # final `time=` is the true duration even when the container header lies —
    # which VBR MP3 routinely does.
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-i", str(path), "-f", "null", "-"],
            capture_output=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("Timed out while reading that media file.") from exc
    except OSError as exc:
        raise FFmpegError(f"Could not run ffmpeg: {exc}") from exc

    log = result.stderr.decode("utf-8", "replace")

    if "Invalid data found" in log or "Invalid argument" in log:
        raise FFmpegError("That file could not be read as audio or video.")

    duration = 0.0
    times = _TIME_RE.findall(log)
    if times:
        duration = _hms(*times[-1])
    else:
        header = _DURATION_RE.search(log)
        if header:
            duration = _hms(*header.groups())

    video_match = _VIDEO_RE.search(log)
    has_audio = bool(_AUDIO_RE.search(log))

    if not video_match and not has_audio:
        raise FFmpegError("That file contains no audio or video stream.")

    return MediaInfo(
        duration_seconds=max(0.0, duration),
        width=int(video_match.group(1)) if video_match else None,
        height=int(video_match.group(2)) if video_match else None,
        has_video=video_match is not None,
        has_audio=has_audio,
    )


def probe_bytes(data: bytes, *, suffix: str = ".bin") -> MediaInfo:
    """`probe`, for media that only exists in memory.

    FFmpeg needs a seekable input to read a container header, so the bytes go
    to a temporary file. It is removed before returning, on every path.
    """
    import tempfile
    import os

    fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="autosocial_probe_")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return probe(tmp)
    finally:
        Path(tmp).unlink(missing_ok=True)


# The audio formats Voice Studio can hand a user, and how to encode each.
# MP3 for sharing and uploading, WAV for editing — those are the two a person
# actually asks for, and offering a longer list would mean maintaining encoder
# settings nobody uses.
AUDIO_FORMATS: dict[str, dict] = {
    "mp3": {
        "content_type": "audio/mpeg",
        "extension": "mp3",
        # 192k CBR: transparent for speech and universally playable. VBR would
        # be smaller but some social platforms still mis-read VBR headers.
        "args": ["-vn", "-c:a", "libmp3lame", "-b:a", "192k"],
    },
    "wav": {
        "content_type": "audio/wav",
        "extension": "wav",
        # 16-bit PCM at 44.1 kHz — what every editor expects to be handed.
        "args": ["-vn", "-c:a", "pcm_s16le", "-ar", "44100"],
    },
}


def transcode_audio(data: bytes, *, source_suffix: str, target: str) -> bytes:
    """Re-encode audio bytes into `target` ("mp3" or "wav").

    Voice Studio offers both downloads, but a provider gives us exactly one:
    edge-tts returns MP3, Groq returns WAV, a local server returns whatever it
    was configured for. Rather than hide whichever the user did not ask for, or
    store both copies of every take, the other one is produced on demand here.

    Returns the input untouched when it is already in the target format, so the
    common download costs nothing.
    """
    target = (target or "").lower()
    spec = AUDIO_FORMATS.get(target)
    if spec is None:
        raise FFmpegError(
            f"{target!r} is not a format this can produce "
            f"({', '.join(AUDIO_FORMATS)})."
        )

    if source_suffix.lstrip(".").lower() == spec["extension"]:
        return data

    import os
    import tempfile

    in_fd, in_path = tempfile.mkstemp(
        suffix=f".{source_suffix.lstrip('.')}", prefix="autosocial_tts_in_"
    )
    out_fd, out_path = tempfile.mkstemp(
        suffix=f".{spec['extension']}", prefix="autosocial_tts_out_"
    )
    # Closed immediately: ffmpeg opens the output path itself, and on Windows
    # an open handle would make it fail with "permission denied".
    os.close(out_fd)

    try:
        with os.fdopen(in_fd, "wb") as handle:
            handle.write(data)

        command = [
            ffmpeg_path(),
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", in_path,
            *spec["args"],
            out_path,
        ]

        try:
            result = subprocess.run(command, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            raise FFmpegError("Timed out while converting that audio.") from exc
        except OSError as exc:
            raise FFmpegError(f"Could not run ffmpeg: {exc}") from exc

        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
            raise FFmpegError(
                "Could not convert that audio"
                + (f": {detail[-1]}" if detail else ".")
            )

        converted = Path(out_path).read_bytes()
        if not converted:
            raise FFmpegError("The audio conversion produced an empty file.")
        return converted
    finally:
        Path(in_path).unlink(missing_ok=True)
        Path(out_path).unlink(missing_ok=True)


def extract_audio(source: str | Path, destination: str | Path) -> None:
    """Write a file's audio track out as 16 kHz mono MP3.

    Transcription providers cap the upload size, and a 200 MB source video is
    mostly pixels the model never looks at. Stripping to mono speech-rate audio
    routinely takes two orders of magnitude off that, which is the difference
    between a video being transcribable and not.
    """
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(source),
        "-vn",                 # drop video
        "-ac", "1",            # mono
        "-ar", "16000",        # what Whisper resamples to anyway
        "-b:a", "64k",
        str(destination),
    ]

    try:
        result = subprocess.run(command, capture_output=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("Timed out while extracting audio.") from exc
    except OSError as exc:
        raise FFmpegError(f"Could not run ffmpeg: {exc}") from exc

    if result.returncode != 0 or not destination.exists():
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise FFmpegError(
            "Could not extract audio from that file"
            + (f": {detail[-1]}" if detail else ".")
        )
