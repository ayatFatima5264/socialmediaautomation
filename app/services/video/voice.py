"""Voice Studio's service layer — the catalogue, and turning text into audio.

Voice Studio is required to work with no project, so nothing here takes one. It
takes a user and some text, and returns an asset. Connecting that asset to a
project is a separate, explicit action (`projects.attach_asset`).

Three things live here rather than in a provider:

  * **One catalogue across providers.** The UI shows a single voice list, and
    each voice carries the provider that owns it — so picking a Groq voice while
    `TTS_PROVIDER=edge` just works, and a provider whose key is missing drops
    out of the list instead of appearing and then failing.
  * **Roman Urdu.** No TTS engine has a "Roman Urdu" voice, because it is not a
    locale — it is Urdu written in Latin script. It is served by routing that
    language choice to the Urdu voices, which pronounce transliterated text
    correctly. Presenting it as its own language is honest to the user and
    costs one mapping here.
  * **Metering and storage.** Every synthesis records the seconds produced and
    stores the audio as an asset, so it survives a page reload — which is the
    difference between a studio and a demo.
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace

from sqlalchemy.orm import Session

from app.config import settings
from app.models.video_asset import VideoAsset
from app.services.video import assets as asset_service
from app.services.video import metering
from app.services.video.providers import (
    MediaProviderConfigError,
    MediaProviderError,
    SpeechRequest,
    Voice,
    get_tts_provider,
    get_tts_providers,
)

logger = logging.getLogger(__name__)


class VoiceError(RuntimeError):
    """A voice operation was refused. The message is user-facing."""


# The languages Voice Studio surfaces first, in the order the dropdown shows
# them. Every other locale the providers offer is still listed, underneath —
# this is priority, not a whitelist.
FEATURED_LANGUAGES = ("en-US", "en-GB", "ur-PK", "ur-IN", "hi-IN", "ar-SA")

# Roman Urdu is Urdu in Latin script, not a locale any engine ships. Selecting
# it uses the Urdu voices; see the module docstring.
ROMAN_URDU = "ur-Latn"
_ROMAN_URDU_SOURCE = "ur-PK"

# Prosody sliders. Clamped here rather than trusted from the client, because a
# rate of 40 is not a fast voice — it is an unusable file the user waited for.
RATE_RANGE = (0.5, 2.0)
PITCH_RANGE = (0.5, 1.5)
VOLUME_RANGE = (0.0, 1.0)


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    low, high = bounds
    return max(low, min(high, float(value)))


# ---------------------------------------------------------------------------
# Delivery styles
# ---------------------------------------------------------------------------
# A style is a *prosody macro*: a named pair of rate and pitch multipliers that
# compose with whatever the user set on the sliders.
#
# It is built this way rather than passed through to the provider because
# almost no provider has a style parameter. Azure's neural voices do;
# edge-tts (the same voices, different endpoint) does not expose it, Groq's
# PlayAI has none, and `/audio/speech` has none. A "Style" dropdown that only
# worked on a provider nobody has configured would be a control that silently
# does nothing — so these are implemented where they can actually take effect.
#
# `Voice.styles` stays on the provider contract for a provider that does have
# native ones; `SpeechRequest.style` carries it, and a provider that ignores it
# is behaving correctly.
#
# The numbers are deliberately small. A style should sound like the same person
# reading differently, not like a different voice.
STYLES: dict[str, dict] = {
    "default": {
        "label": "Default",
        "description": "The voice as the provider ships it.",
        "rate": 1.0,
        "pitch": 1.0,
    },
    "narration": {
        "label": "Narration",
        "description": "Measured and even, for voice-over under footage.",
        "rate": 0.94,
        "pitch": 0.98,
    },
    "conversational": {
        "label": "Conversational",
        "description": "Slightly quicker and lighter, like talking to camera.",
        "rate": 1.06,
        "pitch": 1.02,
    },
    "energetic": {
        "label": "Energetic",
        "description": "Fast and bright. Suits short-form hooks.",
        "rate": 1.16,
        "pitch": 1.06,
    },
    "calm": {
        "label": "Calm",
        "description": "Slower and lower. For explainers and wellbeing content.",
        "rate": 0.88,
        "pitch": 0.96,
    },
    "announcer": {
        "label": "Announcer",
        "description": "Deliberate and low, for intros and promos.",
        "rate": 0.92,
        "pitch": 0.92,
    },
}

DEFAULT_STYLE = "default"


def style_options() -> list[dict]:
    """The style list the UI builds its dropdown from.

    The multipliers are included rather than hidden: the panel can then say
    what a style actually does, which is the difference between a control the
    user can predict and one they have to keep trying.
    """
    return [
        {
            "key": key,
            "label": spec["label"],
            "description": spec["description"],
            "rate": spec["rate"],
            "pitch": spec["pitch"],
        }
        for key, spec in STYLES.items()
    ]


def apply_style(
    style: str | None, rate: float, pitch: float
) -> tuple[float, float, str]:
    """Compose a style with the user's sliders. Returns (rate, pitch, style).

    Composed rather than overriding: the sliders are the user's own adjustment
    and a style must not silently discard them. Both results are clamped to the
    same ranges a bare slider is, so no combination can produce an unusable
    file — "Energetic" plus a rate of 2.0 is still 2.0, not 2.3.
    """
    key = (style or DEFAULT_STYLE).lower()
    spec = STYLES.get(key)
    if spec is None:
        key, spec = DEFAULT_STYLE, STYLES[DEFAULT_STYLE]

    return (
        _clamp(rate * spec["rate"], RATE_RANGE),
        _clamp(pitch * spec["pitch"], PITCH_RANGE),
        key,
    )


async def list_voices() -> list[Voice]:
    """Every voice from every usable provider, merged.

    A provider that fails to answer is logged and skipped: one unreachable
    catalogue must not empty the dropdown for the provider that is working.
    """
    merged: list[Voice] = []
    for provider in get_tts_providers():
        try:
            merged.extend(await provider.list_voices())
        except MediaProviderError as exc:
            logger.warning("Voice catalogue unavailable from %s: %s", provider.name, exc)

    # Featured languages first, then everything else alphabetically. Within a
    # language, female and male voices interleave by name rather than being
    # grouped, so neither is systematically at the bottom of a long list.
    def sort_key(voice: Voice) -> tuple:
        try:
            rank = FEATURED_LANGUAGES.index(voice.language)
        except ValueError:
            rank = len(FEATURED_LANGUAGES)
        return (rank, voice.language, voice.label)

    merged.sort(key=sort_key)
    return merged


def languages_from(voices: list[Voice]) -> list[dict]:
    """The language list the UI builds its dropdown from.

    Derived from the voices actually available, plus the Roman Urdu entry —
    a language with no voices behind it is a dead end in a dropdown.
    """
    seen: dict[str, dict] = {}
    for voice in voices:
        entry = seen.setdefault(
            voice.language,
            {
                "code": voice.language,
                "label": voice.language_label,
                "voices": 0,
                "featured": voice.language in FEATURED_LANGUAGES,
            },
        )
        entry["voices"] += 1

    languages = list(seen.values())

    if _ROMAN_URDU_SOURCE in seen:
        languages.append(
            {
                "code": ROMAN_URDU,
                "label": "Roman Urdu",
                "voices": seen[_ROMAN_URDU_SOURCE]["voices"],
                "featured": True,
                # Stated in the payload so the UI can explain the choice rather
                # than implying a separate engine exists.
                "note": "Urdu written in Latin script, spoken by the Urdu voices.",
            }
        )

    languages.sort(key=lambda item: (not item["featured"], item["label"]))
    return languages


def resolve_language(code: str | None) -> str | None:
    """Map a UI language choice onto a locale a provider actually has."""
    if not code:
        return None
    return _ROMAN_URDU_SOURCE if code == ROMAN_URDU else code


def voices_for_language(voices: list[Voice], code: str | None) -> list[Voice]:
    resolved = resolve_language(code)
    if not resolved:
        return voices
    return [voice for voice in voices if voice.language == resolved]


def _provider_name_for(voice_id: str, voices: list[Voice]) -> str | None:
    for voice in voices:
        if voice.id == voice_id:
            return voice.provider
    return None


def _pick_fallback_voice(
    source_voice: Voice,
    fallback_voices: list[Voice],
    provider_name: str,
) -> Voice:
    """The fallback provider's closest voice to the one the user picked.

    The candidate list is **only** the fallback provider's own catalogue. A
    voice from any other provider is not an option here: it would belong to a
    provider whose own fallback iteration is still to come, and matching it
    would hand the request to an engine nobody selected. The source voice is
    matched against it by language *and* gender first — an exact locale and a
    similar voice — then by language alone, so a fallback with no exact-locale
    match still speaks the same language. Both compare the *fallback* voice's
    language to the *source* voice's; a match that compares the source to
    itself would accept the first voice in the list regardless of what the
    user picked.
    """
    source_language = (source_voice.language or "").lower()
    source_gender = (source_voice.gender or "").lower()

    exact = next(
        (
            voice
            for voice in fallback_voices
            if (voice.language or "").lower() == source_language
            and (voice.gender or "").lower() == source_gender
        ),
        None,
    )
    if exact is not None:
        return exact

    same_language = next(
        (
            voice
            for voice in fallback_voices
            if (voice.language or "").lower().split("-")[0]
            == source_language.split("-")[0]
        ),
        None,
    )
    if same_language is not None:
        return same_language

    if fallback_voices:
        # Last resort: keep the synthesis alive over a perfect voice match.
        return fallback_voices[0]

    raise MediaProviderError(
        f"{provider_name} has no voices to fall back to."
    )


# Voice Studio lets the writer mark a pause. SSML is not accepted from users —
# it would be an injection surface and providers disagree on it — so the marker
# is a bare `[pause]`, converted here to real silence by splitting the text and
# letting the engine's own sentence pacing do the work. Anything longer than a
# beat is a timeline edit, not a synthesis parameter.
_PAUSE = re.compile(r"\[\s*pause\s*\]", re.IGNORECASE)


def clean_text(text: str) -> str:
    """Normalise what the user typed into what the engine should say."""
    if not text or not text.strip():
        raise VoiceError("There is nothing to say — enter some text first.")

    # A pause marker becomes a sentence break, which every engine already
    # renders as a natural gap.
    cleaned = _PAUSE.sub(" … ", text)
    # Collapse the runs of blank lines a pasted script arrives with; they
    # otherwise read as long, uneven silences.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    if len(cleaned) > settings.tts_max_characters:
        raise VoiceError(
            f"That is {len(cleaned):,} characters. One voice-over can be up to "
            f"{settings.tts_max_characters:,} — split a longer script into "
            f"sections and generate them one at a time."
        )
    return cleaned


async def synthesize(
    db: Session,
    *,
    user_id: int,
    text: str,
    voice_id: str,
    rate: float = 1.0,
    pitch: float = 1.0,
    volume: float = 1.0,
    style: str | None = None,
    provider_name: str | None = None,
    project_id: int | None = None,
    title: str | None = None,
    save: bool = True,
    source: str = "voice_studio",
    extra_meta: dict | None = None,
) -> tuple[VideoAsset | None, dict]:
    """Generate a voice-over and store it.

    Returns `(asset, details)`. `asset` is None when `save` is False, which is
    what the preview path uses — a preview the user rejects should not leave a
    file in their library or bytes in the bucket.
    """
    cleaned = clean_text(text)

    if not voice_id:
        raise VoiceError("Choose a voice first.")

    # Charged against the allowance before the work happens, using a rough
    # estimate — roughly 15 characters per second of speech at normal pace.
    # The recorded figure afterwards is the measured duration, not this.
    metering.check_allowance(
        db,
        user_id=user_id,
        metric="voice_seconds",
        requested=len(cleaned) / 15.0,
    )

    # The voice knows its own provider, so a request never has to say which
    # engine to use — and a voice from a provider that is no longer configured
    # fails with a clear message instead of being sent to the wrong engine.
    if not provider_name:
        provider_name = _provider_name_for(voice_id, await list_voices())
    if not provider_name:
        raise VoiceError(
            "That voice could not be found in any configured provider. "
            "Re-choose a voice from the catalogue and try again."
        )

    try:
        provider = get_tts_provider(provider_name)
    except MediaProviderConfigError as exc:
        raise VoiceError(str(exc)) from exc

    # The style composes with the sliders before anything is sent, so what the
    # provider receives is the single effective value — and `details` reports
    # it, so the UI never has to guess what a style did.
    effective_rate, effective_pitch, style_key = apply_style(
        style, _clamp(rate, RATE_RANGE), _clamp(pitch, PITCH_RANGE)
    )

    request = SpeechRequest(
        text=cleaned,
        voice_id=voice_id,
        rate=effective_rate,
        pitch=effective_pitch,
        volume=_clamp(volume, VOLUME_RANGE),
        style=style_key if style_key != DEFAULT_STYLE else None,
    )

    provider_names = [provider_name] + [
        name
        for name in settings.tts_fallback_providers
        if name != provider_name
    ]

    result = None
    last_error = None

    # The selected voice is looked up once, in its own provider's catalogue.
    # Looking the id up in a merged list is exactly what hands the request to
    # the wrong engine when two providers happen to share a voice id.
    source_voice = next(
        (voice for voice in await provider.list_voices() if voice.id == voice_id),
        None,
    )

    for current_provider_name in provider_names:
        try:
            current_provider = get_tts_provider(current_provider_name)

            current_request = request

            # Use a voice belonging to the fallback provider.
            if current_provider_name != provider_name:
                if source_voice is None:
                    raise MediaProviderError(
                        f"Voice {voice_id!r} could not be found in the "
                        f"{provider_name} catalogue."
                    )

                fallback_voices = await current_provider.list_voices()
                fallback_voice = _pick_fallback_voice(
                    source_voice,
                    fallback_voices,
                    current_provider_name,
                )

                # The text and prosody the user set are the request; only the
                # voice has to be the fallback's own.
                current_request = replace(request, voice_id=fallback_voice.id)

            result = await current_provider.synthesize(current_request)

            if result:
                break

        except MediaProviderConfigError as exc:
            # A missing API key is the operator's problem and the route answers
            # 503 for it — it will not succeed on retry, so the fallback chain
            # is not consulted at all for the chosen provider. A *fallback*
            # provider that is unconfigured is different: it is skipped and the
            # next one is tried, which is what lets the keyless "edge" entry
            # stay in the default chain without a working deploy depending on
            # keys it does not have.
            if current_provider_name == provider_name:
                raise
            last_error = exc
            logger.warning(
                "TTS fallback provider %s is not configured: %s",
                current_provider_name,
                exc,
            )
            continue

        except MediaProviderError as exc:
            last_error = exc
            logger.warning(
                "TTS provider %s failed: %s",
                current_provider_name,
                exc,
            )
            continue

    if result is None:
        raise VoiceError(
            f"All configured voice providers failed. Last error: {last_error}"
        )

    details = {
        # The bytes themselves. Carried on the result because the preview path
        # has nowhere else to get them: it deliberately stores nothing, so
        # there is no asset and no URL to read back. The generate path ignores
        # this field — the audio is already in memory either way, so returning
        # it costs nothing and saves the preview a round trip through storage
        # it is specifically avoiding.
        "audio": result.audio,
        "provider": result.provider,
        "voice_id": result.voice_id,
        "duration_seconds": result.duration_seconds,
        "content_type": result.content_type,
        "size_bytes": len(result.audio),
        "characters": len(cleaned),
        # What the user asked for…
        "style": style_key,
        "rate": _clamp(rate, RATE_RANGE),
        "pitch": _clamp(pitch, PITCH_RANGE),
        "volume": request.volume,
        # …and what the style turned it into.
        "effective_rate": request.rate,
        "effective_pitch": request.pitch,
        "word_marks": result.word_marks,
    }

    if not save:
        return None, details

    asset = asset_service.store_asset(
        db,
        user_id=user_id,
        kind="voice",
        data=result.audio,
        content_type=result.content_type,
        title=(title or _title_from(cleaned)),
        filename=f"voiceover.{'wav' if 'wav' in result.content_type else 'mp3'}",
        project_id=project_id,
        # Everything needed to make this take again. The text is kept so a
        # voice-over can be regenerated with a different voice or style without
        # the user retyping it — which is exactly what "Regenerate" needs — and
        # the settings are kept so the regeneration starts from what produced
        # this one rather than from the panel's current state.
        meta={
            "text": cleaned,
            "voice_id": result.voice_id,
            "provider": result.provider,
            "style": style_key,
            "rate": details["rate"],
            "pitch": details["pitch"],
            "volume": request.volume,
            "effective_rate": request.rate,
            "effective_pitch": request.pitch,
            "word_marks": result.word_marks[:2000],
            **(extra_meta or {}),
        },
        # Already measured by the provider; decoding it again would be waste.
        probe=False,
        duration_seconds=result.duration_seconds,
    )

    metering.record(
        db,
        user_id=user_id,
        metric="voice_seconds",
        quantity=result.duration_seconds,
        source=source,
        project_id=project_id,
        meta={"provider": result.provider, "voice_id": result.voice_id},
    )

    return asset, details


# ---------------------------------------------------------------------------
# Segments — the unit "regenerate this part" operates on
# ---------------------------------------------------------------------------
# A script is written in paragraphs and a voice-over is rerecorded in
# paragraphs. Splitting on blank lines is what lets one section be redone
# without regenerating — and re-paying for — the whole thing.

# A blank line, however much whitespace is in it.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n+")


def split_segments(text: str) -> list[dict]:
    """Break a script into the blocks the studio can regenerate individually.

    Each segment carries its character offsets in the original text, so the UI
    can highlight the part of the textarea a take corresponds to, and so a
    regeneration can be written back into exactly the right place.

    A script with no blank lines is one segment. That is correct, not a
    degenerate case: an unbroken paragraph has no natural seam to record
    separately, and inventing one at a sentence boundary would produce takes
    that do not join cleanly.
    """
    if not text or not text.strip():
        return []

    segments: list[dict] = []
    cursor = 0
    for index, block in enumerate(_PARAGRAPH_BREAK.split(text)):
        stripped = block.strip()
        if not stripped:
            cursor += len(block)
            continue

        # Where this block actually starts in the original, so the offsets
        # survive the strip and the split.
        start = text.find(stripped, cursor)
        if start < 0:  # pragma: no cover - only if `text` was mutated
            start = cursor
        end = start + len(stripped)
        cursor = end

        segments.append(
            {
                "index": index,
                "text": stripped,
                "start": start,
                "end": end,
                "characters": len(stripped),
            }
        )

    # Re-index after skipping blanks, so the numbers the UI shows are 0..n-1
    # with no gaps.
    for position, segment in enumerate(segments):
        segment["index"] = position
    return segments


def _title_from(text: str) -> str:
    """A readable asset title from the first few words of the script."""
    words = " ".join(text.split())[:60].strip()
    return (words + "…") if len(" ".join(text.split())) > 60 else (words or "Voice-over")
