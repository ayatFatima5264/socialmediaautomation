"""Video templates — the system set, and reading the library.

A template is a starting point, not a link: applying one copies its definition
into a new project and the two are then unrelated. See the model docstring for
why.

The system templates are defined here in code and synchronised into the table
on startup. That is the same choice `presets.py` makes and for the same reason
— one canonical list, versioned with the code that renders it, rather than seed
data that drifts between environments. Editing a definition here updates every
deployment on its next boot; it does **not** reach into projects already
created from it.
"""
from __future__ import annotations

import logging
import re
from copy import deepcopy

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.video_project import EMPTY_TIMELINE, VideoProject
from app.models.video_scene import VideoScene
from app.models.video_subtitle import VideoSubtitle
from app.models.video_template import (
    SURFACE_CATEGORIES,
    TEMPLATE_CATEGORIES,
    VideoTemplate,
)
from app.services.video import subtitles as subtitle_engine

logger = logging.getLogger(__name__)

# What each category tab says. Kept here rather than on the model because it is
# presentation; the model stores the slug. Anything missing falls back to the
# slug title-cased, so a category added to the tuple still renders.
CATEGORY_LABELS = {
    "youtube": "YouTube",
    "shorts": "Shorts",
    "tiktok": "TikTok",
    "reels": "Reels",
    "educational": "Educational",
    "business": "Business",
    "motivation": "Motivation",
    "facts": "Facts",
    "product": "Product",
    "documentary": "Documentary",
    "storytelling": "Storytelling",
    "animated": "Animated",
    "other": "Other",
}


class TemplateError(RuntimeError):
    """A template operation was refused. The message is user-facing."""


# The default text layout a template starts from: where a title and a body
# line sit on the canvas, and how much of the edge to keep clear.
#
# The safe area is not decoration. Every vertical surface puts its own UI over
# the video — TikTok's caption and buttons, Reels' action rail, Shorts' title —
# and a template whose text runs to the frame edge produces a video with its
# own words underneath somebody else's interface.
DEFAULT_LAYOUT: dict = {
    "title": {"position": "center", "size": "xl", "align": "center", "max_lines": 3},
    "body": {"position": "lower", "size": "md", "align": "center", "max_lines": 2},
    "safe_area": {"top": 0.08, "bottom": 0.14, "left": 0.06, "right": 0.06},
}


def _definition(**overrides) -> dict:
    """A template definition with the defaults filled in.

    This document is the entire template. There is no rendered video behind it
    and there is not meant to be: a template is configuration a new project is
    built from, so changing one here changes what the *next* project starts
    with and touches nothing already made.
    """
    base = {
        "timeline": deepcopy(EMPTY_TIMELINE),
        "scenes": [],
        "subtitle_style": subtitle_engine.preset(subtitle_engine.DEFAULT_PRESET),
        "layout": deepcopy(DEFAULT_LAYOUT),
        # Which face the burned-in text uses. A name the compositor already
        # resolves (see `compositor._FONT_CANDIDATES`), never a file — a
        # template that shipped a font would be shipping a licence too.
        "typography": {"family": "inter", "weight": "bold", "case": "none"},
        # Where a music bed belongs, if one does. `None` means the format does
        # not want one — a talking-head clip with a bed under the voice is
        # worse than silence. Nothing is chosen here: the Music Library picks
        # the track, this says what it should sound like when it lands.
        "music": None,
        "brand": {"apply": True},
        "export_settings": {
            "format": "mp4",
            "quality": "high",
            "burn_subtitles": True,
        },
        # What the card in the picker draws. Colours and a sample line, NOT an
        # image: the preview is generated from the template's own configuration,
        # so it cannot advertise a look the template does not actually produce.
        # `preview_asset_id` on the row stays NULL until somebody renders real
        # artwork, and the card never pretends otherwise.
        "preview": {
            "accent": "#10b981",
            "background": ["#0f2f26", "#0b1f1a"],
            "sample_title": "YOUR HOOK HERE",
            "style": "bold-center",
        },
    }
    base.update(overrides)
    return base


def _preview(accent: str, background: list[str], sample: str, style: str = "bold-center") -> dict:
    """Shorthand for a template's card preview."""
    return {
        "accent": accent,
        "background": background,
        "sample_title": sample,
        "style": style,
    }


# What a scene is *for*, as a closed vocabulary. Drives the preview's shape and
# gives the editor something to label a beat with beyond its position.
SCENE_ROLES = (
    "hook", "intro", "point", "step", "proof", "quote", "product", "cta", "outro",
)

# What kind of visual the beat wants. The template cannot supply the media — it
# says what belongs there, and the editor and the AI visual step both read it.
MEDIA_KINDS = (
    "footage", "image", "product", "screen", "b-roll", "text-only", "speaker",
)


