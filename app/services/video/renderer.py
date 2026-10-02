"""The render worker — the thing that actually produces the file.

`renders.py` owns the state machine; `compositor.py` turns a timeline into an
ffmpeg command. This module is what runs between them: it claims a queued job,
pulls the sources out of object storage, runs the encoder, reports real
progress, and hands the finished file back as an asset.

**It renders the snapshot, not the project.** `queue_render` froze the timeline
when the job was created, so editing the project while it exports cannot change
what is being encoded, and a retry of a failed job reproduces the same file
rather than whatever the timeline looks like now.

**Progress is measured, never simulated.** The fraction comes from ffmpeg's own
`time=` output divided by the timeline's length. Nothing here advances a bar on
a timer — a bar that moves while nothing is happening is worse than no bar,
because it turns a hung render into a render that appears to be working.

**Every failure has a code and a stage.** The stage is where it died and the
code is what the UI branches on: `missing_asset` offers to open the project,
`storage_error` offers to retry, `ffmpeg_error` offers to report it. "Render
failed" on its own is unsupportable, which is why `fail` is never called
without both.

**Cancellation is cooperative.** `renders.cancel` marks the row; this loop
notices within a second and terminates the subprocess. The alternative — the
API killing a process it does not own — does not survive rendering moving to a
separate worker, which is the direction this is built for.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.video_asset import VideoAsset
from app.models.video_project import VideoProject
from app.models.video_render import VideoRender
from app.services.storage.base import StorageError, extension_for
from app.services.video import assets as asset_service
from app.services.video import compositor
from app.services.video import renders as render_service
from app.services.video import timeline as tl
from app.services.video.ffmpeg import (
    FFmpegError,
    extract_poster,
    ffmpeg_path,
    probe,
)

logger = logging.getLogger(__name__)

# ffmpeg's progress line. Matched rather than parsed from `-progress` because
# `-stats` on stderr works identically on every build, including the static
# ones this app ships with.
_TIME_RE = re.compile(rb"time=\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")

# How often the worker looks at its own row to see whether the user cancelled.
_CANCEL_POLL_SECONDS = 1.0

# A hard ceiling on one encode. Nothing should reach it — the duration cap in
# `render_refusal` keeps projects short — but a filter graph that stalls would
# otherwise hold a worker slot forever.
_TIMEOUT_SECONDS = 30 * 60


class RenderExecutionError(RuntimeError):
    """A render failed. Carries the code the UI branches on."""

    def __init__(self, message: str, *, code: str = "unknown"):
        super().__init__(message)
        self.code = code


def _fraction(line: bytes, total: float) -> float | None:
    """The progress fraction from one line of ffmpeg output, if it has one."""
    match = _TIME_RE.search(line)
    if not match or total <= 0:
        return None
    hours, minutes, seconds = match.groups()
    position = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return max(0.0, min(position / total, 1.0))


# ---------------------------------------------------------------------------
# Preparing
# ---------------------------------------------------------------------------


def _resolve_sources(
    db: Session, *, render: VideoRender, document: dict, work: Path
) -> dict[int, compositor.Source]:
    """Pull every asset the timeline needs out of storage and probe it.

    Done up front, before any encoding, so a missing or unreadable file is
    reported in seconds with `missing_asset` rather than as an ffmpeg error
    several minutes into a job.

    Assets are looked up scoped to the render's owner. A timeline naming
    somebody else's asset id resolves to nothing and fails as missing — it is
    not a way to read another account's media.
    """
    sources: dict[int, compositor.Source] = {}

    for asset_id in tl.asset_ids(document):
        try:
            asset = asset_service.get_asset(
                db, user_id=render.user_id, asset_id=asset_id
            )
        except asset_service.AssetError as exc:
            raise RenderExecutionError(
                "A file this video uses is no longer in your library. Open the "
                "project and replace the missing clip.",
                code="missing_asset",
            ) from exc

        try:
            data, content_type = asset_service.read_asset(asset)
        except asset_service.AssetError as exc:
            raise RenderExecutionError(
                f"Could not read “{asset.title}” from storage.",
                code="storage_error",
            ) from exc

        path = work / f"asset_{asset_id}.{extension_for(content_type)}"
        path.write_bytes(data)

        try:
            info = probe(path)
        except FFmpegError as exc:
            raise RenderExecutionError(
                f"“{asset.title}” could not be decoded: {exc}",
                code="missing_asset",
            ) from exc

        sources[asset_id] = compositor.Source(
            path=str(path),
            duration=info.duration_seconds,
            width=info.width,
            height=info.height,
            has_video=info.has_video,
            has_audio=info.has_audio,
        )

    return sources


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def _run_ffmpeg(
    db: Session,
    *,
    render: VideoRender,
    args: list[str],
    total: float,
) -> None:
    """Run the encoder, reporting progress and honouring cancellation.

    stderr is read on a thread rather than with `communicate()`, because
    progress has to be observed *while* the process runs. A pipe that nobody
    drains also fills its buffer and deadlocks the child, which is the classic
    way a subprocess "hangs" at exactly the same point every time.
    """
    argv = [ffmpeg_path(), *args]
    logger.info("Render %s: encoding with %d filter inputs", render.id, len(args))

    process = subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    tail: list[bytes] = []
    latest = {"fraction": 0.0}

    def _drain() -> None:
        assert process.stderr is not None
        # Split on \r as well as \n: ffmpeg writes its stats line with a
        # carriage return so it overwrites itself in a terminal, which means
        # readline() would return one enormous line for the whole encode.
        buffer = b""
        while True:
            chunk = process.stderr.read(256)
            if not chunk:
                break
            buffer += chunk
            while True:
                index = min(
                    (i for i in (buffer.find(b"\r"), buffer.find(b"\n")) if i >= 0),
                    default=-1,
                )
                if index < 0:
                    break
                line, buffer = buffer[:index], buffer[index + 1 :]
                if not line:
                    continue
                fraction = _fraction(line, total)
                if fraction is not None:
                    latest["fraction"] = fraction
                else:
                    # Keep only the last few lines: an ffmpeg error is at the
                    # end, and storing the whole log would put megabytes of
                    # per-frame warnings in a database column.
                    tail.append(line)
                    del tail[:-40]
        if buffer:
            tail.append(buffer)
            del tail[:-40]

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()

    deadline = time.monotonic() + _TIMEOUT_SECONDS
    reported = -1.0

    try:
        while process.poll() is None:
            time.sleep(_CANCEL_POLL_SECONDS)

            # Only write when the number actually moved, so a long encode does
            # not become one UPDATE per second for the same value.
            fraction = latest["fraction"]
            if fraction - reported >= 0.01:
                reported = fraction
                # Encoding is the bulk of the work but not all of it: the bar
                # is mapped into the span this stage owns so it does not hit
                # 100% while uploading is still to come.
                render_service.report_progress(
                    db, render=render, stage="encoding", progress=0.15 + fraction * 0.75
                )

            db.refresh(render)
            if render.status == "cancelled":
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    process.kill()
                raise RenderExecutionError("The render was cancelled.", code="cancelled")

            if time.monotonic() > deadline:  # pragma: no cover — a stall guard
                process.kill()
                raise RenderExecutionError(
                    "The render took too long and was stopped.", code="timeout"
                )
    finally:
        reader.join(timeout=5)

    if process.returncode != 0:
        log = b"\n".join(tail).decode("utf-8", "replace").strip()
        logger.error("Render %s: ffmpeg exited %s\n%s", render.id, process.returncode, log)
        raise RenderExecutionError(
            "The video could not be encoded.\n\n" + (log[-4000:] or "No output from ffmpeg."),
            code="ffmpeg_error",
        )


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------


def _store_poster_frame(
    db: Session,
    *,
    render: VideoRender,
    project: VideoProject,
    output: Path,
    name: str,
) -> int | None:
    """Save one frame of the finished render as the project's thumbnail.

    Returns the new asset's id, or None when a frame could not be produced or
    stored. Never raises: a missing poster must not turn a successful render
    into a failed one.

    A thumbnail the user chose themselves is left alone — this is a default, not
    an opinion about their design work.
    """
    if project.thumbnail_asset_id is not None:
        return None

    try:
        data = extract_poster(output, output.parent / "poster.png")
    except FFmpegError as exc:
        logger.warning("Render %s: no poster frame (%s)", render.id, exc)
        return None

    if not data:
        logger.warning("Render %s: poster frame was empty", render.id)
        return None

    try:
        asset = asset_service.store_asset(
            db,
            user_id=render.user_id,
            kind="thumbnail",
            data=data,
            content_type="image/png",
            title=f"{name[:60]} (poster)",
            filename=f"{name[:60]}.png",
            project_id=project.id,
            # Read out of the frame itself rather than from the project: the
            # compositor can letterbox or scale, so the poster's dimensions are
            # not necessarily the canvas's.
            meta={"render_id": render.id, "source": "render_poster"},
        )
    except asset_service.AssetError as exc:
        logger.warning("Render %s: poster frame not stored (%s)", render.id, exc)
        return None

    logger.info("Render %s: poster frame stored as asset %s", render.id, asset.id)
    return asset.id


def execute(db: Session, render: VideoRender) -> VideoRender:
    """Run one queued render to completion, or record why it could not run.

    Never raises for an ordinary failure: a job that cannot be rendered ends as
    a `failed` row with a code and a message, because that is what the client
    is polling. Exceptions escape only if the *bookkeeping* itself fails, which
    is a bug rather than a render outcome.
    """
    if render.status != "queued":
        raise render_service.RenderError(
            f"A {render.status} render cannot be executed."
        )

    project = db.get(VideoProject, render.project_id)
    if project is None:  # pragma: no cover — a project deleted mid-queue
        return render_service.fail(
            db,
            render=render,
            error="The project no longer exists.",
            error_code="invalid_timeline",
        )

    render_service.start(db, render=render)
    work = Path(tempfile.mkdtemp(prefix=f"render_{render.id}_"))

    try:
        # ---- preparing ---------------------------------------------------
        render_service.report_progress(db, render=render, stage="preparing", progress=0.02)

        document = tl.normalize(render.timeline_snapshot)
        if tl.is_empty(document):
            raise RenderExecutionError(
                "There is nothing on the timeline to render.",
                code="invalid_timeline",
            )

        # ---- downloading -------------------------------------------------
        render_service.report_progress(
            db, render=render, stage="downloading", progress=0.05
        )
        sources = _resolve_sources(db, render=render, document=document, work=work)

        # ---- encoding ----------------------------------------------------
        output = work / "output.mp4"
        try:
            plan = compositor.build_command(
                timeline=document,
                width=project.width,
                height=project.height,
                fps=project.fps,
                sources=sources,
                output_path=output,
                work_dir=work,
                settings=render.settings or {},
            )
        except compositor.CompositorError as exc:
            raise RenderExecutionError(str(exc), code="invalid_timeline") from exc

        render_service.report_progress(db, render=render, stage="encoding", progress=0.15)
        _run_ffmpeg(db, render=render, args=plan.args, total=plan.duration)

        if not output.exists() or output.stat().st_size == 0:
            raise RenderExecutionError(
                "The encoder produced no output.", code="ffmpeg_error"
            )

        # ---- uploading ---------------------------------------------------
        render_service.report_progress(
            db, render=render, stage="uploading", progress=0.92
        )

        name = "".join(
            character if character.isalnum() or character in " -_" else ""
            for character in (project.name or "video")
        ).strip() or "video"

        try:
            asset = asset_service.store_asset(
                db,
                user_id=render.user_id,
                kind="render",
                data=output.read_bytes(),
                content_type="video/mp4",
                title=f"{name[:60]} (export)",
                filename=f"{name[:60]}.mp4",
                project_id=project.id,
                # Measured already — do not decode the file a second time.
                duration_seconds=plan.duration,
                width=project.width,
                height=project.height,
                probe=False,
                meta={
                    "render_id": render.id,
                    "attempt": render.attempt,
                    "quality": (render.settings or {}).get("quality"),
                },
            )
        except asset_service.AssetError as exc:
            raise RenderExecutionError(
                f"The video rendered but could not be saved: {exc}",
                code="storage_error",
            ) from exc

        # ---- poster frame ------------------------------------------------
        # A finished video needs a real image beside it. Without one the project
        # has no thumbnail, and the PNG/JPG exports are unavailable — which used
        # to be exactly what happened, because the MP4 was assigned as the
        # thumbnail and the export then tried to decode a video as an image.
        #
        # Best-effort on purpose: a poster is a convenience, and failing the
        # whole render over one missing frame would throw away a video that
        # encoded correctly. The failure is logged and the project simply has no
        # thumbnail until the user makes one in Thumbnail Studio.
        thumbnail_asset_id = _store_poster_frame(
            db,
            render=render,
            project=project,
            output=output,
            name=name,
        )

        return render_service.complete(
            db,
            render=render,
            output_asset_id=asset.id,
            thumbnail_asset_id=thumbnail_asset_id,
            duration_seconds=plan.duration,
        )

    except RenderExecutionError as exc:
        db.rollback()
        db.refresh(render)
        if exc.code == "cancelled":
            # `cancel` already ran when the user pressed the button; the job is
            # terminal and must not be overwritten with a failure.
            if not render.is_terminal:  # pragma: no cover
                render_service.cancel(db, render=render)
            return render
        return render_service.fail(
            db, render=render, error=str(exc), error_code=exc.code
        )

    except StorageError as exc:
        db.rollback()
        db.refresh(render)
        return render_service.fail(
            db,
            render=render,
            error=f"The file store could not be reached: {exc}",
            error_code="storage_error",
        )

    except Exception as exc:  # noqa: BLE001 — a worker must not die on one job
        logger.exception("Render %s crashed", render.id)
        db.rollback()
        db.refresh(render)
        if render.is_terminal:
            return render
        return render_service.fail(
            db,
            render=render,
            error=f"The render failed unexpectedly: {exc}",
            error_code="unknown",
        )

    finally:
        shutil.rmtree(work, ignore_errors=True)


def render_capabilities() -> dict:
    """What this deployment can render, for `/api/video/capabilities`.

    Reported rather than assumed so the editor can disable the text track on a
    server with no fonts, instead of letting somebody write a title that
    silently will not export.
    """
    try:
        ffmpeg_path()
        available = True
    except FFmpegError:
        available = False

    return {
        "ffmpeg_available": available,
        "text_rendering_available": available and compositor.font_available(),
        "qualities": sorted(compositor.QUALITY_SETTINGS),
        "max_concurrent_renders": settings.video_max_concurrent_renders,
    }
