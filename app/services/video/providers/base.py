"""Provider contracts for Video Studio's media AI.

AutoSocial already abstracts text generation (app/services/providers) and image
generation (app/services/image_service). Video Studio adds two more kinds of
model, and they get the same treatment for the same reason: the free provider
that works today is not the provider this will ship on forever, and swapping one
must not be a rewrite.

    AIProvider              text            (existing, reused unchanged)
    ImageProvider           visuals         (existing, reused unchanged)
    TTSProvider             voice-over      <- here
    TranscriptionProvider   subtitles       <- here

Both contracts are deliberately narrow. A provider turns an input into audio, or
audio into timed text. Anything about *how the product uses that* — voice
catalogues merged across providers, SRT formatting, cue splitting, metering —
lives in the service layer above, so a new provider is one class and one line in
the factory.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class MediaProviderError(RuntimeError):
    """A provider failed at request time (network, API error, bad response)."""


class MediaProviderConfigError(MediaProviderError):
    """A provider is missing required configuration (e.g. an API key)."""


class UnsupportedVoiceError(MediaProviderError):
    """The requested voice is not one this provider can speak."""


# ---------------------------------------------------------------------------
# Text to speech
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Voice:
    """One selectable voice, normalised across providers.

    `id` is provider-scoped and opaque to the UI; `provider` is what routes a
    synthesis request back to whoever owns it. Everything else exists so the
    Voice Studio dropdowns can be built from the catalogue rather than from a
    hardcoded list that drifts.
    """

    id: str
    provider: str
    label: str
    language: str          # BCP-47, e.g. "en-US", "ur-PK"
    language_label: str    # "English (United States)"
    gender: str            # "male" | "female" | "neutral"
    #: True when the provider can shift rate/pitch/volume for this voice.
    supports_prosody: bool = True
    #: Free-form, e.g. "news", "cheerful". Empty when the provider has none.
    styles: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpeechRequest:
    """What to say and how. Percentages are relative to the voice's default.

    `rate`, `pitch` and `volume` are *multipliers around 1.0* rather than
    provider-native strings, because every provider spells those differently
    and the UI must not have to know which one is selected.
    """

    text: str
    voice_id: str
    rate: float = 1.0       # 0.5 – 2.0
    pitch: float = 1.0      # 0.5 – 1.5
    volume: float = 1.0     # 0.0 – 1.0
    output_format: str = "mp3"
    #: A provider-native style ("cheerful", "newscast"), when the voice lists
    #: one in `Voice.styles`. A provider that has no native styles ignores this
    #: — the delivery styles Voice Studio offers are prosody macros applied
    #: *before* this point (see app/services/video/voice.py), so they work on
    #: every provider rather than only on the ones with a style parameter.
    style: str | None = None


@dataclass(frozen=True)
class SpeechResult:
    """Rendered audio plus what it cost and how it was made."""

    audio: bytes
    content_type: str
    #: Measured from the encoded audio, not estimated from the text length.
    duration_seconds: float
    voice_id: str
    provider: str
    #: Word timings when the provider emits them — the basis for karaoke-style
    #: subtitles. Empty is normal and callers must handle it.
    word_marks: list[dict] = field(default_factory=list)


class TTSProvider(ABC):
    #: Stable identifier used for selection and reporting (e.g. "edge").
    name: str = "base"

    @abstractmethod
    async def list_voices(self) -> list[Voice]:
        """Every voice this provider can speak. May be network-backed."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        """Turn text into audio. Raises MediaProviderError on failure."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TranscriptSegment:
    """One timed line of speech. The unit a subtitle cue is built from."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptWord:
    """One timed word, when the provider reports word-level timestamps.

    Needed for word highlighting and karaoke subtitle presets. A provider that
    cannot supply these returns an empty list, and the studio falls back to
    segment timing rather than faking per-word positions.
    """

    start: float
    end: float
    word: str


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    duration_seconds: float
    segments: list[TranscriptSegment]
    words: list[TranscriptWord] = field(default_factory=list)
    provider: str = ""
    model: str = ""


class TranscriptionProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def transcribe(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        language: str | None = None,
        word_timestamps: bool = True,
        translate_to_english: bool = False,
    ) -> Transcript:
        """Turn audio into timed text.

        `language` is a hint, not a filter — passing None asks the provider to
        detect it, which is what the Subtitle Studio's "Auto detect" sends.
        """
        raise NotImplementedError