def _scene(
    title: str,
    seconds: float,
    transition: str = "fade",
    *,
    role: str = "point",
    prompt: str = "",
    media: str = "footage",
    animation: str = "fade",
    layout: str = "center",
    text: str = "",
) -> dict:
    """One beat of the template.

    **`text` is empty across the whole system set, and `prompt` is why that is
    not a gap.** A template supplies the *shape* of a video — how many beats,
    how long each runs, what each one is for. Writing sentences into `text`
    would put words in a business's mouth: `text` is what the voice reads, what
    the subtitles are built from, and what the renderer draws, so a sample line
    nobody edited would be narrated and published verbatim.

    `prompt` is the instruction instead — "Open with the problem your viewer
    has". It travels to the project in `VideoScene.settings`, which nothing
    renders from, and the editor binds it to the field's *placeholder* rather
    than its value. So it is visible exactly where the user needs it and cannot
    become content by being left alone.
    """
    return {
        "title": title,
        "text": text,
        "duration_seconds": seconds,
        "transition": transition,
        "role": role,
        "prompt": prompt,
        "media": media,
        "animation": animation,
        "layout": layout,
    }


# The templates every account sees.
#
# Each one is a canvas, a caption style, a text layout and a scene skeleton —
# which is what a template can honestly deliver. None of them ships artwork:
# `preview_asset_id` stays NULL, and the card in the picker draws the
# `preview` block from the definition rather than showing a stock frame from a
# video the template will not actually produce.
#
# Every category in TEMPLATE_CATEGORIES has at least one entry, because a
# filter tab that leads to an empty grid is worse than no tab. Scene counts and
# durations are the working shape of that format, not a suggestion: a 6-second
# beat in a Shorts template is 6 seconds because that is what holds on that
# surface.
SYSTEM_TEMPLATES: tuple[dict, ...] = (
    # ---- Blank canvases ---------------------------------------------------
    # First in the list and first in the grid. The most common thing somebody
    # wants from this screen is to get past it.
    {
        "key": "blank_shorts",
        "name": "Blank — Vertical",
        "description": "An empty 9:16 canvas for Shorts, Reels and TikTok.",
        "category": "shorts",
        "platform": "youtube_shorts",
        "sort_order": 10,
        "definition": _definition(
            preview=_preview("#10b981", ["#111827", "#0b1220"], "9:16", "blank"),
        ),
    },
    {
        "key": "blank_youtube",
        "name": "Blank — Landscape",
        "description": "An empty 16:9 canvas for YouTube and Facebook.",
        "category": "youtube",
        "platform": "youtube",
        "sort_order": 20,
        "definition": _definition(
            preview=_preview("#10b981", ["#111827", "#0b1220"], "16:9", "blank"),
        ),
    },

    # ---- YouTube ----------------------------------------------------------
    {
        "key": "youtube_explainer",
        "name": "YouTube Explainer",
        "description": "Cold open, intro, three sections and an outro — the standard long-form shape.",
        "category": "youtube",
        "platform": "youtube",
        "sort_order": 30,
        "definition": _definition(
            music=None,
            subtitle_style=subtitle_engine.preset("youtube"),
            preview=_preview("#ef4444", ["#1f2937", "#111827"], "EXPLAINED", "lower-third"),
            layout={
                **deepcopy(DEFAULT_LAYOUT),
                # Landscape puts the title in the lower third, where a YouTube
                # player's own controls do not sit until the viewer moves the
                # mouse — centre-screen text fights the video itself.
                "title": {"position": "lower", "size": "lg", "align": "left", "max_lines": 2},
            },
            scenes=[
                _scene("Cold open", 6.0, "cut", role="hook", media="b-roll",
                       animation="none", layout="lower",
                       prompt="Open with the problem your viewer has, in one sentence"),
                _scene("Intro", 8.0, role="intro", media="speaker", layout="lower",
                       prompt="Say who you are and what they will know by the end"),
                _scene("Section 1", 30.0, role="point", media="screen", layout="lower",
                       prompt="Introduce the main idea and why it matters"),
                _scene("Section 2", 30.0, role="point", media="screen", layout="lower",
                       prompt="Show the key benefit, with an example"),
                _scene("Section 3", 30.0, role="point", media="b-roll", layout="lower",
                       prompt="Handle the objection they are already thinking"),
                _scene("Outro", 12.0, role="cta", media="speaker", layout="lower",
                       prompt="End with a clear CTA - one action, not three"),
            ],
        ),
    },

    # ---- Shorts -----------------------------------------------------------
    {
        "key": "talking_head_shorts",
        "name": "Talking Head",
        "description": "One speaker, big captions burned in. For a clip cut from a longer video.",
        "category": "shorts",
        "platform": "youtube_shorts",
        "sort_order": 40,
        "definition": _definition(
            music=None,
            scenes=[
                _scene("Hook", 3.0, "cut", role="hook", media="speaker",
                       animation="pop", layout="center",
                       prompt="Open with the line that stops the scroll"),
                _scene("The point", 18.0, role="point", media="speaker", layout="center",
                       prompt="Make one point. A short clip cannot carry two"),
                _scene("Sign off", 4.0, role="cta", media="speaker", layout="lower",
                       prompt="End with a clear CTA"),
            ],
            subtitle_style=subtitle_engine.preset("shorts"),
            preview=_preview("#10b981", ["#134e4a", "#0f2f2c"], "BIG CAPTIONS", "caption-heavy"),
        ),
    },

    # ---- TikTok -----------------------------------------------------------
    {
        "key": "tiktok_hook",
        "name": "TikTok Hook",
        "description": "Three seconds to stop the scroll, then payoff. Captions sit above the UI.",
        "category": "tiktok",
        "platform": "tiktok",
        "sort_order": 50,
        "definition": _definition(
            music={'mood': 'energetic', 'volume': 0.18, 'ducking': True},
            subtitle_style=subtitle_engine.preset("tiktok"),
            preview=_preview("#f43f5e", ["#18181b", "#27272a"], "WAIT FOR IT…", "caption-heavy"),
            layout={
                **deepcopy(DEFAULT_LAYOUT),
                # TikTok's caption, handle and button rail occupy roughly the
                # bottom fifth of the frame and the right edge. Text placed
                # there is text the viewer never reads.
                "safe_area": {"top": 0.10, "bottom": 0.22, "left": 0.06, "right": 0.18},
            },
            scenes=[
                _scene("Hook", 3.0, "cut", role="hook", media="footage",
                       animation="pop", layout="upper",
                       prompt="Open with the problem your viewer has - three seconds, no build-up"),
                _scene("Setup", 5.0, "cut", role="intro", media="footage", layout="upper",
                       prompt="Introduce the main idea"),
                _scene("Payoff", 5.0, "cut", role="proof", media="footage",
                       animation="pop", layout="upper",
                       prompt="Show the key benefit - this is what they stayed for"),
                _scene("Loop back", 3.0, "cut", role="cta", media="footage", layout="upper",
                       prompt="End with a clear CTA, or a line that sends them back to the start"),
            ],
        ),
    },

    # ---- Reels ------------------------------------------------------------
    {
        "key": "reels_showcase",
        "name": "Reels Showcase",
        "description": "Five quick beats cut to a music bed. For a place, a product or a process.",
        "category": "reels",
        "platform": "instagram_reels",
        "sort_order": 60,
        "definition": _definition(
            music={'mood': 'uplifting', 'volume': 0.28, 'ducking': True},
            subtitle_style=subtitle_engine.preset("minimal"),
            preview=_preview("#a855f7", ["#2e1065", "#1e1b4b"], "SHOWCASE", "grid"),
            layout={
                **deepcopy(DEFAULT_LAYOUT),
                "safe_area": {"top": 0.12, "bottom": 0.20, "left": 0.06, "right": 0.16},
            },
            scenes=[
                _scene("Beat 1", 3.0, "cut", role="hook", media="image",
                       animation="slide-up", prompt="Open on the strongest shot you have"),
                _scene("Beat 2", 3.0, "cut", role="point", media="image",
                       animation="slide-up", prompt="Add supporting visual"),
                _scene("Beat 3", 3.0, "cut", role="point", media="image",
                       animation="slide-up", prompt="Add supporting visual"),
                _scene("Beat 4", 3.0, "cut", role="point", media="image",
                       animation="slide-up", prompt="Add supporting visual"),
                _scene("Beat 5", 3.0, "cut", role="cta", media="image",
                       animation="slide-up", prompt="End with a clear CTA"),
            ],
        ),
    },

    # ---- Educational ------------------------------------------------------
    {
        "key": "explainer_reels",
        "name": "Explainer",
        "description": "A question, three beats of answer, and a summary. Vertical.",
        "category": "educational",
        "platform": "instagram_reels",
        "sort_order": 70,
        "definition": _definition(
            music={'mood': 'calm', 'volume': 0.15, 'ducking': True},
            preview=_preview("#0ea5e9", ["#0c4a6e", "#082f49"], "HOW IT WORKS", "bold-center"),
            scenes=[
                _scene("The question", 4.0, "cut", role="hook", media="text-only",
                       animation="pop", prompt="Ask the question your viewer already has"),
                _scene("Because", 6.0, role="point", media="footage",
                       prompt="Introduce the main idea in one sentence"),
                _scene("Which means", 6.0, role="point", media="footage",
                       prompt="Show what follows from it"),
                _scene("So", 6.0, role="point", media="footage",
                       prompt="Show the key benefit to them specifically"),
                _scene("Summary", 4.0, role="outro", media="text-only",
                       animation="pop", prompt="Say the one thing to remember"),
            ],
        ),
    },
    {
        "key": "tutorial_steps",
        "name": "Step-by-Step Tutorial",
        "description": "An intro, four numbered steps and a result. Numbers stay on screen.",
        "category": "educational",
        "platform": "youtube_shorts",
        "sort_order": 75,
        "definition": _definition(
            music={'mood': 'calm', 'volume': 0.12, 'ducking': True},
            subtitle_style=subtitle_engine.preset("highlight"),
            preview=_preview("#0ea5e9", ["#082f49", "#0c4a6e"], "STEP 1", "numbered"),
            scenes=[
                _scene("What you will make", 5.0, "cut", role="hook", media="product",
                       prompt="Show the finished result first - that is the reason to watch"),
                _scene("Step 1", 8.0, role="step", media="screen",
                       prompt="First step. One action, stated plainly"),
                _scene("Step 2", 8.0, role="step", media="screen",
                       prompt="Second step"),
                _scene("Step 3", 8.0, role="step", media="screen",
                       prompt="Third step"),
                _scene("Step 4", 4.0, role="step", media="screen",
                       prompt="Final step"),
                _scene("The result", 4.0, role="cta", media="product",
                       prompt="Show the result again and end with a clear CTA"),
            ],
        ),
    },

    # ---- Business ---------------------------------------------------------
    {
        "key": "business_update",
        "name": "Business Update",
        "description": "A clean corporate format: headline, three points, contact card.",
        "category": "business",
        "platform": "instagram_post",
        "sort_order": 80,
        "definition": _definition(
            music={'mood': 'professional', 'volume': 0.14, 'ducking': True},
            subtitle_style=subtitle_engine.preset("clean"),
            preview=_preview("#0f766e", ["#134e4a", "#0f2f2c"], "COMPANY UPDATE", "lower-third"),
            # The one template that leans hardest on the Brand Kit — a
            # corporate update in the wrong colours is worse than none.
            brand={"apply": True, "require_logo": True},
            scenes=[
                _scene("Headline", 5.0, "cut", role="hook", media="text-only",
                       layout="lower", prompt="The announcement, in one line"),
                _scene("Point 1", 7.0, role="point", media="b-roll", layout="lower",
                       prompt="Introduce the main idea"),
                _scene("Point 2", 7.0, role="point", media="b-roll", layout="lower",
                       prompt="Show the key benefit"),
                _scene("Point 3", 5.0, role="point", media="b-roll", layout="lower",
                       prompt="Add supporting visual and the detail that proves it"),
                _scene("Get in touch", 3.0, role="cta", media="text-only", layout="lower",
                       prompt="End with a clear CTA"),
            ],
        ),
    },

    # ---- Motivation -------------------------------------------------------
    {
        "key": "listicle_shorts",
        "name": "Top 5 List",
        "description": "A hook and five numbered points, one scene each.",
        "category": "motivation",
        "platform": "youtube_shorts",
        "sort_order": 90,
        "definition": _definition(
            music={'mood': 'energetic', 'volume': 0.18, 'ducking': True},
            preview=_preview("#f59e0b", ["#451a03", "#292524"], "TOP 5", "numbered"),
            scenes=[
                _scene("Hook", 3.0, "cut", role="hook", media="text-only",
                       animation="pop", prompt="Name the list and why it matters"),
                _scene("Point 1", 5.0, "cut", role="point", media="footage",
                       animation="slide-up", prompt="First item - one line"),
                _scene("Point 2", 5.0, "cut", role="point", media="footage",
                       animation="slide-up", prompt="Second item"),
                _scene("Point 3", 5.0, "cut", role="point", media="footage",
                       animation="slide-up", prompt="Third item"),
                _scene("Point 4", 5.0, "cut", role="point", media="footage",
                       animation="slide-up", prompt="Fourth item"),
                _scene("Point 5", 5.0, "cut", role="point", media="footage",
                       animation="slide-up", prompt="Strongest item last"),
                _scene("Call to action", 3.0, role="cta", media="text-only",
                       prompt="End with a clear CTA"),
            ],
        ),
    },
    {
        "key": "motivation_quote",
        "name": "Quote Card",
        "description": "One line, held long enough to read twice, over a slow push-in.",
        "category": "motivation",
        "platform": "instagram_reels",
        "sort_order": 95,
        "definition": _definition(
            music={'mood': 'inspiring', 'volume': 0.3, 'ducking': False},
            subtitle_style=subtitle_engine.preset("minimal"),
            preview=_preview("#f59e0b", ["#292524", "#1c1917"], "“BELIEVE IN\nYOURSELF”", "quote"),
            layout={
                **deepcopy(DEFAULT_LAYOUT),
                "title": {"position": "center", "size": "xl", "align": "center", "max_lines": 4},
                "body": {"position": "lower", "size": "sm", "align": "center", "max_lines": 1},
            },
            scenes=[
                _scene("The quote", 7.0, "cut", role="quote", media="footage",
                       animation="fade", prompt="The quote. Short enough to read in one breath"),
                _scene("Attribution", 3.0, role="outro", media="footage",
                       prompt="Who said it - and your handle if you want the credit"),
            ],
        ),
    },

    # ---- Facts ------------------------------------------------------------
    {
        "key": "facts_countdown",
        "name": "Fact Countdown",
        "description": "Five facts counted down to number one, with a stinger between each.",
        "category": "facts",
        "platform": "youtube_shorts",
        "sort_order": 100,
        "definition": _definition(
            music={'mood': 'energetic', 'volume': 0.18, 'ducking': True},
            subtitle_style=subtitle_engine.preset("highlight"),
            preview=_preview("#22d3ee", ["#083344", "#0c4a6e"], "FACT #5", "numbered"),
            scenes=[
                _scene("Hook", 3.0, "cut", role="hook", media="text-only",
                       animation="pop", prompt="Promise the payoff - what they will know in 30 seconds"),
                _scene("Fact #5", 5.0, "cut", role="point", media="image",
                       animation="slide-up", prompt="Fifth-most surprising fact"),
                _scene("Fact #4", 5.0, "cut", role="point", media="image",
                       animation="slide-up", prompt="Fourth"),
                _scene("Fact #3", 5.0, "cut", role="point", media="image",
                       animation="slide-up", prompt="Third"),
                _scene("Fact #2", 5.0, "cut", role="point", media="image",
                       animation="slide-up", prompt="Second"),
                _scene("Fact #1", 5.0, "cut", role="point", media="image",
                       animation="pop", prompt="The most surprising one - save it for last"),
                _scene("Which one surprised you?", 3.0, role="cta", media="text-only",
                       prompt="End with a clear CTA - ask for the comment"),
            ],
        ),
    },

    # ---- Product ----------------------------------------------------------
    {
        "key": "product_promo",
        "name": "Product Promo",
        "description": "Problem, product, proof, offer — four scenes for a square in-feed post.",
        "category": "product",
        "platform": "instagram_post",
        "sort_order": 110,
        "definition": _definition(
            music={'mood': 'uplifting', 'volume': 0.2, 'ducking': True},
            preview=_preview("#ec4899", ["#500724", "#831843"], "NEW IN", "split"),
            scenes=[
                _scene("Problem", 5.0, "cut", role="hook", media="footage",
                       prompt="Open with the problem your viewer has"),
                _scene("Product", 6.0, role="product", media="product",
                       prompt="Show the product solving it - no talking about it yet"),
                _scene("Proof", 5.0, role="proof", media="product",
                       prompt="Show the key benefit, or the proof somebody else believed it"),
                _scene("Offer", 3.0, role="cta", media="text-only",
                       prompt="End with a clear CTA - price, offer, or where to get it"),
            ],
        ),
    },
    {
        "key": "product_unboxing",
        "name": "Unboxing",
        "description": "Arrival, open, first look, verdict. Vertical, for Reels and TikTok.",
        "category": "product",
        "platform": "instagram_reels",
        "sort_order": 115,
        "definition": _definition(
            music=None,
            subtitle_style=subtitle_engine.preset("shorts"),
            preview=_preview("#ec4899", ["#831843", "#4c0519"], "UNBOXING", "caption-heavy"),
            scenes=[
                _scene("It arrived", 4.0, "cut", role="hook", media="product",
                       prompt="The box, before it is opened"),
                _scene("Opening it", 7.0, role="product", media="product",
                       prompt="Open it. Let the moment land before you speak"),
                _scene("First look", 6.0, role="proof", media="product",
                       prompt="First honest reaction - what surprised you"),
                _scene("Worth it?", 3.0, role="cta", media="speaker",
                       prompt="End with a clear CTA - your verdict, and where to get it"),
            ],
        ),
    },

    # ---- Documentary ------------------------------------------------------
    {
        "key": "documentary_segment",
        "name": "Documentary Segment",
        "description": "Slow cold open, context, two acts and a close. Lower-third captions.",
        "category": "documentary",
        "platform": "youtube",
        "sort_order": 120,
        "definition": _definition(
            music=None,
            subtitle_style=subtitle_engine.preset("clean"),
            preview=_preview("#a3a3a3", ["#1c1917", "#0c0a09"], "PART ONE", "lower-third"),
            layout={
                **deepcopy(DEFAULT_LAYOUT),
                "title": {"position": "lower", "size": "md", "align": "left", "max_lines": 2},
            },
            export_settings={"format": "mp4", "quality": "high", "burn_subtitles": False},
            scenes=[
                _scene("Cold open", 15.0, "cut", role="hook", media="b-roll",
                       animation="none", layout="lower",
                       prompt="Open in the middle of the story, before any context"),
                _scene("Context", 25.0, role="intro", media="b-roll", layout="lower",
                       prompt="Introduce the main idea - what the viewer needs to follow it"),
                _scene("Act one", 40.0, role="point", media="b-roll", layout="lower",
                       prompt="What happened, and what it cost"),
                _scene("Act two", 35.0, role="point", media="b-roll", layout="lower",
                       prompt="The turn - what changed"),
                _scene("Close", 10.0, role="outro", media="b-roll", layout="lower",
                       prompt="Land the meaning. End with a clear CTA if you want one"),
            ],
        ),
    },

    # ---- Storytelling -----------------------------------------------------
    {
        "key": "story_arc",
        "name": "Story Arc",
        "description": "Setup, turn, climax, resolution — the four beats a short story needs.",
        "category": "storytelling",
        "platform": "instagram_reels",
        "sort_order": 130,
        "definition": _definition(
            music={'mood': 'dramatic', 'volume': 0.22, 'ducking': True},
            subtitle_style=subtitle_engine.preset("shorts"),
            preview=_preview("#8b5cf6", ["#2e1065", "#1e1b4b"], "IT STARTED\nLIKE THIS", "quote"),
            scenes=[
                _scene("Setup", 6.0, "cut", role="hook", media="footage",
                       prompt="Where it started - one line, no preamble"),
                _scene("The turn", 8.0, role="point", media="footage",
                       prompt="What changed, and when you knew"),
                _scene("Climax", 8.0, role="proof", media="footage",
                       animation="pop", prompt="The moment it mattered"),
                _scene("Resolution", 5.0, role="cta", media="footage",
                       prompt="Where it left you. End with a clear CTA"),
            ],
        ),
    },

    # ---- Animated ---------------------------------------------------------
    {
        "key": "animated_kinetic",
        "name": "Kinetic Text",
        "description": "Word-by-word animated captions over a plain background. No footage needed.",
        "category": "animated",
        "platform": "youtube_shorts",
        "sort_order": 140,
        "definition": _definition(
            music={'mood': 'energetic', 'volume': 0.26, 'ducking': False},
            # Karaoke highlights one word at a time, which is what makes this
            # template work with no video behind it at all.
            subtitle_style=subtitle_engine.preset("karaoke"),
            preview=_preview("#84cc16", ["#1a2e05", "#365314"], "WORD BY WORD", "kinetic"),
            layout={
                **deepcopy(DEFAULT_LAYOUT),
                "title": {"position": "center", "size": "xl", "align": "center", "max_lines": 4},
            },
            export_settings={"format": "mp4", "quality": "high", "burn_subtitles": True},
            scenes=[
                _scene("Line 1", 4.0, "cut", role="hook", media="text-only",
                       animation="pop", prompt="Open with the problem your viewer has"),
                _scene("Line 2", 4.0, "cut", role="point", media="text-only",
                       animation="slide-up", prompt="Introduce the main idea"),
                _scene("Line 3", 4.0, "cut", role="point", media="text-only",
                       animation="slide-up", prompt="Show the key benefit"),
                _scene("Sign off", 3.0, "cut", role="cta", media="text-only",
                       animation="pop", prompt="End with a clear CTA"),
            ],
        ),
    },
)


