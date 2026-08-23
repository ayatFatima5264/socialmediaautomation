"""Finding and making the picture for each scene.

The visual step of the AI pipeline. Given a scene with a `visual_prompt`, it
produces a real `VideoAsset` in the user's own library and points the scene at
it — so the picture behind a generated video is a file the user owns, can see
in the Media Library, can replace, and can delete.

**Nothing is referenced by remote URL.** A stock result or an AI generation is
*fetched and stored* before the scene points at it. A timeline clip whose
source is somebody else's URL is a video that renders differently next week and
fails to render at all when that host goes down — and the renderer, which pulls
its inputs from object storage, could not use one anyway.

**Three sources, tried in the order that costs least.**

    stock       Openverse and friends, through the existing `search_stock`.
                Real photography, already licensed for use, free.
    ai_image    the existing image provider chain, for a subject no stock
                library has.
    color       a generated card — a gradient the text sits on. Not a
                fallback for a failed search: it is what **animated** mode is
                supposed to look like, and it is also the honest last resort
                when nothing else can be found, because a scene with a card
                behind it is finished-looking and obviously editable, where a
                scene with nothing is a black gap.

**Every provider stays replaceable.** Stock goes through
`image_service.search_stock` and generation through
`image_service.generate_with_fallback` — the same abstractions the post
composer uses. This module chooses *when* to use each; it does not know which
vendor answered.
"""
from __future__ import annotations

import io
import logging
import math

import httpx
from sqlalchemy.orm import Session

from app.models.video_asset import VideoAsset
from app.models.video_project import VideoProject
from app.models.video_scene import VideoScene
from app.services.video import assets as asset_service
from app.services.video import metering

logger = logging.getLogger(__name__)


class VisualError(RuntimeError):
    """A visual could not be produced. The message is user-facing."""


# A scene image is one frame of a short video, not a print asset. Anything
# larger than this is a download the user waits for and a bucket line item, for
# detail that disappears the moment it is scaled to the canvas.
MAX_IMAGE_BYTES = 12 * 1024 * 1024
FETCH_TIMEOUT = httpx.Timeout(20.0, connect=8.0)

# What we are willing to bring in from a third party. A closed list because
# these bytes go into the user's library and then into a filter graph.
FETCHABLE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

_HEADERS = {"User-Agent": "AutoSocialAI/1.0 (+https://autosocial.ai)"}


async def fetch_image(url: str) -> tuple[bytes, str]:
    """Download an image, or raise. Returns `(bytes, content_type)`.

    Guarded on type and size *after* the response arrives rather than trusting
    the URL, because a stock provider's "photo" link can redirect to an HTML
    page and an AI endpoint can return an error document with a 200.
    """
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT, follow_redirects=True, headers=_HEADERS
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.content
            content_type = (
                response.headers.get("content-type", "").split(";")[0].strip().lower()
            )
    except httpx.HTTPError as exc:
        raise VisualError(f"That image could not be downloaded: {exc}") from exc

    if content_type not in FETCHABLE_TYPES:
        raise VisualError(f"{content_type or 'That URL'} is not an image we can use.")
    if not data:
        raise VisualError("That image was empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise VisualError(
            f"That image is {len(data) // (1024 * 1024)} MB, which is larger than "
            f"a scene visual needs to be."
        )

    return data, content_type


# ---------------------------------------------------------------------------
# Generated cards
# ---------------------------------------------------------------------------

