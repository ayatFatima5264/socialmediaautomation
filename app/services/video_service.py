"""Image → vertical MP4 ("Reel") rendering.

A still image becomes a short video with a slow pan + zoom, so a generated or
uploaded picture can be published to the video-first surfaces (Reels, Shorts,
TikTok) that won't take a static image at all.

Two things here are security boundaries rather than polish. The source URL is
supplied by the caller and fetched *by our server*, so it is checked against
private address space on every redirect hop — otherwise this route is an
internal-network probe. And the download is capped and streamed, so a URL that
happens to serve gigabytes can't exhaust memory before the type check runs.

Rendering is CPU-bound and synchronous; `generate_image_video` keeps it off the
event loop. The caller owns the returned file.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
import numpy as np
from PIL import Image
from moviepy import VideoClip

logger = logging.getLogger(__name__)


class VideoGenerationError(Exception):
    """Raised when image-to-video generation fails."""


DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_DURATION = 5.0
DEFAULT_ZOOM = 1.08

FPS = 30

# A source photo, not a video file or a decompression bomb. Generous next to a
# phone camera's 5-10 MB, small enough that a hostile URL can't exhaust memory.
MAX_SOURCE_BYTES = 20 * 1024 * 1024

# Enough for a CDN's http→https and a shortener; not an open-ended chain.
MAX_REDIRECTS = 3


def _assert_public_http_url(url: str) -> None:
    """Reject anything that isn't an http(s) URL resolving to a public address.

    The caller hands us a URL and *our server* fetches it, so without this the
    endpoint reads the cloud metadata service (169.254.169.254), localhost, and
    anything else on the private network on an attacker's behalf.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise VideoGenerationError("Image URL must be an http or https URL.")

    host = parsed.hostname
    if not host:
        raise VideoGenerationError("Image URL has no host.")

    try:
        resolved = socket.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise VideoGenerationError(
            f"Could not resolve the image host: {host}"
        ) from exc

    for info in resolved:
        address = ipaddress.ip_address(info[4][0])
        # is_global is False for loopback, link-local, private and reserved
        # ranges — every address family, one check.
        if not address.is_global or address.is_multicast:
            raise VideoGenerationError(
                "Image URL must point at a public host."
            )


async def _read_capped(response: httpx.Response) -> bytes:
    """Read a streamed response body, refusing to buffer more than the cap."""

    declared = response.headers.get("content-length", "")

    if declared.isdigit() and int(declared) > MAX_SOURCE_BYTES:
        raise VideoGenerationError(
            f"Source image is larger than "
            f"{MAX_SOURCE_BYTES // (1024 * 1024)} MB."
        )

    chunks: list[bytes] = []
    total = 0

    async for chunk in response.aiter_bytes():
        total += len(chunk)

        # A missing or lying content-length is the normal case, not the
        # exception — this is the limit that actually holds.
        if total > MAX_SOURCE_BYTES:
            raise VideoGenerationError(
                f"Source image is larger than "
                f"{MAX_SOURCE_BYTES // (1024 * 1024)} MB."
            )

        chunks.append(chunk)

    if not total:
        raise VideoGenerationError("The image URL returned an empty response.")

    return b"".join(chunks)


async def _fetch_image_bytes(image_url: str) -> bytes:
    """Download an image URL, refusing anything that isn't a public image."""

    if not image_url or not image_url.strip():
        raise VideoGenerationError("Image URL must not be empty.")

    url = image_url.strip()

    try:
        # Redirects are followed by hand: a public URL is free to redirect to
        # an internal one, and it's the *final* host that gets fetched.
        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=False,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                _assert_public_http_url(url)

                async with client.stream("GET", url) as response:
                    # The status code, not response.is_redirect: that is False
                    # for a 3xx with no Location, which would fall through and
                    # be read as a body.
                    if httpx.codes.is_redirect(response.status_code):
                        location = response.headers.get("location")

                        if not location:
                            raise VideoGenerationError(
                                "Image URL redirected without a destination."
                            )

                        url = str(response.url.join(location))
                        continue

                    response.raise_for_status()

                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";")[0]
                        .strip()
                        .lower()
                    )

                    # Deliberately not echoed back: the caller shouldn't learn
                    # what an internal host answered with.
                    if not content_type.startswith("image/"):
                        raise VideoGenerationError(
                            "The URL did not return an image."
                        )

                    return await _read_capped(response)

            raise VideoGenerationError("Image URL redirected too many times.")

    except httpx.HTTPError as exc:
        raise VideoGenerationError(f"Failed to download image: {exc}") from exc


