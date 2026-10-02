"""Re-flow one banner into every standard display size (BUG-07).

The Banner Generator's right rail promises the banner re-flowed into each
network's display sizes, and the page's own footer called that a compositing
step "still to come" while the Download button sat `disabled` behind a tooltip
claiming a condition that never unlocked. This is that step.

A generated banner comes back at whichever ratio the image model was asked for
(16:9, 1:1 or 9:16 — see RATIO_FOR_SIZE in BannerGenerator.jsx). Turning that
into a 728x90 leaderboard or a 160x600 skyscraper is geometry, not generation:
scale to cover the target, crop the overflow, and pad anything left over.

Two rules that make the output usable rather than merely correct:

- **No stretching.** Every fit is a uniform scale, so a square banner does not
  come out as a squashed rectangle. The subject is cropped, never distorted.
- **No bare edges.** A 16:9 source on a 160x600 target leaves most of the frame
  empty, so the background is extended with a blurred, zoomed copy of the image
  itself. The result reads as a designed vertical ad instead of a photograph
  floating in a black box.

The headline and CTA are drawn on top, because a display ad without its text is
a background. Text is drawn with Pillow's bundled font and fitted to the frame
by measuring and shrinking, so a long headline wraps rather than overflowing.
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import settings

logger = logging.getLogger(__name__)

#: Largest source image fetched and held in memory. A display ad is 1200px on
#: its long edge; anything vastly larger is a mistake, not a high-resolution
#: original, and decoding it costs memory for no visible gain.
MAX_SOURCE_BYTES = 12 * 1024 * 1024

#: JPEG below this and the composited PNG is upscaled from mush.
MIN_SOURCE_EDGE = 400


class BannerExportError(Exception):
    """A banner could not be re-flowed into the requested sizes."""


@dataclass(frozen=True)
class ExportSize:
    """One output size, and where it came from in the rail."""

    width: int
    height: int
    network: str
    #: The name shown on the button, e.g. "Google Ads · 728 x 90".
    label: str

    @property
    def slug(self) -> str:
        return f"{self.width}x{self.height}"


#: The rail's contents, as data. Mirrors `BANNER_EXPORT_SETS` in
#: frontend/src/lib/ads/constants.js — the same list written as pixels the
#: server can composite to, so the rail and the export cannot disagree about
#: which sizes exist.
EXPORT_SIZES: tuple[ExportSize, ...] = (
    ExportSize(1200, 628, "Facebook", "Facebook · 1200 x 628"),
    ExportSize(1080, 1080, "Facebook", "Facebook · 1080 x 1080"),
    ExportSize(1080, 1920, "Facebook", "Facebook · 1080 x 1920"),
    ExportSize(728, 90, "Google Ads", "Google Ads · 728 x 90"),
    ExportSize(300, 250, "Google Ads", "Google Ads · 300 x 250"),
    ExportSize(160, 600, "Google Ads", "Google Ads · 160 x 600"),
    ExportSize(1200, 627, "LinkedIn", "LinkedIn · 1200 x 627"),
    ExportSize(1000, 1500, "Pinterest", "Pinterest · 1000 x 1500"),
)

#: Distinct pixel sizes across every network — 1080x1080 is offered by both
#: Facebook and LinkedIn, and compositing it twice would be wasted work.
UNIQUE_SIZES: tuple[ExportSize, ...] = tuple(
    {s.slug: s for s in EXPORT_SIZES}.values()
)

#: Largest export accepted in one call, so a crafted request cannot ask the
#: server to composite the same image a thousand times.
MAX_EXPORT_SIZES = 20


def parse_size(value: str) -> ExportSize:
    """Resolve a rail label to an ExportSize.

    The rail writes these with a Unicode multiplication sign ("1200 × 628"), so
    `×` and a capital `X` are folded to the ASCII `x` the slugs use. Without
    that fold the browser sends `1200×628` and every request is refused as an
    unsupported size.

    Raises BannerExportError for anything not on the rail, so a caller cannot
    ask for an arbitrary canvas.
    """
    key = (
        re.sub(r"\s+", "", str(value or ""))
        .lower()
        .replace("×", "x")  # ×
        .replace("✕", "x")  # ✕
    )
    for size in EXPORT_SIZES:
        if size.slug == key:
            return size
    allowed = ", ".join(s.slug for s in EXPORT_SIZES)
    raise BannerExportError(f"Unsupported banner size {value!r}. Available: {allowed}.")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


async def fetch_image(url: str) -> bytes:
    """Download the generated banner. Raises BannerExportError on any failure."""
    if not url or not str(url).strip():
        raise BannerExportError("No banner image to export.")

    try:
        async with httpx.AsyncClient(
            timeout=settings.ai_request_timeout, follow_redirects=True
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise BannerExportError(
                        f"The banner image could not be fetched (HTTP {resp.status_code})."
                    )
                ctype = resp.headers.get("content-type", "")
                if ctype and not ctype.startswith("image/"):
                    raise BannerExportError(
                        "That URL did not return an image, so there is nothing to re-flow."
                    )

                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_SOURCE_BYTES:
                        raise BannerExportError(
                            "The banner image is too large to export. Try a smaller one."
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
    except httpx.HTTPError as exc:
        raise BannerExportError(f"The banner image could not be fetched: {exc}") from exc

    if not data:
        raise BannerExportError("The banner image came back empty.")
    return data


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:  # Pillow raises a wide range of decode errors
        raise BannerExportError("That file is not a readable image.") from exc

    image = image.convert("RGB")
    if min(image.size) < MIN_SOURCE_EDGE:
        raise BannerExportError(
            f"The banner is only {image.width}x{image.height}px, which is too small to "
            f"re-flow into display sizes without going blurry. Generate it again at a "
            f"larger size."
        )
    return image


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _cover(source: Image.Image, width: int, height: int) -> Image.Image:
    """Scale uniformly to COVER the target, then centre-crop the overflow.

    Uniform scale is what keeps the aspect ratio: `min` of the two ratios is the
    largest scale at which the source still covers the frame.
    """
    scale = max(width / source.width, height / source.height)
    scaled = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.LANCZOS,
    )
    left = max(0, (scaled.width - width) // 2)
    top = max(0, (scaled.height - height) // 2)
    return scaled.crop((left, top, left + width, top + height))


def _blurred_backdrop(source: Image.Image, width: int, height: int) -> Image.Image:
    """A zoomed, blurred copy of the image, filling any frame it under-covers.

    Used for extreme ratios (a 16:9 banner on a 160x600 skyscraper) where the
    cover-crop would otherwise throw away most of the picture.
    """
    scale = max(width / source.width, height / source.height) * 1.15
    big = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.LANCZOS,
    )
    # Radius scales with the enlarged image, so a large target is blurred more
    # than a small one. Read from `big` after the assignment, not within it.
    blurred = big.filter(ImageFilter.GaussianBlur(radius=max(8, min(big.size) // 40)))
    left = max(0, (blurred.width - width) // 2)
    top = max(0, (blurred.height - height) // 2)
    return blurred.crop((left, top, left + width, top + height))


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

#: Pillow ships DejaVuSans, so text rendering works with no font dependency to
#: install and no path to get wrong on a different machine.
_FONT_CANDIDATES = (
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Greedy word wrap to `max_width`."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    line = words[0]
    for word in words[1:]:
        candidate = f"{line} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            line = candidate
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    *,
    bold: bool,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """Largest size at which `text` wraps inside the box, then returns it.

    Binary-searching the point size beats a fixed multiplier because a long
    headline and a two-word one need very different sizes to fill the same box.
    """
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    low, high = 8, max(10, int(max_height))
    best: tuple[list[str], ImageFont.FreeTypeFont] = ([], _font(10))

    while low <= high:
        mid = (low + high) // 2
        try:
            font = ImageFont.truetype(name, mid)
        except OSError:
            font = _font(mid)
        lines = _wrap(draw, text, font, max_width)
        line_height = (draw.textbbox((0, 0), "Ag", font=font)[3]) or mid
        if lines and len(lines) * line_height <= max_height:
            best = (lines, font)
            low = mid + 1
        else:
            high = mid - 1

    return best


def _draw_block(
    image: Image.Image,
    text: str,
    *,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int] = (255, 255, 255),
    align: str = "left",
) -> None:
    """Draw wrapped text inside `box`, with a shadow so it survives a busy image."""
    if not text.strip():
        return

    draw = ImageDraw.Draw(image)
    left, top, right, bottom = box
    max_width = right - left
    max_height = bottom - top
    if max_width < 20 or max_height < 12:
        return

    lines, font = _fit_text(draw, text, max_width, max_height, bold=True)
    if not lines:
        return

    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] or 12
    y = bottom - len(lines) * line_height
    for line in lines:
        x = left if align == "left" else left + (max_width - draw.textlength(line, font=font)) / 2
        # A dark offset copy one pixel down-right: legible on a white banner and
        # on a black one, without a translucent plate over the artwork.
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def compose(
    source: Image.Image,
    size: ExportSize,
    *,
    headline: str = "",
    subheadline: str = "",
    cta: str = "",
) -> Image.Image:
    """Re-flow `source` into `size`, with the banner's text drawn on top."""
    frame = _cover(source, size.width, size.height)

    # On an extreme ratio change, cover-crop alone can leave the subject
    # unreadable, so the frame is composed over a backdrop of the same image.
    source_ratio = source.width / source.height
    target_ratio = size.width / size.height
    if max(source_ratio, target_ratio) / min(source_ratio, target_ratio) > 2.0:
        frame = Image.blend(
            _blurred_backdrop(source, size.width, size.height), frame, 0.65
        )

    draw = ImageDraw.Draw(frame)
    # A soft gradient behind the text, so a headline over a light photo is
    # still readable. Drawn as bands rather than a per-pixel alpha ramp: an
    # RGBA overlay per line at this size costs more than it is worth.
    text_top = int(size.height * 0.5)
    bands = 26
    for i in range(bands):
        t = i / bands
        alpha = int(150 * (t**1.5))
        y0 = text_top + int((size.height - text_top) * (i / bands))
        y1 = text_top + int((size.height - text_top) * ((i + 1) / bands))
        draw.rectangle([0, y0, size.width, y1], fill=(0, 0, 0, alpha))

    margin = max(12, int(min(size.width, size.height) * 0.06))
    bottom = size.height - margin
    cta_height = max(18, int(size.height * 0.09)) if cta else 0

    _draw_block(
        frame,
        headline,
        box=(margin, int(size.height * 0.5), size.width - margin, bottom - cta_height),
    )

    if subheadline:
        sub_top = int(size.height * 0.72)
        _draw_block(
            frame,
            subheadline,
            box=(margin, sub_top, size.width - margin, bottom - cta_height - 4),
            fill=(235, 235, 235),
        )

    if cta:
        _draw_block(
            frame,
            cta,
            box=(margin, bottom - cta_height, size.width - margin, bottom),
            fill=(255, 255, 255),
        )

    return frame


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