# The palettes an animated scene's background is drawn from. Mint first,
# because it is the product's own accent and a generated video should look like
# it came from this app rather than from a stock template.
CARD_PALETTES = (
    ("#0F2F26", "#134E4A"),
    ("#111827", "#1F2937"),
    ("#1E1B4B", "#312E81"),
    ("#3B0764", "#581C87"),
    ("#0C4A6E", "#075985"),
    ("#431407", "#7C2D12"),
)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    body = value.lstrip("#")
    return tuple(int(body[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def make_card(
    *, width: int, height: int, palette_index: int = 0, seed: int = 0
) -> bytes:
    """A gradient background card, as PNG bytes.

    Drawn rather than downloaded, so an animated-mode video needs no network
    and no licence. The gradient runs on a diagonal and the angle shifts with
    the scene index, so consecutive cards in one video are visibly different
    without being random — a video whose backgrounds flicker between unrelated
    colours looks broken, not designed.
    """
    from PIL import Image

    start = _hex_to_rgb(CARD_PALETTES[palette_index % len(CARD_PALETTES)][0])
    end = _hex_to_rgb(CARD_PALETTES[palette_index % len(CARD_PALETTES)][1])

    # Render the gradient small and scale it up: a smooth ramp needs no more
    # resolution than this, and painting 1080x1920 pixels in Python is slow
    # enough to be felt on a twelve-scene generation.
    small_w, small_h = 64, max(1, int(64 * height / max(width, 1)))
    image = Image.new("RGB", (small_w, small_h))
    pixels = image.load()

    angle = math.radians(35 + (seed % 4) * 25)
    dx, dy = math.cos(angle), math.sin(angle)
    span = abs(dx) * small_w + abs(dy) * small_h or 1

    for y in range(small_h):
        for x in range(small_w):
            t = ((x * dx) + (y * dy)) / span
            t = min(1.0, max(0.0, t))
            pixels[x, y] = tuple(
                int(round(start[i] + (end[i] - start[i]) * t)) for i in range(3)
            )

    image = image.resize((width, height), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def attach_card(
    db: Session,
    *,
    project: VideoProject,
    scene: VideoScene,
    palette_index: int = 0,
) -> VideoAsset:
    """Give a scene a generated background card and point it at the asset."""
    data = make_card(
        width=project.width,
        height=project.height,
        palette_index=palette_index,
        seed=scene.position,
    )

    asset = asset_service.store_asset(
        db,
        user_id=project.user_id,
        kind="image",
        data=data,
        content_type="image/png",
        title=f"{(scene.title or 'Scene')[:40]} — background",
        filename=f"scene-{scene.position + 1}-background.png",
        project_id=project.id,
        # Cards for the same canvas and palette are byte-identical, so one
        # object serves every scene that uses it.
        dedupe=True,
        probe=False,
        width=project.width,
        height=project.height,
        meta={"source": "generated_card", "palette": palette_index},
    )

    scene.asset_id = asset.id
    scene.source = "color"
    db.commit()
    return asset


# ---------------------------------------------------------------------------
# Stock and AI
# ---------------------------------------------------------------------------


async def attach_stock(
    db: Session, *, project: VideoProject, scene: VideoScene, query: str | None = None
) -> VideoAsset:
    """Find a stock photo for a scene, store it, and point the scene at it.

    The licence and the credit travel onto the asset's `meta`, so a video built
    from stock can produce its attributions later — the same obligation the
    music library records, for the same reason.
    """
    from app.services import image_service

    search = (query or scene.visual_prompt or scene.title or "").strip()
    if not search:
        raise VisualError("This scene has nothing to search for yet.")

    provider, results = await image_service.search_stock(search, per_page=8)
    if not results:
        raise VisualError(f"No stock photo was found for “{search[:60]}”.")

    last_error: Exception | None = None
    # Walk the results rather than taking the first: a stock hit whose file is
    # a redirect to an HTML page is common enough that one attempt is not a
    # search.
    for candidate in results[:4]:
        try:
            data, content_type = await fetch_image(candidate["url"])
        except VisualError as exc:
            last_error = exc
            continue

        asset = asset_service.store_asset(
            db,
            user_id=project.user_id,
            kind="image",
            data=data,
            content_type=content_type,
            title=f"{(scene.title or 'Scene')[:40]} — stock",
            filename=f"scene-{scene.position + 1}-stock.{FETCHABLE_TYPES[content_type]}",
            project_id=project.id,
            dedupe=True,
            meta={
                "source": "stock",
                "provider": provider,
                "query": search,
                "credit": candidate.get("credit"),
                "source_url": candidate.get("link"),
            },
        )
        scene.asset_id = asset.id
        scene.source = "stock"
        db.commit()
        return asset

    raise VisualError(
        f"Stock photos were found for “{search[:60]}” but none could be "
        f"downloaded: {last_error}"
    )


async def attach_ai_image(
    db: Session, *, project: VideoProject, scene: VideoScene, prompt: str | None = None
) -> VideoAsset:
    """Generate an image for a scene, store it, and point the scene at it."""
    from app.services import image_service

    description = (prompt or scene.visual_prompt or scene.title or "").strip()
    if not description:
        raise VisualError("This scene has no prompt to generate from.")

    try:
        url, model = await image_service.generate_with_fallback(
            description,
            aspect_ratio=project.aspect_ratio,
        )
    except Exception as exc:  # noqa: BLE001 — the provider chain raises broadly
        raise VisualError(f"The image could not be generated: {exc}") from exc

    data, content_type = await fetch_image(url)

    asset = asset_service.store_asset(
        db,
        user_id=project.user_id,
        kind="image",
        data=data,
        content_type=content_type,
        title=f"{(scene.title or 'Scene')[:40]} — generated",
        filename=f"scene-{scene.position + 1}-ai.{FETCHABLE_TYPES[content_type]}",
        project_id=project.id,
        dedupe=True,
        meta={"source": "ai_image", "model": model, "prompt": description},
    )

    scene.asset_id = asset.id
    scene.source = "ai_image"

    # Metered here rather than at the storage layer: `store_asset` already
    # records the bytes, and what costs money for a generated image is the
    # generation, not the kilobytes. One row per picture asked for.
    metering.record(
        db,
        user_id=project.user_id,
        metric="ai_images",
        quantity=1,
        source="scene_visual",
        project_id=project.id,
        meta={"model": model, "prompt": description[:200]},
        commit=False,
    )

    db.commit()
    return asset


# What each visual mode tries, in order. Written as data so the fallback chain
# is readable in one place rather than spread through if-statements — and so
# "why did this scene end up with a card?" has an answer.
MODE_STRATEGIES: dict[str, tuple[str, ...]] = {
    # Real footage first; a generated image for a subject stock does not have;
    # a card so the scene is never empty.
    "natural": ("stock", "ai_image", "color"),
    # Animated scenes are text on a card by definition — there is nothing to
    # search for and nothing to generate.
    "animated": ("color",),
}


async def attach_visual(
    db: Session,
    *,
    project: VideoProject,
    scene: VideoScene,
    strategy: str | None = None,
) -> tuple[VideoAsset, str]:
    """Give a scene a picture, trying each source its mode allows.

    Returns `(asset, source)`. `strategy` forces one source — that is the
    "regenerate as an AI image instead" button — while leaving it out follows
    the chain for the scene's visual mode.

    Never raises for an ordinary miss. The chain ends at a generated card,
    which always succeeds, so this returns a usable scene or the card. It
    raises only if even the card cannot be written, which is a storage failure.
    """
    mode = (scene.settings or {}).get("visual_mode") or "natural"
    chain = (strategy,) if strategy else MODE_STRATEGIES.get(mode, ("stock", "color"))

    errors: list[str] = []
    for source in chain:
        try:
            if source == "stock":
                return await attach_stock(db, project=project, scene=scene), "stock"
            if source == "ai_image":
                return await attach_ai_image(db, project=project, scene=scene), "ai_image"
            if source == "color":
                return (
                    attach_card(
                        db, project=project, scene=scene, palette_index=scene.position
                    ),
                    "color",
                )
        except VisualError as exc:
            errors.append(f"{source}: {exc}")
            logger.info("Scene %s: %s visual failed — %s", scene.id, source, exc)
            db.rollback()

    raise VisualError(
        "No visual could be produced for this scene. " + " ".join(errors[-2:])
    )
