"""AI service layer.

Orchestrates: request -> per-platform prompt -> provider completion ->
robust JSON parse -> typed GeneratedPost. Platform-agnostic and
provider-agnostic; switching the LLM is a config change, not a code change.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from app.config import settings
from app.schemas.post import (
    GeneratedPost,
    GeneratePostRequest,
    GeneratePostResponse,
    Platform,
)
from app.services.prompt_templates import (
    PLATFORM_SPECS,
    build_system_prompt,
    build_user_prompt,
)
from app.services.providers import AIProvider, get_provider

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


async def generate_posts(
    req: GeneratePostRequest,
    business_context: str | None = None,
    extra_instructions: str | None = None,
) -> GeneratePostResponse:
    """Generate optimized post(s). One platform, or all when none specified.

    `business_context` (from the user's business profile) is woven into each
    prompt when present; it's optional so generation works without a profile.
    `extra_instructions` appends ad-hoc guidance (e.g. the Content Planner's
    "avoid these hashtags/CTAs" diversity rules) — optional and additive.
    """
    provider = get_provider(req.provider)

    targets = [req.platform] if req.platform else list(Platform)

    # Fan out across platforms concurrently — fast and cheap.
    posts = await asyncio.gather(
        *(
            _generate_one(provider, req, p, business_context, extra_instructions)
            for p in targets
        )
    )

    return GeneratePostResponse(
        provider=provider.name,
        model=provider.model,
        results=list(posts),
    )


async def generate_article(
    topic: str,
    *,
    audience: str | None = None,
    tone: str = "professional",
    provider_name: str | None = None,
    business_context: str | None = None,
) -> dict:
    """Generate a LinkedIn article (title, body, tags, SEO keywords, cover prompt).

    Returns a dict the route serializes; reading time is derived from the body.
    Deliberately produces long-form prose — no hashtags or short captions.
    """
    provider = get_provider(provider_name)
    system = (
        "You are an expert LinkedIn ghostwriter who writes engaging, "
        "professional long-form articles. You ALWAYS return only a JSON object "
        "matching the requested schema — no markdown, no code fences, no commentary."
    )
    audience_line = f"\nTARGET AUDIENCE: {audience}" if audience else ""
    context_line = (
        f"\nBUSINESS CONTEXT (make it relevant and on-brand; ignore missing "
        f"fields):\n{business_context}"
        if business_context
        else ""
    )
    user = (
        f"Write a {tone} LinkedIn article about this topic:\n"
        f"TOPIC: {topic}{audience_line}{context_line}\n\n"
        "Requirements:\n"
        "- A compelling, specific title (max ~80 characters).\n"
        "- A body of roughly 400-800 words in clear paragraphs separated by "
        "blank lines. Use a few short plain-text subheadings. Professional, "
        "insight-driven, with a strong opening hook and a closing takeaway.\n"
        "- 3-6 topical tags (no # symbol).\n"
        "- 4-8 SEO keywords/phrases.\n"
        "- A short visual description for a 16:9 cover image.\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        '{"title": "...", "body": "...", "tags": ["..."], '
        '"seo_keywords": ["..."], "cover_image_prompt": "..."}'
    )
    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=max(settings.ai_max_tokens, 2048),
        temperature=settings.ai_temperature,
        json_mode=True,
        context={"article": True, "topic": topic},
    )
    data = _parse_json(raw)
    body = str(data.get("body", "")).strip()
    title = str(data.get("title", "")).strip() or topic[:80]
    words = len(body.split())
    return {
        "title": title,
        "body": body,
        "tags": _normalize_hashtags(data.get("tags")),
        "seo_keywords": _normalize_list(data.get("seo_keywords")),
        "cover_image_prompt": str(data.get("cover_image_prompt", "")).strip() or title,
        "reading_time_min": max(1, round(words / 200)),
        "word_count": words,
    }


# Character budgets per slot. These are not cosmetic: the layout renders each
# slot at a fixed size, so text beyond the budget either wraps past the frame or
# gets clipped. Asking the model for the right length is far more reliable than
# truncating afterwards, which cuts mid-sentence.
TEMPLATE_SLOTS: dict[str, tuple[str, int]] = {
    "headline": ("The main statement. Punchy and specific, not a caption.", 70),
    "subtext": ("One supporting line that adds a concrete detail.", 110),
    "cta": ("A 2-4 word button label, e.g. 'Book a call'.", 22),
    "badge": ("A very short pill label, e.g. '50% OFF' or \"WE'RE HIRING\".", 16),
    "price": ("A short price, e.g. '£49' or 'From $29'.", 12),
}


def _slot_limits(wanted: list[str], max_chars: dict[str, int] | None) -> dict[str, int]:
    """Effective character budget per slot.

    A layout may be tighter than the general budget — a big centred quote holds
    far less than a three-line lower third — but never looser: the defaults are
    what the renderers were sized for, so a caller asking for more would push
    text past the frame.
    """
    limits: dict[str, int] = {}
    for name in wanted:
        default = TEMPLATE_SLOTS[name][1]
        override = (max_chars or {}).get(name)
        limits[name] = min(default, override) if isinstance(override, int) and override > 0 else default
    return limits


async def generate_template_content(
    topic: str,
    *,
    slots: list[str],
    template_label: str,
    tone: str = "professional",
    audience: str | None = None,
    max_chars: dict[str, int] | None = None,
    provider_name: str | None = None,
    business_context: str | None = None,
) -> dict:
    """Generate the text that fills a content template's slots.

    This is what makes generation layout-aware. Rather than producing a caption
    and hoping it fits, the model is told which fields the design has and how
    long each may be, so the result is composed for the layout it will occupy.

    `max_chars` lets a template tighten those budgets for its own geometry; see
    `_slot_limits`.

    Unknown slot names are ignored, and any slot the model omits comes back as
    an empty string — templates already skip empty slots, so a partial response
    degrades to a simpler layout instead of failing.
    """
    wanted = [s for s in slots if s in TEMPLATE_SLOTS]
    if not wanted:
        return {}
    limits = _slot_limits(wanted, max_chars)

    provider = get_provider(provider_name)
    system = (
        "You are a senior social media art director writing copy that must fit "
        "inside a fixed graphic layout. Every field has a hard character limit "
        "and going over breaks the design. You ALWAYS return only a JSON object "
        "matching the requested schema — no markdown, no code fences."
    )
    audience_line = f"\nTARGET AUDIENCE: {audience}" if audience else ""
    context_line = (
        f"\nBUSINESS CONTEXT (make it on-brand; ignore missing fields):\n{business_context}"
        if business_context
        else ""
    )
    field_lines = "\n".join(
        f'- "{name}": {TEMPLATE_SLOTS[name][0]} Max {limits[name]} characters.'
        for name in wanted
    )
    schema = ", ".join(f'"{name}": "..."' for name in wanted)

    user = (
        f"Write the on-image text for a {tone} \"{template_label}\" graphic.\n"
        f"TOPIC: {topic}{audience_line}{context_line}\n\n"
        f"Fields to write:\n{field_lines}\n\n"
        "Rules:\n"
        "- Respect every character limit strictly. Shorter is better.\n"
        "- No hashtags, no emoji, no quotation marks around the text.\n"
        "- Write for a reader who sees only the image, with no caption.\n\n"
        f"Return ONLY a JSON object with exactly these keys:\n{{{schema}}}"
    )

    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=400,
        temperature=settings.ai_temperature,
        json_mode=True,
        context={"template": template_label, "topic": topic},
    )
    data = _parse_json(raw)

    out: dict[str, str] = {}
    for name in wanted:
        limit = limits[name]
        value = str(data.get(name, "") or "").strip().strip('"')
        # Hard cap as a backstop — models overshoot limits often enough that
        # trusting the instruction alone would let text run past the frame.
        out[name] = value[:limit].strip()
    return out


# Where a layout puts its text -> how the scene must be framed to leave room.
# Phrased as camera direction because that is what a text-to-image model acts
# on; "leave space for a headline" means nothing to it, "subject in the upper
# two thirds, foreground falling away" does.
_ZONE_DIRECTION = {
    "bottom": "the lower third of the frame is empty foreground, floor, "
              "surface or sky — no subject matter there",
    "top": "the upper third of the frame is empty sky, wall or open space — "
           "no subject matter there",
    "center": "the subject sits around the outer edges, leaving the middle of "
              "the frame open and low in detail",
    "left": "the subject sits on the right, the left third is open and plain",
    "right": "the subject sits on the left, the right third is open and plain",
    "full": "a restrained, minimal scene with large areas of plain tone",
}


async def build_visual_prompt(
    topic: str,
    *,
    style_label: str | None = None,
    template_label: str | None = None,
    safe_zone: str | None = None,
    headline: str | None = None,
    provider_name: str | None = None,
    business_context: str | None = None,
) -> str:
    """Turn a post topic into a detailed VISUAL SCENE description.

    This is the fix for irrelevant, stock-looking images. Sending the post text
    to a diffusion model asks it to illustrate an abstract marketing statement,
    which is exactly the input that produces a generic laptop-on-a-desk. The
    model needs a *scene*: a concrete subject, setting, lighting, camera angle,
    and colour direction.

    So an LLM reads the post first and writes that scene — grounded in the
    business's actual industry, so a healthcare post yields a clinical setting
    and a restaurant post yields food, rather than the same office stock photo
    for both.

    `safe_zone` is where the chosen template will draw its text. Feeding it in
    here (as well as into compose_prompt) matters because the LLM can frame the
    *scene* around the empty region, which a bolted-on "leave space at the
    bottom" clause cannot do once the subject has already been described.

    Returns a plain prompt string. Falls back to the topic on any failure: a
    worse image is better than no image.
    """
    clean = (topic or "").strip()
    if not clean:
        return clean

    context_line = (
        f"\nBUSINESS CONTEXT (use the industry to ground the scene):\n{business_context}"
        if business_context
        else ""
    )
    # The on-image headline, when it exists, is the single strongest signal of
    # what the picture is actually about — it is the message the design makes.
    headline_line = f"\nHEADLINE THAT WILL APPEAR ON THE IMAGE: {headline}" if headline else ""
    zone = _ZONE_DIRECTION.get(str(safe_zone or "").strip().lower())
    reserve_line = f"\n- Frame it so {zone}." if zone else ""
    style_line = f"\n- Visual treatment: {style_label}." if style_label else ""
    template_line = f"\n- It will be used as a {template_label} graphic." if template_label else ""

    system = (
        "You write prompts for a text-to-image model. You translate a marketing "
        "message into a single concrete PHOTOGRAPHIC SCENE. You never write "
        "slogans, captions, or abstract concepts — a diffusion model cannot "
        "draw 'productivity', only a specific thing in a specific place. "
        "You ALWAYS return only a JSON object."
    )
    user = (
        f"POST TOPIC: {clean}{headline_line}{context_line}\n\n"
        "Write ONE image prompt describing a scene that a viewer would "
        "immediately connect to this topic.\n\n"
        "Requirements:\n"
        "- Name a concrete subject and setting (people, objects, place).\n"
        "- Specify lighting and camera framing.\n"
        "- Suggest a colour direction.\n"
        "- Match the subject to the industry — a healthcare post gets a "
        "clinical scene, a restaurant post gets food, a property post gets "
        "interiors, a marketing post gets a studio or campaign scene. Never "
        "default to a generic laptop or office desk unless the topic is "
        "genuinely about software or office work."
        f"{style_line}{template_line}{reserve_line}\n"
        "- The image is a background for a designed graphic: one clear "
        "subject, plenty of calm negative space, nothing cluttered.\n"
        "- No text, letters, numbers, signage, logos, or watermarks in the scene.\n"
        "- 45 words maximum. No preamble.\n\n"
        'Return ONLY: {"prompt": "..."}'
    )

    try:
        # Provider resolution is inside the guard too: an unconfigured or
        # misconfigured provider must degrade to the raw topic, not take down
        # image generation, which needs no LLM to work at all.
        raw = await get_provider(provider_name).complete(
            system=system,
            user=user,
            max_tokens=200,
            temperature=0.7,
            json_mode=True,
            context={"visual_prompt": True, "topic": clean[:80]},
        )
        built = str(_parse_json(raw).get("prompt", "")).strip()
    except Exception:  # noqa: BLE001 - never let this block image generation
        logger.warning("Visual prompt generation failed; using the raw topic.")
        return clean

    # A one-word answer means the model misunderstood; the topic is safer.
    return built if len(built) > 15 else clean


# Operations the image editor can apply. The model picks from this closed set
# rather than emitting free-form edits, because an operation the client cannot
# execute is worse than a refusal — it looks like the edit silently failed.
IMAGE_EDIT_OPS = {
    "move": "Move a layer to a corner. Needs `target` and `anchor`.",
    "recolor": "Recolour layers. Needs `target`; optional `color` (hex) or `palette`:'brand'.",
    "resize": "Scale a layer. Needs `target` and `scale` (0.5 = half, 2 = double).",
    "spacing": "Shift layers away from the edges. Needs `delta` (e.g. 0.02).",
    "theme": "Switch the overall look. Needs `mode`: 'dark' or 'light'.",
    "add_text": "Add a text layer. Needs `text`; optional `anchor`.",
    "add_cta": "Add a call-to-action button. Needs `text`.",
    "remove": "Delete layers. Needs `target`.",
    "restyle": "Regenerate the artwork in a different visual style. Needs `style`.",
    "regenerate": "Regenerate the artwork from a new description. Needs `prompt`.",
}

#: Targets the client knows how to resolve to layers.
IMAGE_EDIT_TARGETS = (
    "logo", "text", "headline", "subtext", "cta", "background",
    "shapes", "image", "all",
)

#: Ops that require new artwork rather than a layer change.
REGENERATING_OPS = {"restyle", "regenerate"}


async def interpret_image_edit(
    instruction: str,
    *,
    layers: list[dict],
    style: str | None = None,
    provider_name: str | None = None,
    business_context: str | None = None,
) -> dict:
    """Turn a natural-language edit into structured operations.

    The image pipeline is text-to-image and cannot edit an existing bitmap. It
    does not need to for most requests: the picture is a stack of addressable
    layers, so "move the logo to the top right" or "use my brand colours" are
    layer edits — applied instantly, losslessly, and undoably, with the artwork
    untouched.

    Only instructions that genuinely change what is DEPICTED ("replace the
    laptop with a smartphone", "make it more premium") need new artwork. Those
    return a regenerating op, and the client keeps every existing layer so the
    layout survives the swap.

    Returns {"operations": [...], "explanation": str, "needs_regeneration": bool}.
    """
    provider = get_provider(provider_name)

    op_lines = "\n".join(f"- {name}: {desc}" for name, desc in IMAGE_EDIT_OPS.items())
    layer_lines = (
        "\n".join(
            f"- id={l.get('id')} type={l.get('type')}"
            + (f" text={str(l.get('text'))[:40]!r}" if l.get("text") else "")
            for l in layers[:20]
        )
        or "- (no layers)"
    )
    context_line = (
        f"\nBUSINESS CONTEXT:\n{business_context}" if business_context else ""
    )

    system = (
        "You convert a user's plain-English request about a social media graphic "
        "into a short list of structured edit operations. You ALWAYS return only "
        "a JSON object — no markdown, no code fences, no commentary.\n\n"
        "Prefer layer operations. Only use 'restyle' or 'regenerate' when the "
        "request changes what the picture actually DEPICTS or its overall look — "
        "those discard the current artwork, so they are a last resort."
    )
    user = (
        f"USER REQUEST: {instruction}\n\n"
        f"CURRENT LAYERS:\n{layer_lines}\n"
        f"CURRENT STYLE: {style or 'unspecified'}{context_line}\n\n"
        f"AVAILABLE OPERATIONS:\n{op_lines}\n\n"
        f"VALID `target` VALUES: {', '.join(IMAGE_EDIT_TARGETS)}\n"
        "VALID `anchor` VALUES: top-left, top-right, bottom-left, bottom-right, center\n\n"
        "Rules:\n"
        "- Return 1-4 operations. Fewer is better.\n"
        "- Use only the operation names and target values listed above.\n"
        "- If the request is unclear, return an empty operations list and say why.\n"
        "- `explanation` is one short sentence describing what you changed.\n\n"
        'Return ONLY: {"operations": [{"op": "...", ...}], "explanation": "..."}'
    )

    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=500,
        temperature=0.2,  # low: this is parsing intent, not writing copy
        json_mode=True,
        context={"image_edit": True},
    )
    data = _parse_json(raw)

    operations = []
    for item in data.get("operations") or []:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op", "")).strip()
        if op not in IMAGE_EDIT_OPS:
            continue  # drop anything the client cannot execute
        target = str(item.get("target", "")).strip().lower()
        if target and target not in IMAGE_EDIT_TARGETS:
            target = "all"
        cleaned = {k: v for k, v in item.items() if k not in {"op", "target"}}
        operations.append({"op": op, **({"target": target} if target else {}), **cleaned})

    return {
        "operations": operations[:4],
        "explanation": str(data.get("explanation", "")).strip(),
        "needs_regeneration": any(o["op"] in REGENERATING_OPS for o in operations),
    }


def _normalize_list(value: object) -> list[str]:
    """Normalize a value into a clean list of strings (keeps phrases intact)."""
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[,\n]+", value)
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip().lstrip("#").strip()
        if s:
            out.append(s)
    return out


async def generate_carousel_outline(
    topic: str,
    slides: int,
    *,
    platform: Platform | None = None,
    provider_name: str | None = None,
) -> list[str]:
    """Return exactly `slides` short, DISTINCT visual descriptions for a carousel.

    Best-effort: if the LLM provider is unavailable (no API key) or returns
    something unusable, fall back to deterministic per-slide labels so image
    generation still produces visibly different slides — never identical images.
    """
    slides = max(1, min(slides, 10))
    fallback = _fallback_outline(topic, slides)

    try:
        provider = get_provider(provider_name)
    except Exception:  # noqa: BLE001 — provider not configured; use fallback
        logger.info("Carousel outline: provider unavailable, using fallback labels.")
        return fallback

    system = (
        "You design social media carousels. You always return ONLY valid JSON "
        "matching the requested schema — no markdown, no commentary."
    )
    audience = f" for {platform.value}" if platform else ""
    user = (
        f"Create exactly {slides} carousel slides{audience} about this topic:\n"
        f"TOPIC: {topic}\n\n"
        "Each slide must cover a DIFFERENT aspect of the topic (e.g. cover, key "
        "point, example, benefit, summary) so that no two slides look alike.\n"
        'Return ONLY a JSON object: {"slides": ["short visual description", ...]} '
        f"with exactly {slides} items, each 3-10 words, no numbering."
    )
    try:
        raw = await provider.complete(
            system=system,
            user=user,
            max_tokens=settings.ai_max_tokens,
            temperature=0.7,
            json_mode=True,
            context={"carousel": True, "topic": topic, "slides": slides},
        )
        items = _parse_json(raw).get("slides")
        cleaned = (
            [str(s).strip() for s in items if str(s).strip()]
            if isinstance(items, list)
            else []
        )
    except Exception:  # noqa: BLE001 — best effort; keep going with the fallback
        logger.warning("Carousel outline generation failed; using fallback labels.")
        cleaned = []

    if len(cleaned) < slides:
        # Pad with fallback labels so we always return exactly `slides` items.
        cleaned += fallback[len(cleaned):]
    return cleaned[:slides]


# Optional, in-place text edits for the manual composer ("AI Assist"). Each
# transforms the user's existing text rather than generating a new post.
ASSIST_INSTRUCTIONS: dict[str, str] = {
    "improve": "Improve the writing so it is clearer, more engaging and polished. Keep the same meaning and the same language.",
    "rewrite": "Rewrite the text in a fresh way while preserving its meaning and language.",
    "shorten": "Make the text shorter and more concise while keeping the key message.",
    "expand": "Expand the text with more relevant detail and depth, keeping the same voice.",
    "grammar": "Correct all spelling, grammar and punctuation mistakes. Keep the wording and language otherwise unchanged.",
    "tone": "Rewrite the text in a {tone} tone.",
    "hashtags": "Generate 5 to 10 relevant hashtags (a mix of popular and niche) for the text. Each must start with # and be separated by spaces. Return only the hashtags.",
    "cta": "Write one short, compelling call-to-action line for the text. Return only that line.",
    "translate": "Translate the text into {language}. Return only the translation.",
}


async def assist_text(
    text: str,
    action: str,
    *,
    tone: str | None = None,
    language: str | None = None,
    provider_name: str | None = None,
) -> str:
    """Apply an in-place AI edit (improve/rewrite/translate/…) to `text`."""
    instruction = ASSIST_INSTRUCTIONS.get(action)
    if instruction is None:
        raise ValueError(f"Unknown assist action: {action!r}")
    if action == "tone":
        instruction = instruction.format(tone=tone or "professional")
    if action == "translate":
        instruction = instruction.format(language=language or "English")

    provider = get_provider(provider_name)
    system = (
        "You are an expert social media copy editor. You ALWAYS return only a "
        'JSON object {"result": "..."} with no markdown, no code fences and no '
        "commentary."
    )
    user = (
        f"{instruction}\n\nTEXT:\n{text}\n\n"
        'Return ONLY a JSON object: {"result": "the edited text"}.'
    )
    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=settings.ai_max_tokens,
        temperature=0.7,
        json_mode=True,
        context={"assist": action},
    )
    result = str(_parse_json(raw).get("result", "")).strip()
    return result or text


def _fallback_outline(topic: str, slides: int) -> list[str]:
    """Deterministic distinct slide labels when the LLM can't be used."""
    roles = [
        "cover", "introduction", "key point", "example", "benefit",
        "how it works", "pro tip", "common mistake", "insight", "summary",
    ]
    return [
        f"{topic} — {roles[i] if i < len(roles) else f'point {i + 1}'}"
        for i in range(slides)
    ]


async def _generate_one(
    provider: AIProvider,
    req: GeneratePostRequest,
    platform: Platform,
    business_context: str | None = None,
    extra_instructions: str | None = None,
) -> GeneratedPost:
    spec = PLATFORM_SPECS[platform]
    system = build_system_prompt()
    user = build_user_prompt(req, platform, business_context, extra_instructions)

    context = {
        "platform": platform.value,
        "topic": req.topic,
        "tone": req.tone.value,
        "variants": req.variants,
        "include_hashtags": req.include_hashtags,
    }

    raw = await provider.complete(
        system=system,
        user=user,
        max_tokens=settings.ai_max_tokens,
        temperature=settings.ai_temperature,
        json_mode=True,
        context=context,
    )

    data = _parse_json(raw)
    text = str(data.get("text", "")).strip()

    # Some models (e.g. llama-3.3-70b) ignore a stated length floor and return a
    # bare one-line slogan. If the draft is well under the platform minimum, do
    # one expand pass that feeds the draft back and asks for a fuller post.
    if len(text) < spec.min_chars:
        expanded = await _expand(provider, req, platform, text, context)
        if len(expanded) > len(text):
            data["text"] = expanded
            text = expanded

    hashtags: list[str] = []
    if req.include_hashtags:
        hashtags = _normalize_hashtags(data.get("hashtags"))

    return GeneratedPost(
        platform=platform,
        text=text,
        short_version=_opt_str(data.get("short_version")) if req.variants else None,
        long_version=_opt_str(data.get("long_version")) if req.variants else None,
        hashtags=hashtags,
        character_count=len(text),
        char_limit=spec.char_limit,
        within_limit=len(text) <= spec.char_limit,
    )


async def _expand(
    provider: AIProvider,
    req: GeneratePostRequest,
    platform: Platform,
    draft: str,
    context: dict,
) -> str:
    """Rewrite an over-short draft into a fuller, platform-native post.

    Returns the expanded text, or the original draft if the rewrite fails or
    doesn't actually grow it.
    """
    spec = PLATFORM_SPECS[platform]
    system = build_system_prompt()
    user = (
        f"Rewrite the following {spec.label} post so it is more developed and "
        f"engaging. It is currently too short.\n\n"
        f"DRAFT: {draft or '(empty)'}\n\n"
        f"TOPIC: {req.topic}\n"
        f"VOICE: {spec.voice}\n"
        f"REQUIRED LENGTH: between {spec.min_chars} and {spec.char_limit} "
        f"characters. Keep the same core idea and tone, but expand it into "
        f"full sentences — add a concrete benefit, detail or call-to-action. "
        f"Never return just a headline.\n\n"
        'Return ONLY a JSON object: {"text": "the rewritten post"}'
    )
    try:
        raw = await provider.complete(
            system=system,
            user=user,
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
            json_mode=True,
            context={**context, "expand": True},
        )
    except Exception:  # noqa: BLE001 — expansion is best-effort; keep the draft
        logger.warning("Expand pass failed for %s; keeping short draft.", platform.value)
        return draft

    expanded = str(_parse_json(raw).get("text", "")).strip()
    return expanded or draft


def _parse_json(raw: str) -> dict:
    """Best-effort JSON extraction from a model response.

    Handles clean JSON, ```json fenced blocks, and stray prose around the
    object. Falls back to treating the whole response as plain post text.
    """
    if not raw:
        return {"text": ""}

    cleaned = raw.strip()
    # Strip a leading/trailing markdown code fence if present.
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = _JSON_OBJECT_RE.search(cleaned)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from model output; using raw text.")
    return {"text": cleaned}


def _normalize_hashtags(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Accept "#a #b" or "a, b" strings as well as arrays.
        value = re.split(r"[\s,]+", value)
    if not isinstance(value, (list, tuple)):
        return []
    tags: list[str] = []
    for item in value:
        tag = str(item).strip().lstrip("#").strip()
        if tag:
            tags.append(tag)
    return tags


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
