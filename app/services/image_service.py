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

import logging
import re
from urllib.parse import quote

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

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


def named_candidates(
    prompt: str,
    *,
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
    enhance: bool = False,
) -> list[tuple[str, str]]:
    """Ordered (provider, url) pairs for one image — the fallback chain.

    1. Pollinations (flux)  — best-quality free AI generation  [primary]
    2. Pollinations (turbo) — faster AI model, separate from flux  [fallback]
    3. LoremFlickr          — a real photo matching the prompt keywords
    4. Picsum               — a stable placeholder photo (always available)

    The AI models come from settings.image_fallback_models; the last two are
    different hosts that won't rate-limit, guaranteeing a relevant-ish visual.
    """
    w = width or settings.image_width
    h = height or settings.image_height
    lock = abs(seed if seed is not None else 0) % 100000

    out: list[tuple[str, str]] = []
    for model in settings.image_fallback_models:
        out.append((
            f"pollinations-{model}",
            build_image_url(prompt, width=w, height=h, seed=seed, model=model, enhance=enhance),
        ))
    out.append(("loremflickr", f"https://loremflickr.com/{w}/{h}/{quote(_keywords(prompt))}?lock={lock}"))
    out.append(("picsum", f"https://picsum.photos/seed/{lock + 1}/{w}/{h}"))
    return out


def build_image_candidates(
    prompt: str,
    *,
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
    enhance: bool = False,
) -> list[str]:
    """Ordered image-source URLs for one image: try each until one renders.

    The client-side loader tries these in order, so a rate-limited primary
    still yields an image. See `named_candidates` for the provider ordering.
    """
    return [
        url
        for _, url in named_candidates(
            prompt, width=width, height=height, seed=seed, enhance=enhance
        )
    ]


async def _renders_ok(url: str, client: httpx.AsyncClient) -> bool:
    """True if `url` returns a 200 image. Pollinations generates on GET, so a
    streamed GET confirms the image without downloading the whole payload."""
    async with client.stream("GET", url) as resp:
        ctype = resp.headers.get("content-type", "")
        return resp.status_code == 200 and ctype.startswith("image/")


async def generate_with_fallback(
    prompt: str,
    *,
    verify: bool = True,
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
    enhance: bool = False,
) -> tuple[str, str]:
    """Return (image_url, provider), automatically falling back on failure.

    Tries each provider in `named_candidates` in order. With verify=True (the
    default) each candidate is checked to actually render — on an API error,
    timeout, rate-limit or non-image response it moves to the next provider,
    with no user action required. Logs which provider produced the image, and
    raises ImageError only if *every* provider fails.

    With verify=False it returns the primary immediately (fast path); the
    client-side loader still falls back across the returned candidates.
    """
    candidates = named_candidates(
        prompt, width=width, height=height, seed=seed, enhance=enhance
    )
    if not verify:
        provider, url = candidates[0]
        logger.info("Image generated via %s (unverified)", provider)
        return url, provider

    last_error = "no providers configured"
    async with httpx.AsyncClient(
        timeout=settings.ai_request_timeout, follow_redirects=True
    ) as client:
        for provider, url in candidates:
            try:
                if await _renders_ok(url, client):
                    logger.info("Image generated via %s", provider)
                    return url, provider
                last_error = f"{provider} returned a non-image response"
            except httpx.HTTPError as exc:
                last_error = f"{provider} request failed: {exc}"
            logger.warning("Image provider unavailable, falling back: %s", last_error)
    raise ImageError(f"All image providers failed. Last error: {last_error}")


async def generate(prompt: str, *, verify: bool = False, **kwargs) -> str:
    """Return an image URL for `prompt` (backward-compatible thin wrapper).

    Routes through the provider fallback chain, so with verify=True a failing
    primary transparently falls back instead of erroring.
    """
    kwargs.pop("model", None)  # the chain selects models itself
    url, _ = await generate_with_fallback(prompt, verify=verify, **kwargs)
    return url


# ---------------------------------------------------------------------------
# Free stock-image search — an alternative to AI generation. Keyless Openverse
# by default; upgrades to Pexels / Pixabay / Unsplash automatically when a key
# is configured. Returns a normalized list of {url, thumb, credit, source, link}.
# ---------------------------------------------------------------------------
def _resolve_stock_provider() -> str:
    provider = (settings.stock_provider or "auto").lower()
    if provider != "auto":
        return provider
    if settings.pexels_api_key:
        return "pexels"
    if settings.pixabay_api_key:
        return "pixabay"
    if settings.unsplash_access_key:
        return "unsplash"
    return "openverse"