def _prepare_image(
    input_path: Path,
    output_path: Path,
    width: int,
    height: int,
) -> None:
    """
    Crop and resize the source image to the requested video canvas.

    The image is cropped proportionally so it fills the complete video
    without stretching or distortion.
    """

    try:
        with Image.open(input_path) as image:
            image = image.convert("RGB")

            target_ratio = width / height
            image_ratio = image.width / image.height

            if image_ratio > target_ratio:
                # Source is wider -> crop left/right.
                new_width = int(image.height * target_ratio)
                left = (image.width - new_width) // 2

                image = image.crop(
                    (
                        left,
                        0,
                        left + new_width,
                        image.height,
                    )
                )

            elif image_ratio < target_ratio:
                # Source is taller -> crop top/bottom.
                new_height = int(image.width / target_ratio)
                top = (image.height - new_height) // 2

                image = image.crop(
                    (
                        0,
                        top,
                        image.width,
                        top + new_height,
                    )
                )

            image = image.resize(
                (width, height),
                Image.Resampling.LANCZOS,
            )

            image.save(
                output_path,
                format="JPEG",
                quality=95,
            )

    except Exception as exc:
        raise VideoGenerationError(
            f"Failed to prepare image: {exc}"
        ) from exc


def _create_zoom_video(
    image_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
    duration: float,
    zoom: float,
) -> None:
    """
    Create a vertical social video with smooth cinematic
    pan + zoom movement.

    The camera slowly moves across the image while gradually
    zooming in. This makes a still image feel animated instead
    of simply zooming in place.

    `zoom` is honoured exactly: the first frame is the untouched framing and
    the last is `zoom`x into it, so `zoom=1.0` means a still image.
    """

    try:
        # Working at zoom×target gives the crop window somewhere to move. At
        # the start it covers the whole source (the framing the caller asked
        # for); by the end it has tightened to a target-sized window.
        with Image.open(image_path) as opened:
            source = opened.convert("RGB").resize(
                (
                    round(width * zoom),
                    round(height * zoom),
                ),
                Image.Resampling.LANCZOS,
            )

        source_width, source_height = source.size

        def smoothstep(value: float) -> float:
            value = min(max(value, 0.0), 1.0)
            return value * value * (3.0 - 2.0 * value)

        def make_frame(t: float):
            progress = min(max(t / duration, 0.0), 1.0)

            # Smooth cinematic movement.
            eased = smoothstep(progress)

            # Gradual zoom: 1.0 (whole source) -> zoom (a target-sized crop).
            current_scale = 1.0 + ((zoom - 1.0) * eased)

            crop_width = max(1, round(source_width / current_scale))
            crop_height = max(1, round(source_height / current_scale))

            # Gentle camera movement:
            # starts slightly left/top and gradually moves
            # toward right/bottom.
            max_left = max(0, source_width - crop_width)
            max_top = max(0, source_height - crop_height)

            horizontal_progress = smoothstep(progress)
            vertical_progress = smoothstep(
                min(max(progress * 1.15, 0.0), 1.0)
            )

            # Small diagonal cinematic movement.
            left = int(max_left * (0.20 + 0.60 * horizontal_progress))
            top = int(max_top * (0.15 + 0.55 * vertical_progress))

            left = max(0, min(left, max_left))
            top = max(0, min(top, max_top))

            right = left + crop_width
            bottom = top + crop_height

            frame = source.crop(
                (left, top, right, bottom)
            )

            # BICUBIC, not LANCZOS: this runs once per frame (30 × duration),
            # and the crop is within ~zoom× of the output size, where the two
            # are hard to tell apart.
            frame = frame.resize(
                (width, height),
                Image.Resampling.BICUBIC,
            )

            # MoviePy 2.x expects a NumPy array here.
            return np.array(frame)

        clip = VideoClip(
            frame_function=make_frame,
            duration=duration,
        )

        try:
            clip.write_videofile(
                str(output_path),
                fps=FPS,
                codec="libx264",
                audio=False,
                logger=None,
            )
        finally:
            # In a finally, not after the call: a failed encode otherwise
            # leaves the ffmpeg handles open, and on Windows that open handle
            # is what makes the temp-directory cleanup fail.
            clip.close()
            source.close()

    except Exception as exc:
        raise VideoGenerationError(
            f"Failed to generate video: {exc}"
        ) from exc