def sync_system_templates(db: Session, *, commit: bool = True) -> int:
    """Insert or update the built-in templates. Returns how many changed.

    Idempotent, and safe on every boot. Matched by `key`, so renaming a
    template in code updates the row rather than leaving an orphan; a key that
    disappears from the list is left in the table rather than deleted, because
    a project may still name it and a missing template must not become a
    broken reference.
    """
    changed = 0
    for spec in SYSTEM_TEMPLATES:
        row = db.scalars(
            select(VideoTemplate).where(VideoTemplate.key == spec["key"])
        ).first()

        if row is None:
            row = VideoTemplate(key=spec["key"], is_system=True, user_id=None)
            db.add(row)
            changed += 1
        elif not row.is_system:
            # Somebody's own template happens to share this key. Leave it be —
            # overwriting a user's saved settings with ours would be worse than
            # one missing system template.
            logger.warning(
                "Skipping system template %r: a user template already owns that key",
                spec["key"],
            )
            continue
        else:
            changed += 1

        row.name = spec["name"]
        row.description = spec.get("description")
        row.category = spec.get("category", "other")
        row.platform = spec.get("platform", "youtube_shorts")
        row.sort_order = spec.get("sort_order", 100)
        row.definition = deepcopy(spec["definition"])
        row.is_system = True

        # The canvas comes from the platform preset so a template can never
        # disagree with the format it claims to be for.
        from app.services.video import presets

        preset = presets.get_preset(row.platform)
        row.aspect_ratio = preset.aspect_ratio
        row.width, row.height = presets.clamp_resolution(preset.width, preset.height)
        row.fps = preset.fps

    if commit:
        db.commit()
    return changed


