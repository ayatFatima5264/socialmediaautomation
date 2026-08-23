"""Timeline → one ffmpeg command.

This module is the other half of the promise the editor makes: the preview and
the export are the same video, because both are functions of the same timeline
document and this is the only thing that turns that document into pixels.

**One command, not a pipeline of passes.** Everything — the visual sequence,
the audio mix and the text overlays — is built into a single `-filter_complex`
graph and encoded once. Rendering in stages would mean intermediate files, a
generation of quality loss per stage, and progress that jumps backwards every
time a new pass starts.

**Geometry is computed in Python, not in ffmpeg expressions.** The renderer has
already probed every source, so the exact crop rectangle and scaled size are
known numbers. Writing them as `iw`/`ih` expressions instead would put the same
arithmetic in a place where it cannot be unit-tested and where a mistake shows
up as a silently mis-framed export. `build_command` is therefore a pure
function of (timeline, canvas, probed sources) — which is exactly what makes
the tests below it meaningful.

**The graph, in the order it is built:**

    color(black, WxH)              the canvas — also what a gap renders as
      └─ overlay ×N                the video track, gated by `enable=between`
           └─ drawtext ×M          the text track, drawn over the composite
    anullsrc(silent)               guarantees an audio stream exists
      └─ amix                      the audio track: voice-over and music together

The video track is a sequence, so its clips never overlap and the overlays
cannot fight. The audio track is a mix, so `amix` is correct rather than a
compromise. That correspondence is not a coincidence — see
`SEQUENTIAL_TRACKS` in timeline.py.

**Text is passed by file, and expansion is switched off.** Two separate
hazards, and both bite:

  * `drawtext` reads its arguments out of the filter string, so a colon or a
    quote in somebody's title would change the meaning of the graph.
    `textfile=` sidesteps that, which is why there is no text-escaping helper
    here.
  * `drawtext` then runs the text it loaded — from a file too — through
    strftime and `%{...}` expansion. A title containing "100% real" is a
    "Stray %" error that makes the filter draw *nothing at all* while ffmpeg
    still exits 0. `expansion=none` is therefore not a nicety: without it, a
    percent sign anywhere in a title silently deletes the text track from the
    export while every check the renderer makes still passes.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path

from app.services.video import timeline as tl

logger = logging.getLogger(__name__)


class CompositorError(RuntimeError):
    """A timeline could not be turned into a command. User-facing message."""


@dataclass(frozen=True)
class Source:
    """A resolved input file, as the renderer probed it.

    `width`/`height` are None for audio. `duration` is the source's own length,
    used to clamp a trim that runs past the end of the file — a `-t` beyond the
    source makes ffmpeg pad or stall depending on the demuxer, and neither is
    what the timeline said.
    """

    path: str
    duration: float = 0.0
    width: int | None = None
    height: int | None = None
    has_video: bool = False
    has_audio: bool = False


# Audio is resampled to one format before mixing. Without this, mixing a 48 kHz
# stereo voice-over with a 44.1 kHz mono music bed makes `amix` resample on the
# fly with results that drift out of sync over a few minutes.
_SAMPLE_RATE = 44100
_AUDIO_FORMAT = f"aformat=sample_fmts=fltp:sample_rates={_SAMPLE_RATE}:channel_layouts=stereo"

# How long an animated text clip takes to arrive and to leave.
_ANIMATION_SECONDS = 0.35

# Quality presets, as x264 settings. `crf` is the quality knob and `preset` is
# the time/size trade — on a shared API server the preset matters more than the
# crf, which is why even "high" is not slower than `medium`.
QUALITY_SETTINGS = {
    "draft": {"crf": 30, "preset": "veryfast", "audio_bitrate": "128k"},
    "standard": {"crf": 24, "preset": "veryfast", "audio_bitrate": "160k"},
    "high": {"crf": 20, "preset": "medium", "audio_bitrate": "192k"},
}
DEFAULT_QUALITY = "standard"


# ---------------------------------------------------------------------------
# Filter-string escaping
# ---------------------------------------------------------------------------


def escape_filter_path(path: str | Path) -> str:
    """A filesystem path that survives being read as a filter argument.

    Windows paths are the reason this exists: `C:\\Users\\...` contains both a
    backslash (an escape character to ffmpeg's parser) and a colon (the
    argument separator). Forward slashes are accepted on Windows, so the
    backslashes go first and the drive colon is escaped.
    """
    text = str(path).replace("\\", "/")
    return text.replace(":", r"\:").replace("'", r"\'")


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
# `drawtext` needs a font *file*. Asking for a family by name requires
# fontconfig, which is not present in the static ffmpeg builds this app ships
# with, so the family is resolved to a path here.

_FONT_CANDIDATES: dict[str, tuple[str, ...]] = {
    "inter": ("Inter-Bold.ttf", "Inter.ttf", "segoeui.ttf", "DejaVuSans-Bold.ttf"),
    "roboto": ("Roboto-Bold.ttf", "Roboto-Regular.ttf", "DejaVuSans-Bold.ttf"),
    "montserrat": ("Montserrat-Bold.ttf", "DejaVuSans-Bold.ttf"),
    "poppins": ("Poppins-Bold.ttf", "DejaVuSans-Bold.ttf"),
    "open sans": ("OpenSans-Bold.ttf", "DejaVuSans-Bold.ttf"),
    "arial": ("arialbd.ttf", "arial.ttf", "Arial.ttf", "DejaVuSans-Bold.ttf"),
}

# Searched in order. The bundled directory comes first so a deployment can pin
# an exact face; the OS directories are the fallback that makes this work on a
# developer's machine with no setup.
_FONT_DIRECTORIES = (
    Path(__file__).resolve().parent.parent.parent / "assets" / "fonts",
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype"),
    Path("/usr/share/fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
)

# Anything, as long as it is a font. Reached when a project asks for a family
# nobody installed — a title in the wrong typeface is a far better outcome than
# a failed render.
_LAST_RESORT = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "arial.ttf", "segoeui.ttf")


def _find_font_file(family: str) -> str | None:
    wanted = list(_FONT_CANDIDATES.get((family or "").strip().lower(), ()))
    wanted.extend(name for name in _LAST_RESORT if name not in wanted)

    for name in wanted:
        for directory in _FONT_DIRECTORIES:
            candidate = directory / name
            try:
                if candidate.is_file():
                    return str(candidate)
            except OSError:  # pragma: no cover — an unreadable mount
                continue

    # Nothing matched by name: take the first font in the first directory that
    # has one, rather than giving up on text entirely.
    for directory in _FONT_DIRECTORIES:
        try:
            if not directory.is_dir():
                continue
            for entry in sorted(os.listdir(directory)):
                if entry.lower().endswith((".ttf", ".otf")):
                    return str(directory / entry)
        except OSError:  # pragma: no cover
            continue
    return None


def font_available() -> bool:
    """Whether text can be drawn on this deployment at all.

    Reported through `/api/video/capabilities`, so the editor can disable the
    text track rather than letting somebody write a title that silently will
    not export.
    """
    return _find_font_file("inter") is not None


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _even(value: float) -> int:
    """The nearest even integer, at least 2.

    yuv420p subsamples chroma by two, so an odd width or height is rejected by
    the encoder. Rounding here rather than letting `scale` do it keeps the
    number the overlay position was computed from the same as the number the
    frame actually has.
    """
    return max(2, int(round(value / 2)) * 2)


@dataclass(frozen=True)
class Placement:
    """Where one visual clip lands, in whole pixels."""

    crop_w: int
    crop_h: int
    crop_x: int
    crop_y: int
    scaled_w: int
    scaled_h: int
    pos_x: int
    pos_y: int


def tighten(placement: Placement, *, canvas_w: int, canvas_h: int) -> Placement:
    """Shrink a placement to only the part that lands on the canvas.

    **This is the difference between a vertical render taking 13 seconds and
    taking 5.** `cover` on a canvas of a different shape scales the source *up*
    so that it overflows — a 1280x720 clip on a 1080x1920 canvas becomes
    3414x1920, of which 68% is then discarded by the overlay. ffmpeg was
    scaling 6.5 megapixels per frame in order to keep 2.1.

    Cropping the source to the region that will actually be seen, and scaling
    only that, produces the same picture for a fraction of the work.

    **What this does and does not preserve.** A visible window is a whole
    number of *output* pixels, which maps to a fractional number of *source*
    pixels, and `crop` takes only integers — so at a large upscale factor
    (2.7 output pixels per source pixel is typical for 16:9 into 9:16) the
    window cannot always land on a boundary that is exact in both spaces. The
    window is therefore expanded outward to whole source pixels and the output
    size and position are derived from that same window at the original scale,
    which keeps the scale factor identical and the two consistent with each
    other.

    The result is the same framing **to within a pixel or two** at extreme
    upscales, and bit-identical whenever the clip does not overflow the canvas
    (`contain`, or `cover` on a matching aspect ratio), where this returns the
    placement untouched. That tolerance is well inside the difference any two
    resamplers would produce, and it buys roughly a 4x speedup on the vertical
    formats this product mostly renders.

    Returns the placement unchanged when nothing overflows. The caller skips it
    for a rotated clip: rotation happens *after* the scale, so the visible
    region is not a rectangle in source space and this substitution would not
    be equivalent.
    """
    left = max(0, -placement.pos_x)
    top = max(0, -placement.pos_y)
    right = max(0, (placement.pos_x + placement.scaled_w) - canvas_w)
    bottom = max(0, (placement.pos_y + placement.scaled_h) - canvas_h)

    if not (left or top or right or bottom):
        return placement

    # Output pixels per source pixel, kept as the exact ratio so the tightened
    # scale is the same scale.
    per_x = placement.scaled_w / placement.crop_w
    per_y = placement.scaled_h / placement.crop_h

    # The visible window in source pixels, expanded outward to whole pixels.
    source_x0 = placement.crop_x + math.floor(left / per_x)
    source_y0 = placement.crop_y + math.floor(top / per_y)
    source_x1 = placement.crop_x + math.ceil((placement.scaled_w - right) / per_x)
    source_y1 = placement.crop_y + math.ceil((placement.scaled_h - bottom) / per_y)

    # Never past the edge of what was cropped.
    source_x1 = min(source_x1, placement.crop_x + placement.crop_w)
    source_y1 = min(source_y1, placement.crop_y + placement.crop_h)

    source_w = source_x1 - source_x0
    source_h = source_y1 - source_y0
    if source_w < 2 or source_h < 2:
        return placement

    # The same scale, applied to the expanded window.
    output_w = max(2, int(round(source_w * per_x)))
    output_h = max(2, int(round(source_h * per_y)))

    # And the position that window belongs at, derived from the same numbers.
    offset_x = placement.pos_x + int(round((source_x0 - placement.crop_x) * per_x))
    offset_y = placement.pos_y + int(round((source_y0 - placement.crop_y) * per_y))

    return Placement(
        crop_w=source_w,
        crop_h=source_h,
        crop_x=source_x0,
        crop_y=source_y0,
        scaled_w=output_w,
        scaled_h=output_h,
        pos_x=offset_x,
        pos_y=offset_y,
    )


def place(clip: dict, source: Source, *, canvas_w: int, canvas_h: int) -> Placement:
    """Resolve a clip's crop, size and position against a canvas.

    The order is crop → fit → user scale → position, which is the order the
    inspector presents them and therefore the order the user expects:

      * **crop** takes fractions off the source's own edges,
      * **fit** sizes what is left to the canvas (`cover` fills and overflows,
        `contain` fits inside and leaves bars),
      * **scale** is the user's zoom *on top of* the fit, so 1.0 always means
        "as the fit decided" regardless of the source's shape,
      * **position** offsets from centre by a fraction of the canvas, so a
        composition survives the project being re-rendered at another size.

    This is the *full* placement, including the parts that fall outside the
    canvas. The renderer narrows it with `tighten()` before building the
    filter; the editor's preview uses it as-is, because a browser canvas clips
    an overflowing `drawImage` the same way `overlay` does.
    """
    source_w = source.width or canvas_w
    source_h = source.height or canvas_h

    crop = clip.get("crop") or {}
    left = float(crop.get("left", 0.0))
    top = float(crop.get("top", 0.0))
    right = float(crop.get("right", 0.0))
    bottom = float(crop.get("bottom", 0.0))

    crop_w = max(2, int(round(source_w * (1.0 - left - right))))
    crop_h = max(2, int(round(source_h * (1.0 - top - bottom))))
    crop_x = max(0, int(round(source_w * left)))
    crop_y = max(0, int(round(source_h * top)))

    # Never ask for a rectangle that runs off the source.
    crop_w = min(crop_w, source_w - crop_x)
    crop_h = min(crop_h, source_h - crop_y)

    if clip.get("fit") == "contain":
        factor = min(canvas_w / crop_w, canvas_h / crop_h)
    else:
        factor = max(canvas_w / crop_w, canvas_h / crop_h)
    factor *= float(clip.get("scale", 1.0) or 1.0)

    scaled_w = _even(crop_w * factor)
    scaled_h = _even(crop_h * factor)

    pos_x = int(round((canvas_w - scaled_w) / 2 + float(clip.get("x", 0.0)) * canvas_w))
    pos_y = int(round((canvas_h - scaled_h) / 2 + float(clip.get("y", 0.0)) * canvas_h))

    return Placement(
        crop_w=crop_w,
        crop_h=crop_h,
        crop_x=crop_x,
        crop_y=crop_y,
        scaled_w=scaled_w,
        scaled_h=scaled_h,
        pos_x=pos_x,
        pos_y=pos_y,
    )


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


def _source_span(clip: dict, source: Source) -> tuple[float, float]:
    """`(seek, take)` — where to start in the source and how much to read.

    `take` is in *source* seconds, so a clip playing at 2× reads twice its
    timeline length. Clamped to what the file actually contains: a `-t` past
    the end of a source makes ffmpeg either pad or stall, and the timeline said
    neither.
    """
    speed = float(clip.get("speed", 1.0) or 1.0)
    seek = max(0.0, float(clip.get("trim_start", 0.0) or 0.0))
    wanted = float(clip["duration"]) * speed

    trim_end = clip.get("trim_end")
    if trim_end is not None:
        wanted = min(wanted, max(0.0, float(trim_end) - seek))

    if source.duration > 0:
        wanted = min(wanted, max(0.0, source.duration - seek))

    return seek, max(tl.MIN_CLIP_SECONDS, wanted)


def _atempo_chain(speed: float) -> list[str]:
    """`atempo` filters covering a speed factor.

    One filter only handles 0.5–2.0, and the timeline allows 0.25–4.0, so the
    factor is split across as many stages as it takes. Without this, a clip at
    3× is silently clamped by ffmpeg and its audio drifts against its video.
    """
    stages: list[str] = []
    remaining = speed
    while remaining > 2.0 + 1e-9:
        stages.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5 - 1e-9:
        stages.append("atempo=0.5")
        remaining /= 0.5
    if abs(remaining - 1.0) > 1e-3:
        stages.append(f"atempo={remaining:.6f}")
    return stages


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


def _text_position(clip: dict, *, canvas_w: int, canvas_h: int) -> tuple[str, str]:
    """drawtext `x` and `y` expressions.

    Expressions rather than numbers because `text_w`/`text_h` are only known
    once the font has laid the string out — that is the one piece of geometry
    Python genuinely cannot compute here. The animated forms also need `t`.
    """
    offset_x = int(round(float(clip.get("x", 0.0)) * canvas_w))
    offset_y = int(round(float(clip.get("y", 0.0)) * canvas_h))

    align = clip.get("align", "center")
    margin = int(round(canvas_w * 0.06))
    if align == "left":
        x = f"{margin + offset_x}"
    elif align == "right":
        x = f"(w-text_w-{margin - offset_x})"
    else:
        x = f"((w-text_w)/2+{offset_x})"

    position = clip.get("position", "center")
    if position == "top":
        base_y = f"({int(round(canvas_h * 0.08))}+{offset_y})"
    elif position == "bottom":
        base_y = f"(h-text_h-{int(round(canvas_h * 0.12))}+{offset_y})"
    else:
        base_y = f"((h-text_h)/2+{offset_y})"

    start = float(clip["start"])
    animation = clip.get("animation", "none")

    if animation == "slide-up":
        # Rises into place over the entry window, then holds.
        travel = int(round(canvas_h * 0.05))
        y = (
            f"({base_y}+if(lt(t-{start:.3f},{_ANIMATION_SECONDS}),"
            f"{travel}*(1-(t-{start:.3f})/{_ANIMATION_SECONDS}),0))"
        )
    elif animation == "pop":
        # A short overshoot: comes up past its mark and settles back.
        travel = int(round(canvas_h * 0.02))
        y = (
            f"({base_y}-if(lt(t-{start:.3f},{_ANIMATION_SECONDS}),"
            f"{travel}*sin(3.14159*(t-{start:.3f})/{_ANIMATION_SECONDS}),0))"
        )
    else:
        y = base_y

    return x, y


def _text_alpha(clip: dict) -> str | None:
    """An `alpha` expression for an animated clip, or None for a static one."""
    if clip.get("animation", "none") == "none":
        return None

    start = float(clip["start"])
    end = start + float(clip["duration"])
    fade = min(_ANIMATION_SECONDS, float(clip["duration"]) / 2)

    return (
        f"if(lt(t,{start + fade:.3f}),(t-{start:.3f})/{fade:.3f},"
        f"if(gt(t,{end - fade:.3f}),({end:.3f}-t)/{fade:.3f},1))"
    )


def _hex_to_ffmpeg(colour: str) -> str:
    """`#RRGGBB` / `#RRGGBBAA` as ffmpeg's `0xRRGGBB@alpha`."""
    if not colour or colour == "transparent":
        return "black@0.0"
    body = colour.lstrip("#")
    if len(body) == 3:
        body = "".join(character * 2 for character in body)
    if len(body) == 8:
        alpha = int(body[6:8], 16) / 255
        return f"0x{body[:6]}@{alpha:.3f}"
    return f"0x{body[:6]}"


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