async def generate_image_video(
    image_url: str,
    *,
    duration: float = DEFAULT_DURATION,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    zoom: float = DEFAULT_ZOOM,
    output_path: str | None = None,
) -> str:
    """
    Convert an existing image URL into a vertical MP4 Reel.

    Defaults:
        1080x1920
        5 seconds
        30 FPS
        subtle zoom-in
        no audio

    Returns:
        Path to the generated MP4 file.

    The caller owns that file and must delete it. Without `output_path` it is
    an unnamed temporary file, which nothing else will ever clean up — pass an
    explicit path whenever the lifetime matters.
    """

    if duration <= 0:
        raise VideoGenerationError(
            "Video duration must be greater than 0."
        )

    if width <= 0 or height <= 0:
        raise VideoGenerationError(
            "Video width and height must be greater than 0."
        )

    if zoom < 1.0:
        raise VideoGenerationError(
            "Zoom must be >= 1.0."
        )

    if zoom > 1.5:
        raise VideoGenerationError(
            "Zoom must not be greater than 1.5."
        )

    if output_path:
        final_output = Path(output_path)

        final_output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    else:
        fd, temp_output = tempfile.mkstemp(
            suffix=".mp4",
        )

        os.close(fd)

        final_output = Path(temp_output)

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="autosocial_video_"
        )
    )

    downloaded_image = temp_dir / "source.jpg"
    prepared_image = temp_dir / "prepared.jpg"

    try:
        # 1. Download source image.
        downloaded_image.write_bytes(
            await _fetch_image_bytes(image_url)
        )

        # 2. Prepare image for 9:16 video.
        #
        # Steps 2 and 3 are CPU-bound and synchronous — a per-frame resize plus
        # an x264 encode, seconds to minutes of work. On the event loop that
        # stalls every other request in the process, so they run in a thread.
        await asyncio.to_thread(
            _prepare_image,
            downloaded_image,
            prepared_image,
            width,
            height,
        )

        # 3. Create MP4 with zoom effect.
        await asyncio.to_thread(
            _create_zoom_video,
            prepared_image,
            final_output,
            width=width,
            height=height,
            duration=duration,
            zoom=zoom,
        )

        if not final_output.exists():
            raise VideoGenerationError(
                "Video generation completed but output file was not created."
            )

        if final_output.stat().st_size == 0:
            raise VideoGenerationError(
                "Video generation created an empty output file."
            )

        logger.info(
            "Generated Reel video: %s",
            final_output,
        )

        return str(final_output)

    except VideoGenerationError:
        # Unconditionally, including the unnamed temp file: on this path the
        # caller never learns the path, so if we don't remove it nobody can.
        final_output.unlink(missing_ok=True)

        raise

    except Exception as exc:
        final_output.unlink(missing_ok=True)

        raise VideoGenerationError(
            f"Unexpected video generation error: {exc}"
        ) from exc

    finally:
        if temp_dir.exists():
            for file_path in temp_dir.iterdir():
                try:
                    file_path.unlink(
                        missing_ok=True
                    )
                except Exception:
                    pass

            try:
                temp_dir.rmdir()
            except OSError:
                pass