def list_templates(
    db: Session,
    *,
    user_id: int,
    category: str | None = None,
    platform: str | None = None,
    search: str | None = None,
    owned_only: bool = False,
) -> list[VideoTemplate]:
    """The templates this user can start from: the system set plus their own.

    Another account's templates are never included — the filter is part of the
    query, the same rule projects follow.
    """
    query = select(VideoTemplate).where(
        (VideoTemplate.user_id.is_(None)) | (VideoTemplate.user_id == user_id)
    )
    if category:
        query = query.where(VideoTemplate.category == category)
    if platform:
        query = query.where(VideoTemplate.platform == platform)
    if search:
        # Per word, and across the category and platform too. "vertical
        # tiktok" is how somebody looks for a template; as one phrase over the
        # name alone it matches nothing, because no template is called that.
        for word in search.strip().lower().split()[:8]:
            pattern = f"%{word}%"
            query = query.where(
                or_(
                    func.lower(VideoTemplate.name).like(pattern),
                    func.lower(func.coalesce(VideoTemplate.description, "")).like(pattern),
                    func.lower(func.coalesce(VideoTemplate.category, "")).like(pattern),
                    func.lower(func.coalesce(VideoTemplate.platform, "")).like(pattern),
                )
            )
    if owned_only:
        query = query.where(VideoTemplate.user_id == user_id)

    return list(
        db.scalars(
            # A user's own templates sort above the system set at the same
            # `sort_order`. Somebody who saved a template did it to reuse it,
            # and making them scroll past twelve built-ins to find it is the
            # library forgetting whose screen it is.
            query.order_by(
                VideoTemplate.user_id.is_(None),
                VideoTemplate.sort_order,
                VideoTemplate.name,
            )
        ).all()
    )


