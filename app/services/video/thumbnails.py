"""Thumbnail Studio — a composition document, and one renderer for it.

The same principle the timeline editor is built on, applied to a still: there
is **one design document and one function that turns it into pixels**. The
preview endpoint and the download endpoint call that same function, so what the
user is looking at is the file they get. A preview drawn in the browser with
CSS and a download rendered on the server is two implementations of the same
picture, and they diverge the first time either is touched.

    design ──▶ render() ──▶ PNG/JPG      (preview and download, same call)
       │
       ├── background   a colour, a gradient, or an image from the library
       ├── text layers  headline and sub-headline, with outline and shadow
       └── logo         from the Brand Kit, or any asset

**A design is data the user owns.** Every field — the words, the font, the
size, the colour, the position of each layer — is on the document and editable.
Templates produce a design; variations produce several. Nothing is baked.

**Rendering is Pillow, not ffmpeg.** A thumbnail is one frame with text on it;
the video compositor's filter graph is the wrong tool and would be far slower.
The font resolution is shared with the compositor, so a face that renders in a
video renders here too.
"""
from __future__ import annotations

import io
import logging
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)


class ThumbnailError(RuntimeError):
    """A thumbnail could not be produced. The message is user-facing."""


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------
# The canvases a thumbnail is actually made for. YouTube's 1280x720 is the one
# people mean by "thumbnail"; the rest are the covers and posters the same
# artwork gets reused as, which is why they are here rather than in the video
# preset list (a thumbnail is not a video canvas).

FORMATS: tuple[dict, ...] = (
    {
        "key": "youtube",
        "label": "YouTube",
        "width": 1280,
        "height": 720,
        "description": "16:9 — the standard video thumbnail.",
    },
    {
        "key": "youtube_shorts",
        "label": "Shorts / Reels / TikTok",
        "width": 1080,
        "height": 1920,
        "description": "9:16 — a vertical cover.",
    },
    {
        "key": "instagram_post",
        "label": "Instagram Post",
        "width": 1080,
        "height": 1080,
        "description": "1:1 — square feed post.",
    },
    {
        "key": "instagram_portrait",
        "label": "Instagram Portrait",
        "width": 1080,
        "height": 1350,
        "description": "4:5 — the tallest the feed allows.",
    },
    {
        "key": "facebook",
        "label": "Facebook / LinkedIn",
        "width": 1200,
        "height": 630,
        "description": "1.91:1 — link preview card.",
    },
)

FORMATS_BY_KEY = {entry["key"]: entry for entry in FORMATS}
DEFAULT_FORMAT = "youtube"

# Where a layer sits, as one of nine anchors. Nine rather than free-form
# coordinates as the *primary* control because "bottom left" is what somebody
# means, and the fine offset is a nudge on top of it — which also survives the
# design being re-rendered at another format.
ANCHORS = (
    "top-left", "top-center", "top-right",
    "middle-left", "middle-center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
)

BACKGROUND_KINDS = ("color", "gradient", "image")

# Presets the palette picker offers, and what a variation cycles through.
PALETTES: tuple[dict, ...] = (
    {"key": "mint", "label": "Mint", "colors": ["#0F2F26", "#134E4A"], "accent": "#34D399"},
    {"key": "midnight", "label": "Midnight", "colors": ["#0B1220", "#1F2937"], "accent": "#60A5FA"},
    {"key": "violet", "label": "Violet", "colors": ["#2E1065", "#4C1D95"], "accent": "#C4B5FD"},
    {"key": "ember", "label": "Ember", "colors": ["#431407", "#7C2D12"], "accent": "#FDBA74"},
    {"key": "ocean", "label": "Ocean", "colors": ["#082F49", "#0C4A6E"], "accent": "#7DD3FC"},
    {"key": "rose", "label": "Rose", "colors": ["#4C0519", "#881337"], "accent": "#FDA4AF"},
)

PALETTES_BY_KEY = {entry["key"]: entry for entry in PALETTES}


# ---------------------------------------------------------------------------
# Colour handling
# ---------------------------------------------------------------------------


