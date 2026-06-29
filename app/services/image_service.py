"""AI image generation via Pollinations (free, no API key).

Pollinations serves a generated image directly at a GET URL:
    https://image.pollinations.ai/prompt/<prompt>?width=..&height=..&model=..
The URL *is* the image, so it can be handed straight to Instagram, which
fetches media server-side.

`build_image_url` just constructs that URL (instant, no network). `generate`
optionally pings it so callers can surface a clear error early instead of
letting a downstream publish fail.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from app.config import settings

# Instagram's media ingester rejects some encoded punctuation (notably commas)
# in a fetched image URL. The prompt is free text to Pollinations, so we reduce
# it to letters/digits/spaces — same image, URL-safe.
_PROMPT_SANITIZE_RE = re.compile(r"[^A-Za-z0-9 ]+")


class ImageError(Exception):
    """Image generation failed."""


# Aspect ratios offered by the composer -> (width, height) in pixels.
# Short side fixed at 1080 for crisp social media output; all within
# Pollinations' sane bounds. Adding a ratio here makes it available
# end-to-end (no other backend change needed).
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (1080, 1080),    # Square — Instagram/Facebook feed
    "4:5": (1080, 1350),    # Portrait — denser feed real estate
    "9:16": (1080, 1920),   # Story / Reel — vertical full screen
    "16:9": (1920, 1080),   # Landscape — LinkedIn / X / YouTube
    "2:3": (1080, 1620),    # Tall — Pinterest pins
}


def dimensions_for(aspect_ratio: str) -> tuple[int, int]:
    """Map an aspect-ratio string (e.g. "1:1") to (width, height) in pixels."""
    try:
        return ASPECT_RATIOS[aspect_ratio]
    except KeyError as exc:
        allowed = ", ".join(ASPECT_RATIOS)
        raise ImageError(
            f"Unsupported aspect ratio {aspect_ratio!r}. Allowed: {allowed}."
        ) from exc


# Visual style presets -> descriptive keywords folded into the image prompt.
# Adding a style here makes it usable end-to-end with no other change.
IMAGE_STYLES: dict[str, str] = {
    "realistic": "photorealistic, natural lighting, sharp focus, high detail",
    "minimal": "minimalist, clean composition, lots of negative space, simple",
    "illustration": "flat vector illustration, bold clean shapes, vivid colors",
    "3d": "3d render, soft studio lighting, subtle depth of field",
    "cartoon": "playful cartoon style, bold outlines, vibrant colors",
    "watercolor": "soft watercolor painting, gentle washes, artistic texture",
    "anime": "anime style, cel shaded, expressive, crisp linework",
}

#: Allowed image-quality tiers. "hd" asks Pollinations to enhance the prompt.
IMAGE_QUALITIES = ("standard", "hd")


def compose_prompt(
    base: str,
    *,
    style: str | None = None,
    negative: str | None = None,
    prompt_enhancer: bool = False,
) -> str:
    """Fold style, an enhancer hint and negative terms into one prompt string.

    Pollinations has no separate negative-prompt parameter, so "avoid X" terms
    are expressed inline as "without X" — good enough to steer the model away.
    """
    parts: list[str] = [(base or "").strip()]
    if prompt_enhancer:
        parts.append("highly detailed, professional, eye-catching social media visual")
    if style and style in IMAGE_STYLES:
        parts.append(IMAGE_STYLES[style])
    if negative:
        terms = [t.strip() for t in re.split(r"[,\n]+", negative) if t.strip()]
        if terms:
            parts.append("without " + ", ".join(terms))
    return ". ".join(p for p in parts if p)


def build_image_url(
    prompt: str,
    *,
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
    model: str | None = None,
    enhance: bool = False,
) -> str:
    """Build a Pollinations image URL for `prompt` (no network call)."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageError("Image prompt must not be empty.")
    # Drop punctuation that trips Instagram's URL fetcher; collapse whitespace.
    prompt = _PROMPT_SANITIZE_RE.sub(" ", prompt).strip()
    prompt = re.sub(r"\s+", " ", prompt)
    if not prompt:
        raise ImageError("Image prompt has no usable characters.")

    base = settings.pollinations_base.rstrip("/")
    params = {
        "width": width or settings.image_width,
        "height": height or settings.image_height,
        "model": model or settings.image_model,
        "nologo": "true",
    }
    if enhance:
        # Pollinations server-side prompt enrichment — our "HD" quality tier.
        params["enhance"] = "true"
    if seed is not None:
        params["seed"] = seed
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"{base}/prompt/{quote(prompt)}?{query}"


# Common English stopwords stripped when deriving keyword-photo search terms.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "of", "to", "in", "on",
    "our", "your", "new", "this", "that", "about", "from", "into", "you",
}


def _keywords(prompt: str, limit: int = 5) -> str:
    """Reduce a prompt to a few search keywords for keyword-photo fallbacks."""
    words = _PROMPT_SANITIZE_RE.sub(" ", prompt or "").lower().split()
    keep = [w for w in words if len(w) > 2 and w not in _STOPWORDS]
    return ",".join((keep or words)[:limit]) or "abstract"


def build_image_candidates(
    prompt: str,
    *,
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
    enhance: bool = False,
) -> list[str]:
    """Ordered image-source URLs for one image: try each until one renders.

    1. Pollinations (flux)  — best-quality free AI generation
    2. Pollinations (turbo) — faster AI model, separate from flux
    3. LoremFlickr          — a real photo matching the prompt keywords
    4. Picsum               — a stable placeholder photo (always available)

    The first two are AI-generated; the last two are different hosts that won't
    rate-limit, guaranteeing the user always gets a relevant-ish visual.
    """
    w = width or settings.image_width
    h = height or settings.image_height
    lock = abs(seed if seed is not None else 0) % 100000

    candidates = [
        build_image_url(prompt, width=w, height=h, seed=seed, model="flux", enhance=enhance),
        build_image_url(prompt, width=w, height=h, seed=seed, model="turbo", enhance=enhance),
        f"https://loremflickr.com/{w}/{h}/{quote(_keywords(prompt))}?lock={lock}",
        f"https://picsum.photos/seed/{lock + 1}/{w}/{h}",
    ]
    return candidates


async def generate(prompt: str, *, verify: bool = False, **kwargs) -> str:
    """Return an image URL for `prompt`.

    With verify=True, issue a lightweight request so a bad/blocked image fails
    here with a clear message rather than later during publishing.
    """
    url = build_image_url(prompt, **kwargs)
    if verify:
        try:
            async with httpx.AsyncClient(
                timeout=settings.ai_request_timeout, follow_redirects=True
            ) as client:
                # Pollinations generates on GET; a short streamed GET confirms
                # it returns an image without downloading the whole payload.
                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        raise ImageError(f"Image service returned {resp.status_code}.")
                    ctype = resp.headers.get("content-type", "")
                    if not ctype.startswith("image/"):
                        raise ImageError(f"Image service returned non-image ({ctype}).")
        except httpx.HTTPError as exc:
            raise ImageError(f"Image request failed: {exc}") from exc
    return url