def get_template(db: Session, *, user_id: int, key: str) -> VideoTemplate:
    """One template by key, if this user is allowed to see it."""
    template = db.scalars(
        select(VideoTemplate).where(
            VideoTemplate.key == key,
            (VideoTemplate.user_id.is_(None)) | (VideoTemplate.user_id == user_id),
        )
    ).first()
    if template is None:
        raise TemplateError("That template does not exist.")
    return template


def category_counts(db: Session, *, user_id: int) -> list[dict]:
    """The category tabs, with how many templates each holds for this user.

    Ordered by TEMPLATE_CATEGORIES rather than alphabetically, so the four
    surface categories stay at the front — see the note on that tuple. A
    category with nothing in it is omitted: an empty tab is a dead end, and the
    seeded set fills every one of them, so an empty category means a deployment
    where something is genuinely missing.
    """
    rows = db.execute(
        select(VideoTemplate.category, func.count(VideoTemplate.id))
        .where(
            (VideoTemplate.user_id.is_(None)) | (VideoTemplate.user_id == user_id)
        )
        .group_by(VideoTemplate.category)
    ).all()
    counts = {str(category): int(total or 0) for category, total in rows}

    ordered = [
        {
            "key": key,
            "label": CATEGORY_LABELS.get(key, key.title()),
            "count": counts.get(key, 0),
            "is_surface": key in SURFACE_CATEGORIES,
        }
        for key in TEMPLATE_CATEGORIES
        if counts.get(key, 0) > 0
    ]

    # A category somebody's own template invented, which the tuple does not
    # know about. Appended rather than dropped — the row exists, so the tab
    # that reaches it has to.
    for key, total in sorted(counts.items()):
        if key not in TEMPLATE_CATEGORIES and total > 0:
            ordered.append(
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "count": total,
                    "is_surface": False,
                }
            )

    return ordered


