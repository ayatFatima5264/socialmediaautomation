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


def build_image_url(
    prompt: str,
    *,
    width: int | None = None,
    height: int | None = None,
    seed: int | None = None,
    model: str | None = None,
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
    if seed is not None:
        params["seed"] = seed
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    return f"{base}/prompt/{quote(prompt)}?{query}"


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