async def export_sizes(
    image_url: str,
    sizes: list[str],
    *,
    headline: str = "",
    subheadline: str = "",
    cta: str = "",
) -> list[dict]:
    """Fetch `image_url` once and composite it into each requested size.

    Returns one entry per requested size, in the order asked for, with the PNG
    bytes inline. The source is fetched a single time even for nine outputs.
    """
    if not sizes:
        raise BannerExportError("Choose at least one size to export.")
    if len(sizes) > MAX_EXPORT_SIZES:
        raise BannerExportError(f"At most {MAX_EXPORT_SIZES} sizes can be exported at once.")

    # Resolved before the fetch so a bad label fails without spending a download.
    resolved = [parse_size(s) for s in sizes]

    data = await fetch_image(image_url)
    source = _open(data)

    out: list[dict] = []
    for size in resolved:
        try:
            frame = compose(
                source, size, headline=headline, subheadline=subheadline, cta=cta
            )
            png = to_png(frame)
        except BannerExportError:
            raise
        except Exception as exc:  # Pillow can fail on an odd mode or palette
            raise BannerExportError(
                f"{size.label} could not be produced: {exc}"
            ) from exc

        out.append({
            "size": size.slug,
            "label": size.label,
            "network": size.network,
            "width": size.width,
            "height": size.height,
            "filename": f"banner-{size.slug}.png",
            "content_type": "image/png",
            "bytes": png,
        })
        logger.info("Composited banner into %s (%d bytes)", size.slug, len(png))

    return out