async def _search_openverse(client: httpx.AsyncClient, query: str, per_page: int) -> list[dict]:
    r = await client.get(
        f"{settings.openverse_base.rstrip('/')}/v1/images/",
        params={
            "q": query,
            "page_size": per_page,
            "license_type": "commercial",  # safe for social use
            "mature": "false",
        },
        headers={"User-Agent": "AutoSocialAI/1.0 (+https://autosocial.ai)"},
    )
    r.raise_for_status()
    items = r.json().get("results", []) or []
    out: list[dict] = []
    for it in items:
        url = it.get("url")
        if not url:
            continue
        out.append({
            "url": url,
            "thumb": it.get("thumbnail") or url,
            "credit": it.get("creator") or it.get("source") or "Openverse",
            "source": "openverse",
            "link": it.get("foreign_landing_url"),
        })
    return out


async def _search_pexels(client: httpx.AsyncClient, query: str, per_page: int) -> list[dict]:
    r = await client.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": per_page},
        headers={"Authorization": settings.pexels_api_key or ""},
    )
    r.raise_for_status()
    out: list[dict] = []
    for it in r.json().get("photos", []) or []:
        src = it.get("src", {}) or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            continue
        out.append({
            "url": url,
            "thumb": src.get("medium") or src.get("small") or url,
            "credit": it.get("photographer") or "Pexels",
            "source": "pexels",
            "link": it.get("url"),
        })
    return out


async def _search_pixabay(client: httpx.AsyncClient, query: str, per_page: int) -> list[dict]:
    r = await client.get(
        "https://pixabay.com/api/",
        params={
            "key": settings.pixabay_api_key or "",
            "q": query,
            "per_page": max(3, per_page),  # Pixabay requires per_page >= 3
            "image_type": "photo",
            "safesearch": "true",
        },
    )
    r.raise_for_status()
    out: list[dict] = []
    for it in r.json().get("hits", []) or []:
        url = it.get("largeImageURL") or it.get("webformatURL")
        if not url:
            continue
        out.append({
            "url": url,
            "thumb": it.get("webformatURL") or it.get("previewURL") or url,
            "credit": it.get("user") or "Pixabay",
            "source": "pixabay",
            "link": it.get("pageURL"),
        })
    return out


async def _search_unsplash(client: httpx.AsyncClient, query: str, per_page: int) -> list[dict]:
    r = await client.get(
        "https://api.unsplash.com/search/photos",
        params={"query": query, "per_page": per_page},
        headers={"Authorization": f"Client-ID {settings.unsplash_access_key or ''}"},
    )
    r.raise_for_status()
    out: list[dict] = []
    for it in r.json().get("results", []) or []:
        urls = it.get("urls", {}) or {}
        url = urls.get("regular") or urls.get("full") or urls.get("raw")
        if not url:
            continue
        out.append({
            "url": url,
            "thumb": urls.get("small") or urls.get("thumb") or url,
            "credit": (it.get("user", {}) or {}).get("name") or "Unsplash",
            "source": "unsplash",
            "link": (it.get("links", {}) or {}).get("html"),
        })
    return out


async def search_stock(query: str, *, per_page: int = 12) -> tuple[str, list[dict]]:
    """Search a free stock-photo provider. Returns (provider, results).

    Uses the configured provider (or Openverse when no key is set). Raises
    ImageError on an empty query or a provider/network failure.
    """
    query = (query or "").strip()
    if not query:
        raise ImageError("Search query must not be empty.")
    per_page = max(1, min(per_page, 30))
    provider = _resolve_stock_provider()
    searchers = {
        "openverse": _search_openverse,
        "pexels": _search_pexels,
        "pixabay": _search_pixabay,
        "unsplash": _search_unsplash,
    }
    searcher = searchers.get(provider, _search_openverse)
    try:
        async with httpx.AsyncClient(
            timeout=settings.ai_request_timeout, follow_redirects=True
        ) as client:
            results = await searcher(client, query, per_page)
    except httpx.HTTPError as exc:
        raise ImageError(f"Stock image search failed ({provider}): {exc}") from exc
    logger.info("Stock search via %s for %r -> %d results", provider, query, len(results))
    return provider, results