def parse_color(value: str | None, fallback: tuple = (0, 0, 0, 255)) -> tuple:
    """`#rgb`, `#rrggbb`, `#rrggbbaa` or "transparent" as an RGBA tuple.

    Validated rather than passed through: these values arrive from a client and
    end up in a drawing call, and Pillow raising on a malformed colour would
    turn a typo into a 500.
    """
    text = str(value or "").strip()
    if text.lower() == "transparent":
        return (0, 0, 0, 0)
    if not text.startswith("#"):
        return fallback

    body = text[1:]
    if len(body) == 3:
        body = "".join(character * 2 for character in body)
    if len(body) not in (6, 8) or any(
        character not in "0123456789abcdefABCDEF" for character in body
    ):
        return fallback

    red, green, blue = (int(body[i : i + 2], 16) for i in (0, 2, 4))
    alpha = int(body[6:8], 16) if len(body) == 8 else 255
    return (red, green, blue, alpha)


# ---------------------------------------------------------------------------
# The design document
# ---------------------------------------------------------------------------

TEXT_DEFAULTS: dict = {
    "id": "",
    "type": "text",
    "text": "",
    "font_family": "Inter",
    "font_size": 0.12,        # a fraction of the canvas height — see below
    "font_weight": 800,
    "color": "#FFFFFF",
    "outline": "#000000",
    "outline_width": 0.006,   # also a fraction, so it scales with the format
    "shadow": True,
    "background": "transparent",
    "anchor": "middle-center",
    "offset_x": 0.0,
    "offset_y": 0.0,
    "align": "center",
    "uppercase": False,
    "max_width": 0.86,        # fraction of the canvas the text may occupy
    "line_spacing": 1.12,
    "rotation": 0.0,
}

LOGO_DEFAULTS: dict = {
    "id": "logo",
    "type": "logo",
    "asset_id": None,
    "url": None,
    "anchor": "bottom-right",
    "offset_x": 0.0,
    "offset_y": 0.0,
    "size": 0.14,             # fraction of the canvas's short side
    "opacity": 1.0,
}