@dataclass
class Plan:
    """A built command, plus what the caller needs to run and report on it."""

    args: list[str]
    duration: float
    # Temporary text files the graph references. The caller owns their
    # lifetime — they must outlive the ffmpeg process, which is why they are
    # returned rather than cleaned up here.
    text_files: list[str]


def build_command(
    *,
    timeline: dict,
    width: int,
    height: int,
    fps: int,
    sources: dict[int, Source],
    output_path: str | Path,
    work_dir: str | Path,
    settings: dict | None = None,
) -> Plan:
    """Turn a normalized timeline into one ffmpeg invocation.

    `sources` maps asset id to a probed file. A clip whose asset is missing is
    **skipped**, not fatal — the renderer checks for missing assets before it
    gets here and fails with `missing_asset`, so reaching this function with a
    gap means the caller decided to render anyway.

    Raises `CompositorError` only for a timeline that cannot produce a video at
    all: nothing on it, or a text clip with no font on the machine.
    """
    document = tl.normalize(timeline)
    total = tl.duration(document)
    if total <= 0:
        raise CompositorError("There is nothing on the timeline to render.")

    options = settings or {}
    quality = QUALITY_SETTINGS.get(
        str(options.get("quality") or DEFAULT_QUALITY), QUALITY_SETTINGS[DEFAULT_QUALITY]
    )

    work = Path(work_dir)
    canvas_w, canvas_h = _even(width), _even(height)

    inputs: list[str] = []
    filters: list[str] = []
    text_files: list[str] = []

    # ---- input 0: the canvas --------------------------------------------
    # Also what a gap on the video track renders as, which is why it is a black
    # colour source rather than the first clip.
    inputs += [
        "-f", "lavfi",
        "-i", f"color=c=black:s={canvas_w}x{canvas_h}:r={fps}:d={total:.3f}",
    ]
    # ---- input 1: silence ------------------------------------------------
    # Guarantees an audio stream on the output even for a project with no
    # sound. A video whose audio track is absent rather than silent is
    # rejected by some platforms and plays inconsistently on others.
    inputs += ["-f", "lavfi", "-i", f"anullsrc=r={_SAMPLE_RATE}:cl=stereo"]

    next_input = 2
    audio_labels: list[str] = []
    video_chain = "0:v"

    # ---- the video track -------------------------------------------------
    for index, clip in enumerate(tl.get_track(document, "video")["clips"]):
        source = sources.get(clip["asset_id"] or -1)
        if source is None or not source.has_video:
            continue

        seek, take = _source_span(clip, source)
        start = float(clip["start"])
        speed = float(clip.get("speed", 1.0) or 1.0)

        if clip["kind"] == "image":
            # A still has no timebase: loop one frame for as long as the clip
            # is on the timeline, at the project's frame rate.
            inputs += [
                "-loop", "1",
                "-framerate", str(fps),
                "-t", f"{clip['duration']:.3f}",
                "-i", str(source.path),
            ]
        else:
            # `-ss` before `-i` seeks by demuxer, which is orders of magnitude
            # faster than decoding from zero and is frame-accurate in ffmpeg 7.
            inputs += [
                "-ss", f"{seek:.3f}",
                "-t", f"{take:.3f}",
                "-i", str(source.path),
            ]

        stream = f"{next_input}:v"
        placement = place(clip, source, canvas_w=canvas_w, canvas_h=canvas_h)
        rotation = float(clip.get("rotation", 0.0) or 0.0)

        # Scale only what will be seen. Skipped for a rotated clip: the
        # rotation happens after the scale, so the visible region is not a
        # rectangle in source space and the substitution is not equivalent.
        if abs(rotation) <= 1e-6:
            placement = tighten(placement, canvas_w=canvas_w, canvas_h=canvas_h)

        stages = [
            f"crop={placement.crop_w}:{placement.crop_h}"
            f":{placement.crop_x}:{placement.crop_y}",
            f"scale={placement.scaled_w}:{placement.scaled_h}",
        ]

        if abs(rotation) > 1e-6:
            # `c=none` keeps the corners transparent instead of black, so a
            # rotated clip composites over what is behind it.
            stages.append(f"rotate={rotation}*PI/180:c=none")

        stages.append("format=rgba")

        opacity = float(clip.get("opacity", 1.0) or 1.0)
        if opacity < 1.0 - 1e-6:
            stages.append(f"colorchannelmixer=aa={opacity:.3f}")

        # Put the clip's frames where the timeline says they belong. Speed is
        # a division of the presentation timestamps — the same factor the
        # audio's `atempo` chain applies, so the two stay locked.
        if clip["kind"] == "image":
            stages.append(f"setpts=PTS-STARTPTS+{start:.3f}/TB")
        else:
            stages.append(f"setpts=(PTS-STARTPTS)/{speed:.6f}+{start:.3f}/TB")

        label = f"v{index}"
        filters.append(f"[{stream}]" + ",".join(stages) + f"[{label}]")

        end = start + float(clip["duration"])
        out = f"vc{index}"
        # `eof_action=pass` lets the canvas continue after this clip ends —
        # without it the whole composite stops at the first clip's end.
        filters.append(
            f"[{video_chain}][{label}]overlay="
            f"x={placement.pos_x}:y={placement.pos_y}"
            f":eof_action=pass:shortest=0"
            f":enable='between(t,{start:.3f},{end:.3f})'[{out}]"
        )
        video_chain = out

        # A video clip's own audio, when it has some and is not muted.
        if source.has_audio and not clip.get("muted") and float(clip.get("volume", 1.0)) > 0:
            audio_labels.append(
                _audio_branch(
                    filters,
                    stream=f"{next_input}:a",
                    clip=clip,
                    label=f"av{index}",
                    speed=speed,
                )
            )

        next_input += 1

    # ---- the audio track -------------------------------------------------
    for index, clip in enumerate(tl.get_track(document, "audio")["clips"]):
        source = sources.get(clip["asset_id"] or -1)
        if source is None or not source.has_audio:
            continue
        if clip.get("muted") or float(clip.get("volume", 1.0)) <= 0:
            continue

        seek, take = _source_span(clip, source)
        inputs += ["-ss", f"{seek:.3f}", "-t", f"{take:.3f}", "-i", str(source.path)]

        audio_labels.append(
            _audio_branch(
                filters,
                stream=f"{next_input}:a",
                clip=clip,
                label=f"aa{index}",
                speed=float(clip.get("speed", 1.0) or 1.0),
            )
        )
        next_input += 1

    # ---- the text track --------------------------------------------------
    text_clips = [
        clip
        for clip in tl.get_track(document, "text")["clips"]
        if (clip.get("text") or "").strip()
    ]

    if text_clips:
        font_file = _find_font_file(text_clips[0].get("font_family", "Inter"))
        if font_file is None:
            raise CompositorError(
                "No font is available to draw text on this server. Remove the "
                "text clips, or install a font."
            )

    for index, clip in enumerate(text_clips):
        content = clip["text"].upper() if clip.get("uppercase") else clip["text"]
        # By file, never inlined — see the module docstring.
        path = work / f"text_{index}.txt"
        path.write_text(content, encoding="utf-8")
        text_files.append(str(path))

        font_file = _find_font_file(clip.get("font_family", "Inter")) or font_file
        x, y = _text_position(clip, canvas_w=canvas_w, canvas_h=canvas_h)
        start = float(clip["start"])
        end = start + float(clip["duration"])

        parts = [
            f"fontfile='{escape_filter_path(font_file)}'",
            f"textfile='{escape_filter_path(path)}'",
            # Literal text. Without this a "%" in a title is a "Stray %" that
            # makes drawtext render nothing while ffmpeg still exits 0 — see
            # the module docstring.
            "expansion=none",
            f"fontcolor={_hex_to_ffmpeg(clip['color'])}",
            f"fontsize={clip['font_size']}",
            # Quoted, and that is not cosmetic. An animated position is an
            # expression like `if(lt(t,0.35),13*(1-t/0.35),0)` — and a comma
            # inside an *unquoted* filter argument is read as the separator
            # between two filters, so the graph silently becomes nonsense and
            # ffmpeg fails with "No option name near" a fragment of the
            # expression. `alpha` was quoted from the start; these were not,
            # which is why a static title rendered and a sliding one did not.
            f"x='{x}'",
            f"y='{y}'",
            "line_spacing=8",
            f"enable='between(t,{start:.3f},{end:.3f})'",
        ]

        if int(clip.get("outline_width", 0)) > 0 and clip.get("outline") != "transparent":
            parts.append(f"borderw={clip['outline_width']}")
            parts.append(f"bordercolor={_hex_to_ffmpeg(clip['outline'])}")

        if clip.get("background") and clip["background"] != "transparent":
            parts.append("box=1")
            parts.append(f"boxcolor={_hex_to_ffmpeg(clip['background'])}")
            parts.append("boxborderw=18")

        alpha = _text_alpha(clip)
        if alpha:
            parts.append(f"alpha='{alpha}'")

        out = f"vt{index}"
        filters.append(f"[{video_chain}]drawtext=" + ":".join(parts) + f"[{out}]")
        video_chain = out

    # ---- the mix ---------------------------------------------------------
    # The silent base is always in the mix, so `amix` has an input even when
    # the project has no audio and the output always carries a stream.
    filters.append(f"[1:a]{_AUDIO_FORMAT},atrim=0:{total:.3f}[abase]")
    mix_inputs = ["abase"] + audio_labels
    if len(mix_inputs) == 1:
        filters.append("[abase]anull[aout]")
    else:
        joined = "".join(f"[{label}]" for label in mix_inputs)
        # `normalize=0` keeps each track at the gain the user set. With
        # normalisation on, adding a quiet sound effect would duck the
        # voice-over — mixing is not averaging.
        filters.append(
            f"{joined}amix=inputs={len(mix_inputs)}:duration=longest:normalize=0[aout]"
        )

    # `format=yuv420p` last: the overlays work in RGBA, and every player
    # expects 4:2:0 in an MP4.
    filters.append(f"[{video_chain}]format=yuv420p[vout]")

    args = [
        "-hide_banner",
        "-nostdin",
        # Progress is parsed from stderr; `-stats` guarantees the time= lines
        # are emitted even when the log level is low.
        "-loglevel", "error",
        "-stats",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-map", "[aout]",
        "-r", str(fps),
        # The authoritative length. Every stream is trimmed to the timeline, so
        # a source that overruns cannot extend the export.
        "-t", f"{total:.3f}",
        "-c:v", "libx264",
        "-preset", quality["preset"],
        "-crf", str(quality["crf"]),
        "-pix_fmt", "yuv420p",
        # Playable before it is fully downloaded, which is what a preview in a
        # browser needs.
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", quality["audio_bitrate"],
        "-ar", str(_SAMPLE_RATE),
        "-y",
        str(output_path),
    ]

    return Plan(args=args, duration=total, text_files=text_files)


