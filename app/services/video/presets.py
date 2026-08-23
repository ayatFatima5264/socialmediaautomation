"""Platform formats — "Create for TikTok" instead of "enter 1080 by 1920".

The canonical list lives on the server, not in the frontend, because three
different things need to agree on it: the Create Video screen offering the
choice, the project row recording it, and the renderer sizing the canvas. A
copy in JavaScript would be a fourth answer that drifts.

`GET /api/video/presets` serves this list, and the frontend renders whatever it
is given — so adding a platform is one entry here.

Every preset is a *starting point*, never a constraint. A project stores its own
width, height and fps and may be resized away from its preset; `platform` then
records where it began. That is what makes Multi-Format Adaptation (a 16:9
project converted to a 9:16 copy) possible without a special case.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.config import settings


@dataclass(frozen=True)
class PlatformPreset:
    key: str
    label: str
    #: The surface this publishes to, for grouping in the UI.
    family: str
    aspect_ratio: str
    width: int
    height: int
    fps: int
    #: What the platform itself allows, in seconds. Separate from the MVP
    #: render cap, which is smaller and about our compute, not their rules.
    platform_max_seconds: int
    description: str


# Ordered as the Create Video screen shows them: long-form first, then the
# vertical short-form surfaces that share a canvas, then square and landscape.
PRESETS: tuple[PlatformPreset, ...] = (
    PlatformPreset(
        key="youtube",
        label="YouTube",
        family="youtube",
        aspect_ratio="16:9",
        width=1920,
        height=1080,
        fps=30,
        platform_max_seconds=12 * 3600,
        description="Long-form landscape video.",
    ),
    PlatformPreset(
        key="youtube_shorts",
        label="YouTube Shorts",
        family="youtube",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        fps=30,
        platform_max_seconds=180,
        description="Vertical short-form, up to 3 minutes.",
    ),
    PlatformPreset(
        key="tiktok",
        label="TikTok",
        family="tiktok",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        fps=30,
        platform_max_seconds=600,
        description="Vertical, sound-on, fast-paced.",
    ),
    PlatformPreset(
        key="instagram_reels",
        label="Instagram Reels",
        family="instagram",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        fps=30,
        platform_max_seconds=180,
        description="Vertical video for Reels and Stories.",
    ),
    PlatformPreset(
        key="instagram_post",
        label="Instagram Post",
        family="instagram",
        aspect_ratio="1:1",
        width=1080,
        height=1080,
        fps=30,
        platform_max_seconds=60,
        description="Square in-feed video.",
    ),
    PlatformPreset(
        key="facebook",
        label="Facebook",
        family="facebook",
        aspect_ratio="16:9",
        width=1920,
        height=1080,
        fps=30,
        platform_max_seconds=4 * 3600,
        description="Landscape in-feed video.",
    ),
    PlatformPreset(
        key="facebook_reels",
        label="Facebook Reels",
        family="facebook",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        fps=30,
        platform_max_seconds=90,
        description="Vertical video for Facebook Reels and Stories.",
    ),
    PlatformPreset(
        key="custom",
        label="Custom",
        family="custom",
        aspect_ratio="16:9",
        width=1920,
        height=1080,
        fps=30,
        platform_max_seconds=3600,
        description="Set your own dimensions.",
    ),
)

_BY_KEY = {preset.key: preset for preset in PRESETS}

#: Aspect ratios the studio understands, and their reference canvas.
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "4:3": (1440, 1080),
    "21:9": (2560, 1080),
}


def get_preset(key: str | None) -> PlatformPreset:
    """A preset by key, falling back to Shorts.

    Vertical is the fallback deliberately: it is the format most of these
    platforms want, and a project that opens in the wrong orientation is more
    obviously wrong than one that opens at the wrong resolution.
    """
    return _BY_KEY.get((key or "").lower(), _BY_KEY["youtube_shorts"])


def limits() -> dict:
    """The MVP compute caps, as the UI must state them.

    These are ours, not the platforms'. Every one of them exists because
    rendering currently runs inside the API process on a small shared CPU, and
    every one of them should rise when rendering moves to a worker — which is
    why they are settings and this is a function rather than a constant.
    """
    return {
        "max_duration_seconds": settings.video_max_duration_seconds,
        "max_resolution_height": settings.video_max_resolution_height,
        "max_upload_mb": settings.video_max_upload_mb,
        "max_concurrent_renders": settings.video_max_concurrent_renders,
        "reason": (
            "Rendering currently runs on the API server. These limits keep one "
            "long render from slowing everything else down, and will rise when "
            "rendering moves to a dedicated worker."
        ),
    }


def as_dicts() -> list[dict]:
    """The preset list, JSON-ready."""
    return [asdict(preset) for preset in PRESETS]


def clamp_resolution(width: int, height: int) -> tuple[int, int]:
    """Scale a canvas down to the MVP resolution cap, preserving its ratio.

    The cap applies to the **short side**, not to the height. "1080p" means the
    short side is 1080 in both orientations — a 1080x1920 Short and a 1920x1080
    YouTube video are the same resolution, and only one of them has a height of
    1080.

    Comparing against height instead is the obvious reading of
    VIDEO_MAX_RESOLUTION_HEIGHT and it is wrong in a way that is easy to miss:
    every vertical project would be quietly rescaled to 608x1080, which is not
    a canvas any of the vertical platforms accept, and the user would only find
    out after building the video.

    Both dimensions are forced even because H.264's chroma subsampling requires
    it — an odd width fails the encode outright, which is a confusing way to
    learn that a preset was one pixel too tall.
    """
    cap = settings.video_max_resolution_height
    short_side = min(width, height)
    if short_side > cap:
        scale = cap / short_side
        width = round(width * scale)
        height = round(height * scale)
    return (max(2, width - width % 2), max(2, height - height % 2))


def resolution_label(width: int, height: int) -> str:
    """How a canvas is named in the export dialog: "1080p", "720p".

    The short side again, for the same reason as above.
    """
    return f"{min(width, height)}p"