def _number(value, fallback: float, low: float, high: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    if result != result:
        return fallback
    return max(low, min(result, high))


def _boolean(value, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return fallback if value is None else bool(value)


def _choice(value, allowed: tuple[str, ...], fallback: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else fallback


def normalize_layer(raw: dict, index: int = 0) -> dict:
    """One layer, complete and in range.

    **Sizes are fractions of the canvas, never pixels.** A design made for
    YouTube's 1280x720 has to render at 1080x1920 without the headline becoming
    a footnote, and a font size in points cannot do that. Everything the
    renderer multiplies by a canvas dimension is stored as a proportion of it.
    """
    kind = _choice(raw.get("type"), ("text", "logo"), "text")
    defaults = LOGO_DEFAULTS if kind == "logo" else TEXT_DEFAULTS
    layer = {**defaults, **{k: v for k, v in raw.items() if k in defaults}}

    layer["id"] = str(layer.get("id") or "").strip() or f"{kind}-{index + 1}"
    layer["type"] = kind
    layer["anchor"] = _choice(layer["anchor"], ANCHORS, defaults["anchor"])
    layer["offset_x"] = _number(layer["offset_x"], 0.0, -1.0, 1.0)
    layer["offset_y"] = _number(layer["offset_y"], 0.0, -1.0, 1.0)

    if kind == "logo":
        layer["size"] = _number(layer["size"], 0.14, 0.02, 0.6)
        layer["opacity"] = _number(layer["opacity"], 1.0, 0.0, 1.0)
        try:
            layer["asset_id"] = int(layer["asset_id"]) if layer["asset_id"] else None
        except (TypeError, ValueError):
            layer["asset_id"] = None
        return layer

    text = str(layer.get("text") or "")
    layer["text"] = "".join(
        character for character in text if character == "\n" or character >= " "
    )[:200]
    layer["font_family"] = str(layer.get("font_family") or "Inter").strip()[:60] or "Inter"
    layer["font_size"] = _number(layer["font_size"], 0.12, 0.02, 0.5)
    layer["font_weight"] = int(_number(layer["font_weight"], 800, 100, 900))
    layer["color"] = _hex(layer["color"], "#FFFFFF")
    layer["outline"] = _hex(layer["outline"], "#000000")
    layer["outline_width"] = _number(layer["outline_width"], 0.006, 0.0, 0.05)
    layer["background"] = _hex(layer["background"], "transparent")
    layer["shadow"] = _boolean(layer["shadow"], True)
    layer["align"] = _choice(layer["align"], ("left", "center", "right"), "center")
    layer["uppercase"] = _boolean(layer["uppercase"])
    layer["max_width"] = _number(layer["max_width"], 0.86, 0.1, 1.0)
    layer["line_spacing"] = _number(layer["line_spacing"], 1.12, 0.8, 2.0)
    layer["rotation"] = _number(layer["rotation"], 0.0, -45.0, 45.0)
    return layer


def _hex(value, fallback: str) -> str:
    """Keep a colour as the string the client sent, once it is known valid."""
    text = str(value or "").strip()
    if text.lower() == "transparent":
        return "transparent"
    parsed = parse_color(text, None)
    return text.upper() if parsed is not None else fallback


def normalize(design: dict | None) -> dict:
    """A complete design document, whatever came in."""
    source = design if isinstance(design, dict) else {}

    format_key = _choice(
        source.get("format"), tuple(FORMATS_BY_KEY), DEFAULT_FORMAT
    )
    spec = FORMATS_BY_KEY[format_key]

    background = source.get("background")
    background = background if isinstance(background, dict) else {}
    kind = _choice(background.get("kind"), BACKGROUND_KINDS, "gradient")

    palette_key = _choice(
        background.get("palette"), tuple(PALETTES_BY_KEY), "mint"
    )
    palette = PALETTES_BY_KEY[palette_key]

    colors = background.get("colors")
    if not isinstance(colors, list) or not colors:
        colors = list(palette["colors"])
    colors = [_hex(value, "#000000") for value in colors][:2]
    if len(colors) == 1:
        colors.append(colors[0])

    try:
        asset_id = int(background.get("asset_id")) if background.get("asset_id") else None
    except (TypeError, ValueError):
        asset_id = None

    layers = source.get("layers")
    layers = layers if isinstance(layers, list) else []

    return {
        "version": 1,
        "format": format_key,
        "width": spec["width"],
        "height": spec["height"],
        "background": {
            "kind": kind,
            "palette": palette_key,
            "colors": colors,
            "asset_id": asset_id,
            # How much to darken an image background so text stays readable.
            # Not a style flourish: white text on an arbitrary photo is
            # unreadable about half the time, and this is the fix that does not
            # require the user to notice.
            "scrim": _number(background.get("scrim"), 0.35, 0.0, 0.9),
            "blur": _number(background.get("blur"), 0.0, 0.0, 1.0),
            "angle": _number(background.get("angle"), 35.0, 0.0, 360.0),
        },
        "layers": [
            normalize_layer(layer, index)
            for index, layer in enumerate(layers)
            if isinstance(layer, dict)
        ],
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _font(family: str, weight: int, size: int) -> ImageFont.FreeTypeFont:
    """A Pillow font for a family at a size.

    Resolution is shared with the video compositor, so a face that renders in a
    video renders on its thumbnail. Falls back to Pillow's built-in bitmap font
    only if the machine has no usable TTF at all — the text will look wrong,
    but a thumbnail with ugly text beats a 500.
    """
    from app.services.video.compositor import _find_font_file

    path = _find_font_file(family)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:  # pragma: no cover — a corrupt font file
            logger.warning("Could not load font %s", path)
    return ImageFont.load_default()


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """Break text to fit a width, honouring the newlines the user typed.

    Explicit newlines are respected first and never merged — somebody who put a
    line break in a headline meant it — and each of those lines is then wrapped
    if it is still too wide.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _anchor_position(
    anchor: str, box: tuple[int, int], canvas: tuple[int, int], margin: int
) -> tuple[int, int]:
    """The top-left corner for a box of this size at this anchor."""
    width, height = box
    canvas_w, canvas_h = canvas

    vertical, horizontal = anchor.split("-")

    if horizontal == "left":
        x = margin
    elif horizontal == "right":
        x = canvas_w - width - margin
    else:
        x = (canvas_w - width) // 2

    if vertical == "top":
        y = margin
    elif vertical == "bottom":
        y = canvas_h - height - margin
    else:
        y = (canvas_h - height) // 2

    return x, y


def _gradient(size: tuple[int, int], colors: list[str], angle: float) -> Image.Image:
    """A two-stop linear gradient, drawn small and scaled up.

    Painting every pixel of a 1280x720 canvas in Python is slow enough to be
    felt; a smooth ramp carries no detail that survives downsampling anyway.
    """
    start = parse_color(colors[0], (0, 0, 0, 255))
    end = parse_color(colors[-1], (32, 32, 32, 255))

    small_w, small_h = 96, max(1, int(96 * size[1] / max(size[0], 1)))
    image = Image.new("RGB", (small_w, small_h))
    pixels = image.load()

    radians = math.radians(angle)
    dx, dy = math.cos(radians), math.sin(radians)
    span = abs(dx) * small_w + abs(dy) * small_h or 1

    for y in range(small_h):
        for x in range(small_w):
            t = min(1.0, max(0.0, ((x * dx) + (y * dy)) / span))
            pixels[x, y] = tuple(
                int(round(start[i] + (end[i] - start[i]) * t)) for i in range(3)
            )

    return image.resize(size, Image.LANCZOS)


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale and centre-crop an image to fill a canvas exactly.

    Cover rather than fit: a thumbnail with letterbox bars is a thumbnail that
    looks like a mistake.
    """
    target_w, target_h = size
    factor = max(target_w / image.width, target_h / image.height)
    scaled = image.resize(
        (max(1, int(image.width * factor)), max(1, int(image.height * factor))),
        Image.LANCZOS,
    )
    left = (scaled.width - target_w) // 2
    top = (scaled.height - target_h) // 2
    return scaled.crop((left, top, left + target_w, top + target_h))


def render(
    design: dict,
    *,
    background_image: bytes | None = None,
    logo_image: bytes | None = None,
    fmt: str = "png",
    scale: float = 1.0,
) -> bytes:
    """Draw a design. **The one function preview and download both call.**

    `background_image` and `logo_image` are passed in as bytes rather than
    fetched here, so this stays a pure function of its inputs — testable
    without a database and reusable from anywhere that can supply the files.

    `scale` renders at a fraction of full size for a fast preview. The
    composition is identical because every dimension in the document is a
    proportion; only the pixel count changes.
    """
    document = normalize(design)
    width = max(16, int(document["width"] * scale))
    height = max(16, int(document["height"] * scale))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))

    background = document["background"]

    # ---- background -----------------------------------------------------
    if background["kind"] == "image" and background_image:
        try:
            source = Image.open(io.BytesIO(background_image)).convert("RGBA")
        except Exception as exc:  # noqa: BLE001 — Pillow raises broadly
            raise ThumbnailError("That background image could not be read.") from exc
        layer = _cover(source, (width, height))
        if background["blur"] > 0:
            layer = layer.filter(
                ImageFilter.GaussianBlur(radius=background["blur"] * 0.03 * width)
            )
        canvas.paste(layer, (0, 0))

        # The scrim. See the note on the field.
        if background["scrim"] > 0:
            shade = Image.new(
                "RGBA", (width, height), (0, 0, 0, int(255 * background["scrim"]))
            )
            canvas = Image.alpha_composite(canvas, shade)
    elif background["kind"] == "color":
        canvas = Image.new(
            "RGBA", (width, height), parse_color(background["colors"][0])
        )
    else:
        canvas.paste(
            _gradient((width, height), background["colors"], background["angle"]), (0, 0)
        )

    # ---- layers ---------------------------------------------------------
    margin = int(min(width, height) * 0.055)

    for layer in document["layers"]:
        if layer["type"] == "logo":
            if logo_image and layer.get("_is_active", True):
                canvas = _draw_logo(canvas, layer, logo_image, margin)
            continue
        canvas = _draw_text(canvas, layer, (width, height), margin)

    # ---- encode ---------------------------------------------------------
    buffer = io.BytesIO()
    if fmt == "jpg":
        # JPEG has no alpha; flattening onto black rather than letting Pillow
        # guess keeps a transparent-background design predictable.
        flat = Image.new("RGB", canvas.size, (0, 0, 0))
        flat.paste(canvas, mask=canvas.split()[3])
        flat.save(buffer, format="JPEG", quality=90, optimize=True)
    else:
        canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _draw_text(
    canvas: Image.Image, layer: dict, size: tuple[int, int], margin: int
) -> Image.Image:
    """Draw one text layer onto the canvas."""
    content = layer["text"].upper() if layer["uppercase"] else layer["text"]
    if not content.strip():
        return canvas

    width, height = size

    # Sized against the **short side**, not the height. A fraction of the
    # height is the same number as the width at 16:9, so it looks right there
    # and then triples on a 9:16 canvas — 0.11 of 1920 is 211px of type across
    # a frame only 1080 wide, which overflows the moment a word is long. The
    # short side is the readable dimension in both orientations, which is the
    # same reasoning `storyboard._text_size` uses for on-screen video text.
    short_side = min(width, height)
    font_size = max(8, int(layer["font_size"] * short_side))
    font = _font(layer["font_family"], layer["font_weight"], font_size)

    scratch = ImageDraw.Draw(canvas)
    max_width = int(width * layer["max_width"])
    lines = _wrap(scratch, content, font, max_width)

    # A single word can be wider than the frame, and there is nowhere to break
    # it — "REPURPOSE" at a headline size on a vertical canvas runs off both
    # edges. Shrink until the longest line fits rather than letting it bleed,
    # because a headline with its ends cut off is not a thumbnail.
    while font_size > 8 and lines:
        widest = max(scratch.textlength(line, font=font) for line in lines)
        if widest <= max_width:
            break
        font_size = int(font_size * 0.92)
        font = _font(layer["font_family"], layer["font_weight"], font_size)
        lines = _wrap(scratch, content, font, max_width)

    line_height = int(font_size * layer["line_spacing"])
    text_width = max(
        (int(scratch.textlength(line, font=font)) for line in lines), default=0
    )
    block = (min(text_width, max_width), line_height * len(lines))

    # Drawn on its own transparent layer so rotation and the box do not smear
    # what is underneath.
    pad = int(font_size * 0.5)
    tile = Image.new(
        "RGBA", (block[0] + pad * 2, block[1] + pad * 2), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(tile)

    if layer["background"] != "transparent":
        draw.rounded_rectangle(
            (0, 0, tile.width - 1, tile.height - 1),
            radius=int(font_size * 0.22),
            fill=parse_color(layer["background"]),
        )

    outline_width = int(layer["outline_width"] * height)
    fill = parse_color(layer["color"], (255, 255, 255, 255))
    stroke = parse_color(layer["outline"], (0, 0, 0, 255))

    for index, line in enumerate(lines):
        line_width = int(draw.textlength(line, font=font))
        if layer["align"] == "left":
            x = pad
        elif layer["align"] == "right":
            x = pad + block[0] - line_width
        else:
            x = pad + (block[0] - line_width) // 2
        y = pad + index * line_height

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
            stroke_width=outline_width if stroke[3] else 0,
            stroke_fill=stroke if stroke[3] else None,
        )

    if layer["shadow"]:
        # A soft drop shadow behind the tile, which is what keeps light text
        # legible over a busy photo even with the scrim.
        shadow = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        shadow.paste(tile, (0, 0), tile)
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(2, font_size // 14)))
        alpha = shadow.split()[3].point(lambda value: int(value * 0.7))
        shadow.putalpha(alpha)
        merged = Image.new("RGBA", tile.size, (0, 0, 0, 0))
        merged.paste(shadow, (0, 0), shadow)
        merged.paste(tile, (0, 0), tile)
        tile = merged

    if abs(layer["rotation"]) > 0.01:
        tile = tile.rotate(layer["rotation"], expand=True, resample=Image.BICUBIC)

    x, y = _anchor_position(
        layer["anchor"], tile.size, (width, height), margin
    )
    x += int(layer["offset_x"] * width)
    y += int(layer["offset_y"] * height)

    canvas.alpha_composite(tile, (x, y))
    return canvas


def _draw_logo(
    canvas: Image.Image, layer: dict, logo_bytes: bytes, margin: int
) -> Image.Image:
    try:
        logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    except Exception:  # noqa: BLE001 — a logo that will not open is not fatal
        logger.warning("Could not read the logo image; skipping it")
        return canvas

    target = max(8, int(min(canvas.size) * layer["size"]))
    factor = target / max(logo.width, logo.height)
    logo = logo.resize(
        (max(1, int(logo.width * factor)), max(1, int(logo.height * factor))),
        Image.LANCZOS,
    )

    if layer["opacity"] < 1.0:
        alpha = logo.split()[3].point(lambda value: int(value * layer["opacity"]))
        logo.putalpha(alpha)

    x, y = _anchor_position(layer["anchor"], logo.size, canvas.size, margin)
    x += int(layer["offset_x"] * canvas.width)
    y += int(layer["offset_y"] * canvas.height)

    canvas.alpha_composite(logo, (x, y))
    return canvas


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
# A template is a *function that produces a design*, not a stored blob. That is
# what lets one template serve every format: the layout is expressed in canvas
# fractions and the headline is supplied by the caller, so "Bold Centre" is the
# same idea at 1280x720 and at 1080x1920.
#
# Kept in code for the same reason the video templates are: one canonical list,
# versioned with the renderer that draws it.

THUMBNAIL_TEMPLATES: tuple[dict, ...] = (
    {
        "key": "bold_center",
        "name": "Bold Centre",
        "description": "One big headline in the middle. Reads at any size.",
    },
    {
        "key": "lower_third",
        "name": "Lower Third",
        "description": "Headline across the bottom, picture left clear above it.",
    },
    {
        "key": "split_accent",
        "name": "Accent Bar",
        "description": "Headline in a coloured box, with a kicker above it.",
    },
    {
        "key": "question",
        "name": "Question",
        "description": "A big question with a small answer teased underneath.",
    },
    {
        "key": "numbered",
        "name": "Numbered",
        "description": "A large number, then the headline. For lists.",
    },
    {
        "key": "minimal",
        "name": "Minimal",
        "description": "Small type, top-left. Lets the picture carry it.",
    },
)

TEMPLATES_BY_KEY = {entry["key"]: entry for entry in THUMBNAIL_TEMPLATES}


def build_design(
    *,
    template: str = "bold_center",
    headline: str = "",
    kicker: str = "",
    format_key: str = DEFAULT_FORMAT,
    palette: str = "mint",
    background_asset_id: int | None = None,
    brand: dict | None = None,
    logo_asset_id: int | None = None,
) -> dict:
    """Produce a design from a template and some words.

    `brand` is the user's Brand Kit. When it carries colours they replace the
    palette's, so a thumbnail made from a template still looks like the
    business that made it — which is the whole reason the Brand Kit exists.
    """
    spec = TEMPLATES_BY_KEY.get(template) or TEMPLATES_BY_KEY["bold_center"]
    key = spec["key"]

    chosen = PALETTES_BY_KEY.get(palette) or PALETTES_BY_KEY["mint"]
    colors = list(chosen["colors"])
    accent = chosen["accent"]

    brand_colors = [
        value
        for value in ((brand or {}).get("brand_colors") or [])
        if isinstance(value, str) and value.startswith("#")
    ]
    if len(brand_colors) >= 2:
        colors = brand_colors[:2]
        accent = brand_colors[-1]
    elif len(brand_colors) == 1:
        colors = [brand_colors[0], brand_colors[0]]
        accent = brand_colors[0]

    headline = (headline or "").strip()
    kicker = (kicker or "").strip()

    layers: list[dict] = []

    if key == "lower_third":
        layers.append({
            "type": "text", "id": "headline", "text": headline,
            "font_size": 0.11, "anchor": "bottom-center", "offset_y": -0.02,
            "uppercase": True, "align": "center", "max_width": 0.9,
        })
        if kicker:
            layers.append({
                "type": "text", "id": "kicker", "text": kicker,
                "font_size": 0.05, "anchor": "bottom-center", "offset_y": -0.16,
                "color": accent, "outline": "transparent",
            })
    elif key == "split_accent":
        if kicker:
            layers.append({
                "type": "text", "id": "kicker", "text": kicker,
                "font_size": 0.05, "anchor": "middle-center", "offset_y": -0.16,
                "color": accent, "uppercase": True, "outline": "transparent",
            })
        layers.append({
            "type": "text", "id": "headline", "text": headline,
            "font_size": 0.12, "anchor": "middle-center", "uppercase": True,
            "background": colors[0], "outline": "transparent", "max_width": 0.8,
        })
    elif key == "question":
        layers.append({
            "type": "text", "id": "headline", "text": headline,
            "font_size": 0.13, "anchor": "middle-center", "offset_y": -0.05,
            "max_width": 0.88,
        })
        layers.append({
            "type": "text", "id": "kicker", "text": kicker or "Here is why",
            "font_size": 0.055, "anchor": "middle-center", "offset_y": 0.2,
            "color": accent, "outline": "transparent",
        })
    elif key == "numbered":
        layers.append({
            "type": "text", "id": "number", "text": kicker or "5",
            "font_size": 0.34, "anchor": "middle-left", "offset_x": 0.04,
            "color": accent, "align": "left",
        })
        layers.append({
            "type": "text", "id": "headline", "text": headline,
            "font_size": 0.1, "anchor": "middle-right", "offset_x": -0.02,
            "align": "right", "max_width": 0.55, "uppercase": True,
        })
    elif key == "minimal":
        layers.append({
            "type": "text", "id": "headline", "text": headline,
            "font_size": 0.07, "anchor": "top-left", "align": "left",
            "max_width": 0.6, "shadow": True,
        })
        if kicker:
            layers.append({
                "type": "text", "id": "kicker", "text": kicker,
                "font_size": 0.04, "anchor": "top-left", "offset_y": 0.11,
                "align": "left", "color": accent, "outline": "transparent",
            })
    else:  # bold_center
        if kicker:
            layers.append({
                "type": "text", "id": "kicker", "text": kicker,
                "font_size": 0.05, "anchor": "top-center", "offset_y": 0.06,
                "color": accent, "uppercase": True, "outline": "transparent",
            })
        layers.append({
            "type": "text", "id": "headline", "text": headline,
            "font_size": 0.145, "anchor": "middle-center", "uppercase": True,
            "max_width": 0.88,
        })

    if logo_asset_id or (brand or {}).get("logo_url"):
        layers.append({
            "type": "logo", "id": "logo", "asset_id": logo_asset_id,
            "anchor": "bottom-right", "size": 0.12, "opacity": 0.95,
        })

    document = normalize({
        "format": format_key,
        "background": {
            "kind": "image" if background_asset_id else "gradient",
            "palette": palette,
            "colors": colors,
            "asset_id": background_asset_id,
            # A photo behind white text is unreadable about half the time. The
            # scrim is the fix that does not require the user to notice.
            "scrim": 0.4 if background_asset_id else 0.0,
        },
        "layers": layers,
    })
    # Remembered so "make variations" can start from the layout the user is
    # actually looking at rather than guessing.
    document["template"] = key
    return document


# ---------------------------------------------------------------------------
# Variations
# ---------------------------------------------------------------------------


def variations(design: dict, *, count: int = 4) -> list[dict]:
    """Several designs from one, varying only what is worth comparing.

    The *words stay the same* and the template alternates alongside the
    palette — because what the user is choosing between is layouts and
    colourways, not different copy. Varying the headline too would leave them
    unable to tell which change they were reacting to.
    """
    document = normalize(design)
    base_template = design.get("template") or "bold_center"

    headline = ""
    kicker = ""
    for layer in document["layers"]:
        if layer["type"] != "text":
            continue
        if layer["id"] in ("headline",) and not headline:
            headline = layer["text"]
        elif not kicker:
            kicker = layer["text"]
    if not headline and document["layers"]:
        first = next(
            (row for row in document["layers"] if row["type"] == "text"), None
        )
        headline = first["text"] if first else ""

    order = [base_template] + [
        entry["key"] for entry in THUMBNAIL_TEMPLATES if entry["key"] != base_template
    ]
    palettes = [document["background"]["palette"]] + [
        entry["key"]
        for entry in PALETTES
        if entry["key"] != document["background"]["palette"]
    ]

    out: list[dict] = []
    for index in range(max(1, min(count, 8))):
        out.append(
            build_design(
                template=order[index % len(order)],
                headline=headline,
                kicker=kicker,
                format_key=document["format"],
                palette=palettes[index % len(palettes)],
                background_asset_id=document["background"]["asset_id"],
            )
        )
    return out


def options() -> dict:
    """Everything the Thumbnail Studio's controls are built from."""
    from app.services.video.subtitles import SUBTITLE_FONTS

    return {
        "formats": [dict(entry) for entry in FORMATS],
        "templates": [dict(entry) for entry in THUMBNAIL_TEMPLATES],
        "palettes": [dict(entry) for entry in PALETTES],
        "anchors": list(ANCHORS),
        "fonts": list(SUBTITLE_FONTS),
        "background_kinds": list(BACKGROUND_KINDS),
    }