def _audio_branch(
    filters: list[str], *, stream: str, clip: dict, label: str, speed: float
) -> str:
    """One audio input, trimmed, sped, faded, delayed — ready for the mix.

    Order matters and is not arbitrary: tempo first so the fades are measured
    in output seconds, then gain, then the fades, then the delay that puts the
    clip where the timeline says. Fading before `atempo` would make a
    one-second fade last two seconds on a half-speed clip.
    """
    stages = [_AUDIO_FORMAT, "asetpts=PTS-STARTPTS"]
    stages.extend(_atempo_chain(speed))

    volume = float(clip.get("volume", 1.0) or 1.0)
    if abs(volume - 1.0) > 1e-6:
        stages.append(f"volume={volume:.4f}")

    duration = float(clip["duration"])
    fade_in = float(clip.get("fade_in", 0.0) or 0.0)
    fade_out = float(clip.get("fade_out", 0.0) or 0.0)

    if fade_in > 0:
        stages.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        stages.append(
            f"afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}"
        )

    start = float(clip["start"])
    if start > 0:
        milliseconds = int(round(start * 1000))
        # `all=1` applies the delay to every channel; without it only the first
        # is delayed and the clip arrives smeared across the stereo field.
        stages.append(f"adelay=delays={milliseconds}:all=1")

    filters.append(f"[{stream}]" + ",".join(stages) + f"[{label}]")
    return label
