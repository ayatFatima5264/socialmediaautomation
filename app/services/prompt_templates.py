"""Per-platform prompt engineering.

The goal is high-quality, platform-native copy. Each platform has its own
voice, length budget, hashtag etiquette and structural conventions, captured
in PLATFORM_SPECS and woven into the prompt sent to the LLM.

`build_system_prompt` / `build_user_prompt` are provider-agnostic: any
provider (Groq, OpenAI, Claude, ...) receives the same strings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.schemas.post import GeneratePostRequest, Platform


@dataclass(frozen=True)
class PlatformSpec:
    label: str
    char_limit: int          # hard platform limit for the main `text`
    sweet_spot: str          # human description of the ideal length
    hashtags: str            # hashtag etiquette
    voice: str               # tone/structure guidance


PLATFORM_SPECS: dict[Platform, PlatformSpec] = {
    Platform.twitter: PlatformSpec(
        label="Twitter/X",
        char_limit=280,
        sweet_spot="one punchy thought, ideally under 280 characters",
        hashtags="0–2 highly relevant hashtags, never more",
        voice=(
            "Hook in the first 7 words. Be concise, witty and scroll-stopping. "
            "No filler. One clear idea. Emojis only if they add punch."
        ),
    ),
    Platform.instagram: PlatformSpec(
        label="Instagram",
        char_limit=2200,
        sweet_spot="125–250 characters of caption before the hashtags",
        hashtags="5–10 relevant, mixed popular + niche hashtags",
        voice=(
            "Start with a strong visual hook line, then 1–3 short lines with "
            "line breaks for readability. Warm, expressive, emoji-friendly. "
            "End with a clear call-to-action (save, comment, tag a friend)."
        ),
    ),
    Platform.facebook: PlatformSpec(
        label="Facebook",
        char_limit=63206,
        sweet_spot="40–80 words, conversational",
        hashtags="0–2 hashtags only",
        voice=(
            "Conversational and community-oriented. Tell a micro-story or pose "
            "a question. Encourage comments/shares. Minimal hashtags."
        ),
    ),
    Platform.linkedin: PlatformSpec(
        label="LinkedIn",
        char_limit=3000,
        sweet_spot="100–200 words with short paragraphs",
        hashtags="3 professional hashtags",
        voice=(
            "Professional, insight-driven thought leadership. Open with a bold "
            "one-line hook, then short single-sentence paragraphs with white "
            "space. Share a lesson or takeaway. Restrained emoji use. End with "
            "a reflective question or CTA."
        ),
    ),
    Platform.threads: PlatformSpec(
        label="Threads",
        char_limit=500,
        sweet_spot="under 500 characters, casual",
        hashtags="0–1 hashtag",
        voice=(
            "Casual, authentic and conversational, like talking to a friend. "
            "Light and real. Almost no hashtags."
        ),
    ),
}


def build_system_prompt() -> str:
    return (
        "You are an elite social media copywriter and growth strategist who "
        "writes native, high-engagement content for each platform. You "
        "understand platform algorithms, hooks, pacing and hashtag etiquette. "
        "You always return ONLY valid JSON that matches the requested schema — "
        "no markdown, no code fences, no commentary."
    )


def build_user_prompt(req: GeneratePostRequest, platform: Platform) -> str:
    spec = PLATFORM_SPECS[platform]

    # Describe the exact JSON object we want back.
    schema: dict[str, str] = {
        "text": f"the main post copy for {spec.label}, within {spec.char_limit} characters",
    }
    if req.variants:
        schema["short_version"] = "a tighter, shorter variant of the post"
        schema["long_version"] = "a more detailed, longer variant of the post"
    if req.include_hashtags:
        schema["hashtags"] = "an array of hashtag strings WITHOUT the # symbol"

    lines = [
        f"Write a {req.tone.value} social media post for {spec.label}.",
        "",
        f"TOPIC: {req.topic}",
    ]
    if req.audience:
        lines.append(f"TARGET AUDIENCE: {req.audience}")
    lines += [
        "",
        f"PLATFORM VOICE: {spec.voice}",
        f"IDEAL LENGTH: {spec.sweet_spot}.",
        f"HARD LIMIT: stay within {spec.char_limit} characters.",
    ]
    if req.include_hashtags:
        lines.append(f"HASHTAGS: {spec.hashtags}.")
    else:
        lines.append("HASHTAGS: do not include any hashtags.")

    lines += [
        "",
        "Return ONLY a JSON object with exactly these keys:",
        json.dumps(schema, indent=2),
    ]
    if not req.include_hashtags:
        lines.append('If you include a "hashtags" key, it must be an empty array.')

    return "\n".join(lines)
