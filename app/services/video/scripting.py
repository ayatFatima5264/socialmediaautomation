"""AI script generation — the first step of the AI video pipeline.

    topic ──▶ SCRIPT ──▶ scenes ──▶ voice ──▶ visuals ──▶ subtitles ──▶ music
                                                                          │
                                              timeline editor ◀── project ┘

**The output is a document the user owns, not a black box.** A script is a
plain dict on `VideoProject.script` with five named parts — hook, introduction,
main points, ending, CTA — each a separately editable string. Nothing about it
is opaque: the editor can rewrite one main point, or all of it, and
regeneration is a *replacement of that document*, not a different mode the
project is in. That is what "everything must remain editable" means
structurally rather than as a promise.

**The provider stays replaceable.** Generation goes through the existing
`AIProvider` contract (`app/services/providers`) — the same abstraction the
post composer uses, with the same fallback chain. This module contributes a
prompt and a parser; it does not know which model answered, and a new provider
is a line in that factory, not a change here.

**Length is arithmetic, not a request.** Models are unreliable at "make this 30
seconds long", so the target duration is converted to a word budget at a
measured speaking rate and enforced on the way out — the script is trimmed or
the shortfall is reported. Asking politely and hoping is how a "30-second"
video renders at 1:10.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.config import settings
from app.services.providers.base import AIProvider, ProviderError
from app.services.providers.factory import get_provider

logger = logging.getLogger(__name__)

SCRIPT_VERSION = 1


class ScriptError(RuntimeError):
    """A script could not be generated. The message is user-facing."""


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------
# Served to the UI through `/api/video/ai/options` rather than duplicated in
# JavaScript, the same rule the subtitle style panel follows: the generator has
# to understand every value the form can produce.

TONES = (
    "professional",
    "friendly",
    "energetic",
    "inspirational",
    "educational",
    "humorous",
    "dramatic",
    "calm",
)

CONTENT_TYPES = (
    "educational",
    "promotional",
    "storytelling",
    "listicle",
    "tutorial",
    "testimonial",
    "announcement",
    "entertainment",
)

# How the video will be *shown*, which changes what the script should be like.
# A kinetic-typography video has no footage to carry it, so its lines have to
# be shorter and land harder; a natural one can let a shot breathe.
VISUAL_MODES = ("natural", "animated")

# Mirrors `voice.FEATURED_LANGUAGES` so a script and its voice-over can be in
# the same language. A language here with no voice behind it would produce a
# script nobody can narrate.
LANGUAGES = (
    {"code": "en-US", "label": "English (US)"},
    {"code": "en-GB", "label": "English (UK)"},
    {"code": "ur-PK", "label": "Urdu"},
    {"code": "hi-IN", "label": "Hindi"},
    {"code": "ar-SA", "label": "Arabic"},
)

LANGUAGE_CODES = tuple(entry["code"] for entry in LANGUAGES)

# Words per second of finished narration, by language.
#
# These are speaking rates, not reading rates — the difference matters, because
# a script sized by reading speed comes out roughly a third too long. English
# conversational narration sits around 150 wpm (2.5 w/s); Urdu, Hindi and
# Arabic carry more meaning per word and are read slower in practice.
WORDS_PER_SECOND = {
    "en": 2.5,
    "ur": 2.0,
    "hi": 2.0,
    "ar": 1.9,
}
DEFAULT_WORDS_PER_SECOND = 2.3

# What a script is allowed to be. Below the floor there is nothing to make a
# video out of; above the ceiling the render caps would refuse it anyway, so
# refusing here gives the user the reason before they wait for a generation.
MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 600

# How many main points to ask for, by length. Deliberately few: the most common
# failure of an AI script is six shallow points where three developed ones
# would have held attention.
def points_for(duration_seconds: float) -> int:
    if duration_seconds <= 20:
        return 1
    if duration_seconds <= 45:
        return 2
    if duration_seconds <= 90:
        return 3
    if duration_seconds <= 180:
        return 4
    return 5


def words_per_second(language: str) -> float:
    return WORDS_PER_SECOND.get((language or "en")[:2].lower(), DEFAULT_WORDS_PER_SECOND)


def word_budget(duration_seconds: float, language: str) -> int:
    """How many words of narration fit in this many seconds."""
    return max(12, int(duration_seconds * words_per_second(language)))


def count_words(text: object) -> int:
    """Words in a spoken part.

    Takes `object` rather than `str` because a script document arrives from the
    client, where a field can be anything JSON allows. Coercing here keeps a
    malformed document a validation problem instead of an AttributeError three
    frames down.
    """
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return len([word for word in re.split(r"\s+", text.strip()) if word])


def script_words(script: dict) -> int:
    """Total narration in a script — every part that is actually spoken.

    The CTA counts; a heading does not. Headings are labels for the editor's
    benefit and are never read aloud, so counting them would make every script
    come out short of its own budget.
    """
    raw_points = script.get("main_points")
    if not isinstance(raw_points, list):
        raw_points = []

    parts = [
        script.get("hook", ""),
        script.get("introduction", ""),
        # A point that is not an object has no narration to count. Skipping it
        # rather than trusting the shape matters because this runs on documents
        # the client sent — the save and the section rewrite both land here, and
        # a bad shape used to surface as a 500 instead of a validation error.
        *[
            point.get("text", "")
            for point in raw_points
            if isinstance(point, dict)
        ],
        script.get("ending", ""),
        script.get("cta", ""),
    ]
    return sum(count_words(part) for part in parts)


# A script is five short spoken parts. These caps are far above anything a real
# one needs and exist only so a project's script column cannot become somewhere
# to park megabytes: the document is stored as JSON on the row, and nothing else
# bounds what a client sends to the save endpoint.
MAX_SECTION_CHARS = 5000
MAX_HEADING_CHARS = 200
MAX_POINTS = 50
MAX_KEYWORDS = 16
MAX_KEYWORD_CHARS = 60

# What a script document is allowed to contain. Anything else a client sends is
# dropped rather than stored: `ScriptDocument` already ignores unknown keys on
# the way out, so keeping them only grows the row with data nothing can read.
DOCUMENT_KEYS = (
    "version",
    "brief",
    "title",
    "hook",
    "introduction",
    "main_points",
    "ending",
    "cta",
    "keywords",
    "estimated_seconds",
    "fits_budget",
    "generated_at",
)


def sanitize_points(value: object) -> list[dict]:
    """`main_points` coerced into the shape the rest of the code assumes.

    Structure and length only — the words are left exactly as they are within
    the cap. A user's manual edit must survive a save, so this is not
    `normalize_script`, which strips markdown and parentheticals and would
    quietly rewrite text a person typed on purpose.
    """
    if not isinstance(value, list):
        return []

    points: list[dict] = []
    for index, point in enumerate(value[:MAX_POINTS], start=1):
        if isinstance(point, dict):
            text = point.get("text")
            heading = point.get("heading")
            identifier = point.get("id")
        else:
            # A bare string is the one non-object shape worth rescuing: it is
            # what a hand-written script or a sloppy client sends.
            text, heading, identifier = point, "", ""
        points.append(
            {
                "id": str(identifier or f"p{index}")[:40],
                "heading": ("" if heading is None else str(heading))[:MAX_HEADING_CHARS],
                "text": ("" if text is None else str(text))[:MAX_SECTION_CHARS],
            }
        )
    return points


def sanitize_document(script: dict) -> dict:
    """A script document made valid in shape and bounded in size.

    The user's words are preserved as typed, within the caps. What is dropped is
    only what a script document is not: unknown keys, and anything past a limit
    no real script comes close to.
    """
    if not isinstance(script, dict):
        return {"main_points": [], "keywords": []}

    clean = {key: script[key] for key in DOCUMENT_KEYS if key in script}
    clean["main_points"] = sanitize_points(script.get("main_points"))

    for key in ("title", "hook", "introduction", "ending", "cta"):
        if key in clean:
            value = clean[key]
            text = "" if value is None else str(value)
            clean[key] = text[:MAX_SECTION_CHARS]

    keywords = clean.get("keywords")
    if not isinstance(keywords, list):
        clean["keywords"] = []
    else:
        clean["keywords"] = [
            str(word)[:MAX_KEYWORD_CHARS]
            for word in keywords[:MAX_KEYWORDS]
            if word is not None
        ]

    if not isinstance(clean.get("brief"), dict):
        clean.pop("brief", None)

    return clean


def estimated_duration(script: dict) -> float:
    """How long this script will take to narrate, in seconds."""
    language = (script.get("brief") or {}).get("language") or "en-US"
    return round(script_words(script) / words_per_second(language), 1)


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a video scriptwriter for short-form social video. You write "
    "narration that is spoken aloud, not prose that is read. Short sentences. "
    "Concrete nouns. No stage directions, no camera notes, no emoji, no "
    "markdown, and never a line like 'In this video we will'. "
    "Return only the JSON object you are asked for."
)


def _brief_lines(brief: dict) -> list[str]:
    """The brief, as the lines the model is actually given.

    Every field the form collects appears here. A field the UI asks for and the
    prompt drops is a control that does nothing, which is worse than not
    offering it.
    """
    lines = [
        f"TOPIC: {brief['topic']}",
        f"LANGUAGE: write entirely in {brief['language_label']}.",
        f"TONE: {brief['tone']}",
        f"AUDIENCE: {brief['audience']}",
        f"PLATFORM: {brief['platform_label']}",
        f"CONTENT TYPE: {brief['content_type']}",
        f"TARGET LENGTH: {brief['duration_seconds']:.0f} seconds of narration, "
        f"which is about {brief['word_budget']} words IN TOTAL across every "
        f"section. This is a hard budget, not a suggestion.",
    ]

    if brief["visual_mode"] == "animated":
        lines.append(
            "VISUAL STYLE: animated text and motion graphics — there is no "
            "footage. Every line has to work on its own on screen, so keep "
            "sentences short and punchy."
        )
    else:
        lines.append(
            "VISUAL STYLE: real footage and photography behind the narration."
        )

    if brief.get("instructions"):
        lines.append(f"EXTRA INSTRUCTIONS FROM THE USER: {brief['instructions']}")

    return lines


def build_prompt(brief: dict) -> str:
    points = brief["main_point_count"]
    return "\n".join(
        [
            *_brief_lines(brief),
            "",
            f"Write the script with exactly {points} main "
            f"point{'s' if points != 1 else ''}.",
            "",
            "Return ONLY this JSON object:",
            "{",
            '  "title": "a short title for the video",',
            '  "hook": "the first line, said in under 3 seconds, that stops the scroll",',
            '  "introduction": "one or two sentences setting up what follows",',
            '  "main_points": [',
            '    {"heading": "a 2-4 word label for the editor", '
            '"text": "what is said for this point"}',
            "  ],",
            '  "ending": "the line that closes the idea",',
            '  "cta": "one short call to action",',
            '  "keywords": ["3-6 words describing the subject, for finding visuals"]',
            "}",
        ]
    )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _clean(value: object, limit: int = 2000) -> str:
    """One field of model output, as a plain spoken line.

    Strips the markdown and the stage directions models add regardless of
    being told not to. This runs on every field because narration with a stray
    `**` in it is narration a TTS engine will read aloud as "asterisk".
    """
    text = str(value or "").strip()
    text = re.sub(r"[*_`#]+", "", text)
    # "(upbeat music)" / "[cut to wide shot]" — direction, not narration.
    text = re.sub(r"\[[^\]]{0,80}\]|\([^)]{0,80}\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def normalize_script(data: dict, brief: dict) -> dict:
    """A model response as the script document, complete and in range.

    Missing parts become empty strings rather than absent keys: the editor
    renders a field per part, and a key that is sometimes there is a field that
    sometimes disappears.
    """
    raw_points = data.get("main_points")
    points: list[dict] = []
    if isinstance(raw_points, list):
        for index, point in enumerate(raw_points):
            if isinstance(point, dict):
                heading = _clean(point.get("heading"), 120)
                text = _clean(point.get("text"))
            else:
                heading, text = "", _clean(point)
            if not text:
                continue
            points.append(
                {
                    "id": f"p{index + 1}",
                    "heading": heading or f"Point {index + 1}",
                    "text": text,
                }
            )

    keywords = data.get("keywords")
    if not isinstance(keywords, list):
        keywords = []
    keywords = [_clean(word, 40) for word in keywords][:8]
    keywords = [word for word in keywords if word]

    return {
        "version": SCRIPT_VERSION,
        "brief": brief,
        "title": _clean(data.get("title"), 200) or brief["topic"][:200],
        "hook": _clean(data.get("hook")),
        "introduction": _clean(data.get("introduction")),
        "main_points": points,
        "ending": _clean(data.get("ending")),
        "cta": _clean(data.get("cta")),
        # Not narration — what the visual search and the image prompts start
        # from. Kept on the script so regenerating visuals does not need the
        # model again.
        "keywords": keywords or [brief["topic"]],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_brief(
    *,
    topic: str,
    language: str = "en-US",
    tone: str = "friendly",
    audience: str = "a general audience",
    duration_seconds: float = 30.0,
    platform: str = "youtube_shorts",
    content_type: str = "educational",
    instructions: str | None = None,
    visual_mode: str = "natural",
) -> dict:
    """Validate and complete the inputs. Raises ScriptError for a bad brief."""
    topic = (topic or "").strip()
    if len(topic) < 3:
        raise ScriptError("Give the video a topic to write about.")

    if not (MIN_DURATION_SECONDS <= duration_seconds <= MAX_DURATION_SECONDS):
        raise ScriptError(
            f"Pick a length between {MIN_DURATION_SECONDS} seconds and "
            f"{MAX_DURATION_SECONDS // 60} minutes."
        )

    language = language if language in LANGUAGE_CODES else "en-US"
    language_label = next(
        entry["label"] for entry in LANGUAGES if entry["code"] == language
    )

    from app.services.video import presets

    preset = presets.get_preset(platform)

    return {
        "topic": topic[:300],
        "language": language,
        "language_label": language_label,
        "tone": tone if tone in TONES else "friendly",
        "audience": (audience or "a general audience").strip()[:200],
        "duration_seconds": float(duration_seconds),
        "platform": preset.key,
        "platform_label": preset.label,
        "content_type": content_type if content_type in CONTENT_TYPES else "educational",
        "instructions": (instructions or "").strip()[:1000] or None,
        "visual_mode": visual_mode if visual_mode in VISUAL_MODES else "natural",
        "word_budget": word_budget(duration_seconds, language),
        "main_point_count": points_for(duration_seconds),
    }


async def generate_script(brief: dict, *, provider: AIProvider | None = None) -> dict:
    """Write a script for a brief.

    `provider` is injectable so a test can run the whole pipeline without a
    network call and so a caller can pin a model; left out, the configured
    chain with its fallbacks is used.
    """
    client = provider or get_provider()

    try:
        raw = await client.complete(
            system=_SYSTEM,
            user=build_prompt(brief),
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
            json_mode=True,
            context={"feature": "video_script", "topic": brief["topic"]},
        )
    except ProviderError as exc:
        raise ScriptError(f"The script could not be generated: {exc}") from exc

    from app.services.ai_service import _parse_json

    data = _parse_json(raw)
    if not isinstance(data, dict):
        raise ScriptError("The script generator returned something unusable.")

    script = normalize_script(data, brief)

    if not script["hook"] and not script["main_points"]:
        raise ScriptError(
            "The script generator returned nothing usable. Try again, or "
            "reword the topic."
        )

    return fit_to_budget(script)


# ---------------------------------------------------------------------------
# Regenerating one section
# ---------------------------------------------------------------------------
# Rewriting the whole script to fix a weak hook throws away every other line the
# user had already accepted — and the lines they kept are usually the reason
# they stayed. So a section can be rewritten on its own, with the rest of the
# script sent as context the model is told not to touch, which is what keeps the
# replacement part of the same piece rather than a good line from a different
# script.

REGENERABLE_SECTIONS = ("title", "hook", "introduction", "ending", "cta", "point")

_SECTION_ASKS = {
    "title": "the title — a short label for the video, not a sentence",
    "hook": "the first line, said in under 3 seconds, that stops the scroll",
    "introduction": "the one or two sentences that set up what follows",
    "ending": "the line that closes the idea",
    "cta": "the call to action — one short line",
}


def find_point(script: dict, point_id: str) -> dict | None:
    for point in script.get("main_points") or []:
        if isinstance(point, dict) and point.get("id") == point_id:
            return point
    return None


def _script_as_text(script: dict, *, skip: str = "", skip_point: str = "") -> str:
    """The script as the model should see it: labelled, in running order.

    The section being rewritten is left out — including it invites the model to
    hand back a lightly reworded copy of the line the user just rejected.
    """
    parts: list[str] = []
    if script.get("title") and skip != "title":
        parts.append(f"TITLE: {script['title']}")
    if script.get("hook") and skip != "hook":
        parts.append(f"HOOK: {script['hook']}")
    if script.get("introduction") and skip != "introduction":
        parts.append(f"INTRODUCTION: {script['introduction']}")
    for index, point in enumerate(script.get("main_points") or [], start=1):
        if not isinstance(point, dict):
            continue
        if skip == "point" and point.get("id") == skip_point:
            continue
        heading = point.get("heading") or f"Point {index}"
        parts.append(f"MAIN POINT {index} ({heading}): {point.get('text') or ''}")
    if script.get("ending") and skip != "ending":
        parts.append(f"ENDING: {script['ending']}")
    if script.get("cta") and skip != "cta":
        parts.append(f"CALL TO ACTION: {script['cta']}")
    return "\n".join(parts)


def build_section_prompt(
    brief: dict, script: dict, section: str, *, point_id: str = ""
) -> str:
    if section == "point":
        point = find_point(script, point_id)
        if point is None:
            raise ScriptError("That main point is no longer in the script.")
        current = str(point.get("text") or "")
        ask = f"main point {point.get('heading') or point_id} — the words spoken for it"
    else:
        current = str(script.get(section) or "")
        ask = _SECTION_ASKS[section]

    # Match the length of what is being replaced, so rewriting one line does
    # not quietly blow the duration budget the rest of the script was fitted to.
    words = count_words(current)
    if words < 3:
        share = max(1, brief["main_point_count"] + 4)
        words = max(6, brief["word_budget"] // share)

    context_text = _script_as_text(script, skip=section, skip_point=point_id)

    lines = [
        *_brief_lines(brief),
        "",
        "THE REST OF THE SCRIPT. Do not rewrite any of it. The new text has to "
        "sit inside it without repeating a line that is already there:",
        context_text or "(nothing else is written yet)",
        "",
        f"Rewrite ONLY {ask}.",
        f"Aim for about {words} words.",
        "It must say something different from the current version:",
        f"CURRENT: {current or '(empty)'}",
        "",
        "Return ONLY this JSON object:",
        "{",
    ]
    if section == "point":
        lines += [
            '  "heading": "a 2-4 word label for the editor",',
            '  "text": "what is said for this point"',
        ]
    else:
        lines += ['  "text": "the rewritten section"']
    lines += ["}"]
    return "\n".join(lines)


async def regenerate_section(
    brief: dict,
    script: dict,
    section: str,
    *,
    point_id: str = "",
    provider: AIProvider | None = None,
) -> dict:
    """Rewrite one part of a script and return the whole updated document.

    The document comes back rather than the fragment, so the caller saves the
    same shape it saves after any other edit and the recomputed duration is
    never a separate step somebody can forget.
    """
    if section not in REGENERABLE_SECTIONS:
        raise ScriptError(f"“{section}” is not a part of the script that can be rewritten.")

    # The document came from the client, so make it structurally sound before
    # anything reads it as though it were the shape this module produces.
    script = sanitize_document(script)

    prompt = build_section_prompt(brief, script, section, point_id=point_id)
    client = provider or get_provider()

    try:
        raw = await client.complete(
            system=_SYSTEM,
            user=prompt,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
            json_mode=True,
            context={
                "feature": "video_script_section",
                "topic": brief["topic"],
                "section": section,
            },
        )
    except ProviderError as exc:
        raise ScriptError(f"That section could not be rewritten: {exc}") from exc

    from app.services.ai_service import _parse_json

    data = _parse_json(raw)
    if not isinstance(data, dict):
        raise ScriptError("The generator returned something unusable.")

    text = _clean(data.get("text"))
    if not text:
        raise ScriptError("The generator returned an empty section. Try again.")

    updated = dict(script)
    if section == "point":
        points = [dict(row) for row in (script.get("main_points") or []) if isinstance(row, dict)]
        for point in points:
            if point.get("id") == point_id:
                point["text"] = text
                heading = _clean(data.get("heading"), 120)
                if heading:
                    point["heading"] = heading
                break
        updated["main_points"] = points
    else:
        updated[section] = text

    updated["estimated_seconds"] = estimated_duration(updated)
    target = (updated.get("brief") or {}).get("duration_seconds") or 0
    updated["fits_budget"] = not target or updated["estimated_seconds"] <= target * 1.15
    return updated


def fit_to_budget(script: dict) -> dict:
    """Trim a script that overran its word budget, longest part first.

    Models overshoot a stated length routinely, and an overlong script is not a
    cosmetic problem: it becomes a video that is half again as long as the user
    asked for, on a platform where that matters.

    Trimming happens at sentence boundaries and only on the *main points* —
    the hook, the ending and the CTA are load-bearing and short, and cutting
    them mid-thought to save four words produces a worse video than one that
    runs a little long. A script still over budget after that is reported as
    such rather than mangled.
    """
    brief = script.get("brief") or {}
    budget = int(brief.get("word_budget") or 0)
    if budget <= 0:
        return script

    # A tolerance band, and it is not slack for its own sake. The budget is
    # itself an estimate (a speaking rate applied to a word count), and the
    # smallest thing that can be cut is a whole sentence — so trimming to the
    # exact number means routinely dropping fifteen words to save four. That
    # overshoot is visible in the result: two main points written to the same
    # length come out at 4 seconds and 11, and the video looks lopsided for no
    # reason the user can see.
    tolerance = max(4, int(budget * 0.10))

    overrun = script_words(script) - budget
    if overrun <= tolerance:
        script["fits_budget"] = True
        script["estimated_seconds"] = estimated_duration(script)
        return script

    points = script.get("main_points") or []
    # Longest first, so the cut lands where there is most to lose.
    order = sorted(
        range(len(points)), key=lambda i: count_words(points[i]["text"]), reverse=True
    )

    for index in order:
        if overrun <= tolerance:
            break
        sentences = re.split(r"(?<=[.!?])\s+", points[index]["text"])
        # Stop at the tolerance rather than at zero: one sentence past the
        # line is what the band exists to absorb.
        while len(sentences) > 1 and overrun > tolerance:
            dropped = sentences.pop()
            overrun -= count_words(dropped)
        points[index]["text"] = " ".join(sentences).strip()

    script["estimated_seconds"] = estimated_duration(script)
    script["fits_budget"] = script["estimated_seconds"] <= (
        brief.get("duration_seconds") or 0
    ) * 1.15
    return script


def options() -> dict:
    """Everything the "new AI video" form needs to build itself."""
    return {
        "tones": list(TONES),
        "content_types": list(CONTENT_TYPES),
        "visual_modes": list(VISUAL_MODES),
        "languages": [dict(entry) for entry in LANGUAGES],
        "duration_range": [MIN_DURATION_SECONDS, MAX_DURATION_SECONDS],
        "default_duration": 30,
    }
