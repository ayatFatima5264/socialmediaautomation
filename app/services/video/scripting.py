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

**Past a few minutes, one call is not enough.** A half-hour script is roughly
4,500 words, several times what any provider will return in one response, and
the failure is silent: the model writes a third of it and stops, or compresses
the whole thing into something that reads at four minutes. So long scripts are
written the way a person writes one — an outline pass, then the chapters, a few
at a time and concurrently. Same document out; see `generate_long_form`.
"""
from __future__ import annotations

import asyncio
import logging
import math
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
# video out of; the ceiling is a half-hour talk, which at a speaking rate is
# roughly 4,500 words — long enough for a webinar or a YouTube explainer, and
# far enough short of "a book" that the generation still finishes in a request.
#
# This ceiling is about the *script*. Rendering a video is a separate, much
# lower limit (`settings.video_max_duration_seconds`), and it has its own
# refusal with its own reason — see `projects.render_refusal`.
MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 1800

# Past this length one model call cannot write the whole thing: 4,500 words is
# several times any provider's per-response token ceiling, and asking for it
# anyway returns a script that stops mid-sentence at the halfway mark. Above the
# line the script is written in passes — an outline first, then the chapters.
LONG_FORM_SECONDS = 240

# How many words one long-form call is asked for. Small enough to finish inside
# `ai_request_timeout`, large enough that a half-hour script is six calls rather
# than twenty-four.
CHAPTER_BATCH_WORDS = 700

# How many of those calls are in flight at once. Free provider tiers are rate
# limited per minute, so this is deliberately modest — it is the difference
# between a 20-second wait and a 60-second one, not between working and not.
MAX_CONCURRENT_BATCHES = 3

# The most chapters a script is cut into, whatever its length. Past this the
# editor becomes a list nobody scrolls, and each chapter gets too little to say.
MAX_MAIN_POINTS = 24

# The longest script that can be turned into a video *project*. Lower than
# `MAX_DURATION_SECONDS` because a project is a scene, a visual and a voice-over
# per beat — a different order of cost from a page of text — and lower still is
# `settings.video_max_duration_seconds`, which is what may actually be rendered.
MAX_PROJECT_SECONDS = 600


# How many main points to ask for, by length. Deliberately few at short lengths:
# the most common failure of an AI script is six shallow points where three
# developed ones would have held attention. Long form is the opposite problem —
# a 20-minute video with five points is five ten-minute monologues — so past
# five minutes a new chapter is added roughly every 90 seconds.
def points_for(duration_seconds: float) -> int:
    if duration_seconds <= 20:
        return 1
    if duration_seconds <= 45:
        return 2
    if duration_seconds <= 90:
        return 3
    if duration_seconds <= 180:
        return 4
    if duration_seconds <= 300:
        return 5
    return min(MAX_MAIN_POINTS, 5 + math.ceil((duration_seconds - 300) / 90))


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

# The same writer, given a length where the short-form instincts stop helping.
# A twenty-minute script written in scroll-stopping one-liners is exhausting;
# what holds attention at that length is examples, numbers and a thread that
# carries from one chapter to the next.
_SYSTEM_LONG = (
    "You are a video scriptwriter for long-form video — explainers, talks and "
    "tutorials that run for many minutes. You write narration that is spoken "
    "aloud, not prose that is read. You develop an idea with concrete examples, "
    "numbers and short stories rather than restating it, and you never pad. No "
    "stage directions, no camera notes, no emoji, no markdown, and never a line "
    "like 'In this video we will'. Return only the JSON object you are asked for."
)


def is_long_form(brief: dict) -> bool:
    """Whether this script has to be written in passes rather than one call."""
    return float(brief.get("duration_seconds") or 0) > LONG_FORM_SECONDS


def _system_for(brief: dict) -> str:
    return _SYSTEM_LONG if is_long_form(brief) else _SYSTEM


def _max_tokens_for(words: int) -> int:
    """A response ceiling sized to what was actually asked for.

    `ai_max_tokens` is set for a social post — around 750 words, which is fine
    for a two-minute script and silently truncates a ten-minute one. So it acts
    as the floor here, not the value: the ask is the word count plus room for
    the JSON around it, and non-Latin scripts (Urdu, Arabic) that tokenize
    several times worse per word.
    """
    return max(settings.ai_max_tokens, min(8000, int(words * 2.6) + 500))


def _brief_lines(brief: dict, *, total_budget: bool = True) -> list[str]:
    """The brief, as the lines the model is actually given.

    Every field the form collects appears here. A field the UI asks for and the
    prompt drops is a control that does nothing, which is worse than not
    offering it.

    `total_budget` is off when the call is writing one part of a longer script:
    telling a model that is producing 700 words of chapter three that the whole
    thing is 4,500 words invites it to write the whole thing.
    """
    lines = [
        f"TOPIC: {brief['topic']}",
        f"LANGUAGE: write entirely in {brief['language_label']}.",
        f"TONE: {brief['tone']}",
        f"AUDIENCE: {brief['audience']}",
        f"PLATFORM: {brief['platform_label']}",
        f"CONTENT TYPE: {brief['content_type']}",
    ]

    if total_budget:
        lines.append(
            f"TARGET LENGTH: {brief['duration_seconds']:.0f} seconds of narration, "
            f"which is about {brief['word_budget']} words IN TOTAL across every "
            f"section. This is a hard budget, not a suggestion."
        )
    else:
        lines.append(
            f"THE FINISHED VIDEO: about {brief['duration_seconds'] / 60:.0f} "
            f"minutes long. You are writing one part of it, not the whole thing."
        )

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
                text = _clean(point.get("text"), MAX_SECTION_CHARS)
            else:
                heading, text = "", _clean(point, MAX_SECTION_CHARS)
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

    Anything past `LONG_FORM_SECONDS` goes the other way — see
    `generate_long_form`. One call cannot write half an hour of narration.
    """
    client = provider or get_provider()

    if is_long_form(brief):
        return await generate_long_form(brief, client)

    try:
        raw = await client.complete(
            system=_SYSTEM,
            user=build_prompt(brief),
            max_tokens=_max_tokens_for(brief["word_budget"]),
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
# Long form — a script written in passes
# ---------------------------------------------------------------------------
# A half-hour video is about 4,500 words of narration. No provider will return
# that in one response, and the failure is not an error: the model writes the
# first third at the right quality and then stops, or compresses the whole thing
# into a summary that reads at four minutes. Either way the user asked for
# twenty minutes and got five.
#
# So long scripts are written the way a person writes one:
#
#   1. an OUTLINE pass  — the title, the framing lines, and a heading plus a
#      one-line summary for every chapter. Cheap, and it is what makes the
#      chapters belong to the same video instead of being N essays on a theme.
#   2. CHAPTER passes   — the actual narration, a few chapters at a time, each
#      call given the whole outline as context so it knows what the chapters
#      around it already cover and does not repeat them.
#
# The chapter passes are independent once the outline exists, so they run
# concurrently. That is the difference between a twenty-second wait and a minute
# and a half.


def framing_and_chapter_words(brief: dict) -> tuple[int, list[int]]:
    """Split the word budget into framing and one number per chapter.

    Not proportionally: a half-hour video still opens with a three-second hook
    and closes with a one-line CTA. Framing takes a small, capped share and the
    body gets everything else — otherwise a 4,500-word budget produces a
    360-word "hook".
    """
    count = max(1, int(brief["main_point_count"]))
    budget = max(1, int(brief["word_budget"]))

    framing = max(60, min(220, int(budget * 0.08)))
    body = max(count * 40, budget - framing)

    base, extra = divmod(body, count)
    return framing, [base + (1 if index < extra else 0) for index in range(count)]


def batch_chapters(words: list[int]) -> list[list[int]]:
    """Group chapter indexes into the calls that will write them.

    Consecutive, so a batch is a run of the video rather than a scatter — the
    model writing chapters 5–8 can carry a thread through them. Each batch stops
    at `CHAPTER_BATCH_WORDS`, which is what keeps one call inside the provider's
    response ceiling and the request timeout.
    """
    batches: list[list[int]] = []
    current: list[int] = []
    total = 0

    for index, count in enumerate(words):
        if current and total + count > CHAPTER_BATCH_WORDS:
            batches.append(current)
            current, total = [], 0
        current.append(index)
        total += count

    if current:
        batches.append(current)
    return batches


def build_outline_prompt(brief: dict, framing_words: int, chapter_words: list[int]) -> str:
    count = len(chapter_words)
    return "\n".join(
        [
            *_brief_lines(brief),
            "",
            f"This is a long video, so plan it before writing it. Break it into "
            f"exactly {count} chapters that move the idea forward in order — "
            f"each one a different part of the subject, none of them a restatement "
            f"of another. Each chapter will be about {chapter_words[0]} words of "
            f"narration when it is written.",
            "",
            f"Write the framing lines in full — hook, introduction, ending and "
            f"call to action, about {framing_words} words between them. For the "
            f"chapters write only the heading and one sentence saying what that "
            f"chapter covers; the narration comes later.",
            "",
            "Return ONLY this JSON object:",
            "{",
            '  "title": "a short title for the video",',
            '  "hook": "the first line, said in under 3 seconds, that stops the scroll",',
            '  "introduction": "what the video will cover and why it is worth the time",',
            '  "chapters": [',
            '    {"heading": "a 2-5 word label", '
            '"summary": "one sentence on what this chapter covers"}',
            "  ],",
            '  "ending": "the line that closes the idea",',
            '  "cta": "one short call to action",',
            '  "keywords": ["3-6 words describing the subject, for finding visuals"]',
            "}",
        ]
    )


def build_chapter_prompt(
    brief: dict, outline: dict, indexes: list[int], chapter_words: list[int]
) -> str:
    chapters = outline["chapters"]

    plan = [
        f"{position}. {row['heading']} — {row['summary']}"
        for position, row in enumerate(chapters, start=1)
    ]
    asks = [
        f"{index + 1}. {chapters[index]['heading']} — {chapters[index]['summary']} "
        f"(about {chapter_words[index]} words)"
        for index in indexes
    ]

    return "\n".join(
        [
            *_brief_lines(brief, total_budget=False),
            "",
            f"THE VIDEO IS TITLED: {outline['title']}",
            f"IT OPENS WITH: {outline['hook']} {outline['introduction']}",
            f"IT CLOSES WITH: {outline['ending']}",
            "",
            "THE FULL CHAPTER PLAN. Every one of these is being written, so do "
            "not cover a chapter that is not yours — say your part and hand over:",
            *plan,
            "",
            f"Write the narration for {'these chapters' if len(asks) > 1 else 'this chapter'}, "
            "in this order, and nothing else:",
            *asks,
            "",
            "Hit those word counts — they are what makes the video come out the "
            "right length. Use concrete examples, numbers and short stories "
            "rather than repeating the heading in longer words. Do not open a "
            "chapter by announcing it ('In this chapter'); just start saying it.",
            "",
            "Return ONLY this JSON object:",
            "{",
            '  "chapters": [',
            '    {"heading": "the heading you were given", '
            '"text": "the narration for that chapter"}',
            "  ]",
            "}",
            f"There must be exactly {len(asks)} entries in that array, in the "
            "order they were asked for.",
        ]
    )


def normalize_outline(data: object, brief: dict, count: int) -> dict:
    """A model's outline response, made complete and the right length.

    A short outline is padded rather than refused: the chapters carry the video
    and a missing heading is a placeholder the chapter pass can still write to,
    where a raised error is a half-hour script the user does not get at all.
    """
    if not isinstance(data, dict):
        raise ScriptError("The script outline came back unusable. Try again.")

    rows = data.get("chapters")
    chapters: list[dict] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                heading = _clean(row.get("heading"), 120)
                summary = _clean(row.get("summary"), 400)
            else:
                heading, summary = _clean(row, 120), ""
            if heading or summary:
                chapters.append(
                    {"heading": heading or summary[:60], "summary": summary or heading}
                )

    chapters = chapters[:count]
    hook = _clean(data.get("hook"))

    # Checked before the padding below, not after: a response with nothing in it
    # would otherwise be padded into `count` placeholder chapters and go on to
    # spend twenty calls writing narration for "Part 1" through "Part 22".
    if not hook and not chapters:
        raise ScriptError(
            "The script outline came back empty. Try again, or reword the topic."
        )

    while len(chapters) < count:
        position = len(chapters) + 1
        chapters.append(
            {
                "heading": f"Part {position}",
                "summary": f"another part of {brief['topic']}",
            }
        )

    keywords = data.get("keywords")
    keywords = [_clean(word, 40) for word in keywords] if isinstance(keywords, list) else []

    return {
        "title": _clean(data.get("title"), 200) or brief["topic"][:200],
        "hook": hook,
        "introduction": _clean(data.get("introduction")),
        "ending": _clean(data.get("ending")),
        "cta": _clean(data.get("cta")),
        "chapters": chapters,
        "keywords": [word for word in keywords if word][:8],
    }


async def _write_batch(
    brief: dict,
    outline: dict,
    indexes: list[int],
    chapter_words: list[int],
    client: AIProvider,
) -> dict[int, str]:
    """The narration for one run of chapters, keyed by chapter index.

    A batch that fails comes back empty rather than raising. Losing one chapter
    out of twenty to a rate limit should not lose the other nineteen — the
    caller falls back to the outline's summary for that chapter, which leaves a
    complete, editable document with one thin section the user can rewrite in
    place.
    """
    from app.services.ai_service import _parse_json

    asked = sum(chapter_words[index] for index in indexes)

    try:
        raw = await client.complete(
            system=_SYSTEM_LONG,
            user=build_chapter_prompt(brief, outline, indexes, chapter_words),
            max_tokens=_max_tokens_for(asked),
            temperature=settings.ai_temperature,
            json_mode=True,
            context={
                "feature": "video_script_chapters",
                "topic": brief["topic"],
                "chapters": len(indexes),
            },
        )
    except ProviderError as exc:
        logger.warning("Long-form chapters %s failed: %s", indexes, exc)
        return {}

    data = _parse_json(raw)

    rows = data.get("chapters") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        logger.warning("Long-form chapters %s came back in the wrong shape", indexes)
        return {}

    # Matched by heading where the model echoed one back, positionally where it
    # did not. Order alone would be enough if models always returned the array
    # they were asked for; when one drops a chapter, positional matching quietly
    # files every chapter after it under the wrong heading.
    by_heading = {
        outline["chapters"][index]["heading"].casefold(): index for index in indexes
    }
    spare = list(indexes)

    written: dict[int, str] = {}
    for row in rows:
        if isinstance(row, dict):
            heading = _clean(row.get("heading"), 120).casefold()
            text = _clean(row.get("text"), MAX_SECTION_CHARS)
        else:
            heading, text = "", _clean(row, MAX_SECTION_CHARS)

        index = by_heading.get(heading)
        if index is None or index in written:
            index = next((value for value in spare if value not in written), None)
        if index is None:
            break
        if text:
            written[index] = text

    return written


async def generate_long_form(brief: dict, client: AIProvider) -> dict:
    """Write a script too long for a single call: outline, then chapters.

    Returns the same document shape as `generate_script` — there is no separate
    "long" script the editor would have to know about.
    """
    from app.services.ai_service import _parse_json

    framing_words, chapter_words = framing_and_chapter_words(brief)

    try:
        raw = await client.complete(
            system=_SYSTEM_LONG,
            user=build_outline_prompt(brief, framing_words, chapter_words),
            max_tokens=_max_tokens_for(framing_words + 25 * len(chapter_words)),
            temperature=settings.ai_temperature,
            json_mode=True,
            context={
                "feature": "video_script_outline",
                "topic": brief["topic"],
                "chapters": len(chapter_words),
            },
        )
    except ProviderError as exc:
        raise ScriptError(f"The script could not be generated: {exc}") from exc

    outline = normalize_outline(_parse_json(raw), brief, len(chapter_words))

    # Independent once the outline exists, so they overlap. The semaphore is
    # what keeps a 24-chapter script from opening ten connections at once and
    # tripping a free tier's per-minute limit.
    gate = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)

    async def run(indexes: list[int]) -> dict[int, str]:
        async with gate:
            return await _write_batch(brief, outline, indexes, chapter_words, client)

    batches = batch_chapters(chapter_words)
    written: dict[int, str] = {}
    for result in await asyncio.gather(*(run(batch) for batch in batches)):
        written.update(result)

    if not written:
        raise ScriptError(
            "The script generator returned nothing usable. Try again, or "
            "reword the topic."
        )

    points = [
        {
            "heading": chapter["heading"],
            "text": written.get(index) or chapter["summary"],
        }
        for index, chapter in enumerate(outline["chapters"])
    ]

    script = normalize_script(
        {
            "title": outline["title"],
            "hook": outline["hook"],
            "introduction": outline["introduction"],
            "main_points": points,
            "ending": outline["ending"],
            "cta": outline["cta"],
            "keywords": outline["keywords"],
        },
        brief,
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


def _script_as_text(
    script: dict, *, skip: str = "", skip_point: str = "", point_limit: int = 0
) -> str:
    """The script as the model should see it: labelled, in running order.

    The section being rewritten is left out — including it invites the model to
    hand back a lightly reworded copy of the line the user just rejected.

    `point_limit` shortens each main point to that many characters. A long-form
    script is thousands of words, and sending all of it to rewrite one line
    buries the actual instruction; what the model needs from the other chapters
    is what they cover, which the opening of each one already says.
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
        text = str(point.get("text") or "")
        if point_limit and len(text) > point_limit:
            text = text[:point_limit].rsplit(" ", 1)[0] + "…"
        parts.append(f"MAIN POINT {index} ({heading}): {text}")
    if script.get("ending") and skip != "ending":
        parts.append(f"ENDING: {script['ending']}")
    if script.get("cta") and skip != "cta":
        parts.append(f"CALL TO ACTION: {script['cta']}")
    return "\n".join(parts)


def _section_words(brief: dict, script: dict, section: str, point_id: str = "") -> int:
    """How long the replacement for a section should be.

    Match the length of what is being replaced, so rewriting one line does not
    quietly blow the duration budget the rest of the script was fitted to. A
    section that is empty has nothing to match, so it gets an even share of the
    budget instead.
    """
    if section == "point":
        point = find_point(script, point_id)
        current = str((point or {}).get("text") or "")
    else:
        current = str(script.get(section) or "")

    words = count_words(current)
    if words < 3:
        share = max(1, brief["main_point_count"] + 4)
        words = max(6, brief["word_budget"] // share)
    return words


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

    words = _section_words(brief, script, section, point_id)

    # Past a handful of chapters the surrounding script is longer than anything
    # a model reads carefully, so the others are reduced to their openings.
    others = len(script.get("main_points") or [])
    context_text = _script_as_text(
        script,
        skip=section,
        skip_point=point_id,
        point_limit=240 if others > 6 else 0,
    )

    lines = [
        *_brief_lines(brief, total_budget=not is_long_form(brief)),
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
            system=_system_for(brief),
            user=prompt,
            max_tokens=_max_tokens_for(_section_words(brief, script, section, point_id)),
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


# The lengths the form offers as one tap. Any value inside `duration_range` is
# accepted, so this is a menu rather than a constraint — but it lives here
# rather than in JavaScript so "what lengths exist" has one answer.
DURATION_CHOICES = (
    15, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1200, 1500, 1800,
)


def options() -> dict:
    """Everything the "new AI video" form needs to build itself."""
    return {
        "tones": list(TONES),
        "content_types": list(CONTENT_TYPES),
        "visual_modes": list(VISUAL_MODES),
        "languages": [dict(entry) for entry in LANGUAGES],
        "duration_range": [MIN_DURATION_SECONDS, MAX_DURATION_SECONDS],
        "durations": list(DURATION_CHOICES),
        "default_duration": 30,
        # A script can be far longer than a video this deployment will render,
        # and longer again than one it will cut into a project. The form for
        # *making a video* stops at these; Script Studio does not, and a script
        # written past them is still worth having.
        "max_video_seconds": settings.video_max_duration_seconds,
        "project_max_seconds": MAX_PROJECT_SECONDS,
    }