# ---------------------------------------------------------------------------
# User templates
# ---------------------------------------------------------------------------

_SLUG = re.compile(r"[^a-z0-9]+")

# How many templates one account may save. Not a billing limit — it is what
# stops a runaway client turning the shared `key` namespace into a landfill.
MAX_USER_TEMPLATES = 50


def _user_key(db: Session, user_id: int, name: str) -> str:
    """A unique key for a saved template.

    Namespaced with the user id because `key` is unique across the whole table:
    without it, the first person to save "Product Promo" would take a name away
    from everybody else, including from the system set.
    """
    stem = _SLUG.sub("-", (name or "").lower()).strip("-")[:40] or "template"
    base = f"u{user_id}-{stem}"

    candidate = base
    suffix = 2
    while db.scalars(
        select(VideoTemplate.id).where(VideoTemplate.key == candidate)
    ).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
        if suffix > 200:  # pragma: no cover — a runaway loop guard, not a path
            raise TemplateError("Could not find a free name for that template.")

    return candidate


def save_user_template(
    db: Session,
    *,
    user_id: int,
    project: VideoProject,
    name: str,
    description: str | None = None,
    category: str | None = None,
    include_scenes: bool = True,
) -> VideoTemplate:
    """Save a project's setup as a template of this user's own.

    **Configuration only.** The canvas, the caption style, the layout, the
    brand and export choices, and — if asked for — the shape of the scenes:
    their titles, durations and transitions. Never the scenes' *text*, never
    the media, never a rendered frame. A template is how the next video is set
    up, and copying this video's script into it would make every project made
    from it a copy of this one.

    That is also why nothing here references an asset. A template that pointed
    at a clip would break the day that clip was deleted, and would quietly
    share one file across every project made from it.
    """
    if project.user_id != user_id:
        raise TemplateError("That project belongs to a different account.")

    cleaned = (name or "").strip()
    if not cleaned:
        raise TemplateError("Give the template a name.")

    existing = db.scalar(
        select(func.count(VideoTemplate.id)).where(VideoTemplate.user_id == user_id)
    )
    if int(existing or 0) >= MAX_USER_TEMPLATES:
        raise TemplateError(
            f"You have {MAX_USER_TEMPLATES} saved templates, which is the limit. "
            f"Delete one to save another."
        )

    scenes: list[dict] = []
    if include_scenes:
        rows = db.scalars(
            select(VideoScene)
            .where(VideoScene.project_id == project.id)
            .order_by(VideoScene.position, VideoScene.id)
        ).all()
        scenes = [
            _scene(
                scene.title or f"Scene {index + 1}",
                float(scene.duration_seconds or 5.0),
                scene.transition or "fade",
            )
            for index, scene in enumerate(rows)
        ]

    subtitle_style = subtitle_engine.preset(subtitle_engine.DEFAULT_PRESET)
    track = db.scalars(
        select(VideoSubtitle)
        .where(VideoSubtitle.project_id == project.id)
        .order_by(VideoSubtitle.id)
    ).first()
    if track is not None and track.style:
        subtitle_style = deepcopy(track.style)

    definition = _definition(
        scenes=scenes,
        subtitle_style=subtitle_style,
        # The timeline is reset rather than copied. It references this
        # project's clips by id, and carrying those ids into a template would
        # produce a new project whose timeline points at somebody's else's
        # scenes — or at nothing.
        timeline=deepcopy(EMPTY_TIMELINE),
        brand=deepcopy(project.brand or {}) or {"apply": True},
        export_settings=deepcopy(project.export_settings or {})
        or {"format": "mp4", "quality": "high", "burn_subtitles": True},
        layout=deepcopy((project.brand or {}).get("layout") or DEFAULT_LAYOUT),
        preview=_preview("#10b981", ["#0f2f26", "#0b1f1a"], cleaned.upper()[:18], "saved"),
    )

    template = VideoTemplate(
        key=_user_key(db, user_id, cleaned),
        user_id=user_id,
        name=cleaned[:120],
        description=(description or "").strip()[:500] or None,
        category=(category or project.project_type or "other").lower()[:40],
        platform=project.platform,
        aspect_ratio=project.aspect_ratio,
        width=project.width,
        height=project.height,
        fps=project.fps,
        definition=definition,
        is_system=False,
        # Behind every system template by default, which is what `sort_order`
        # 10–140 leaves room for. The list query already floats a user's own
        # templates to the top, so this only orders them against each other.
        sort_order=200,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    logger.info(
        "User %s saved template %r from project %s", user_id, template.key, project.id
    )
    return template


def delete_user_template(db: Session, *, user_id: int, key: str) -> None:
    """Delete one of this user's own templates.

    A system template is refused rather than hidden: it is shared, and one
    account deleting it would take it out of everybody's library.

    Projects created from this template keep working. `template_key` on a
    project is a record of where it came from, not a live reference — see the
    model docstring.
    """
    template = db.scalars(
        select(VideoTemplate).where(VideoTemplate.key == key)
    ).first()
    if template is None:
        raise TemplateError("That template does not exist.")
    if template.is_system or template.user_id != user_id:
        raise TemplateError("Built-in templates cannot be deleted.")

    db.delete(template)
    db.commit()
