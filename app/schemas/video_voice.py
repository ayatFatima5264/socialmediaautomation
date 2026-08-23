"""Request and response shapes for Voice Studio.

The prosody fields carry their real ranges as validation rather than as
comments. A rate of 40 is not a fast voice — it is an unusable file the user
waited two minutes for — and rejecting it at the boundary is cheaper than
clamping it silently and leaving them wondering why the slider did nothing.
(The service clamps as well; this is the layer that can explain itself.)
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class VoiceOption(BaseModel):
    id: str
    provider: str
    label: str
    language: str
    language_label: str
    gender: str
    #: False for providers with no prosody parameters (Groq's PlayAI, and
    #: `/audio/speech`, which has speed only). The UI disables the sliders
    #: rather than offering controls that do nothing.
    supports_prosody: bool
    #: Provider-native styles, when it has any. Descriptive personality tags on
    #: edge-tts; empty almost everywhere. Not the same thing as the delivery
    #: styles below, which work on every provider.
    styles: list[str] = Field(default_factory=list)


class LanguageOption(BaseModel):
    code: str
    label: str
    voices: int
    featured: bool
    note: str | None = None


class StyleOption(BaseModel):
    key: str
    label: str
    description: str
    rate: float
    pitch: float


class VoiceCatalogue(BaseModel):
    voices: list[VoiceOption]
    languages: list[LanguageOption]
    styles: list[StyleOption]
    #: Providers that actually answered. A provider with no key drops out.
    providers: list[str]
    #: Every provider this build knows how to talk to, configured or not.
    available_providers: list[str]
    max_characters: int
    preview_characters: int
    default_style: str


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


class _SpeechSettings(BaseModel):
    """The controls shared by preview and generate."""

    voice_id: str = Field(min_length=1, max_length=200)
    style: str | None = None
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=1.5)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)


class VoicePreviewRequest(_SpeechSettings):
    #: Only the first `preview_characters` are spoken — the response says so.
    text: str = Field(min_length=1)


class VoiceGenerateRequest(_SpeechSettings):
    text: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=200)
    #: Optional, and that is the product rule made structural: Voice Studio
    #: works with no project at all.
    project_id: int | None = None
    #: Which block of a longer script this take covers, when regenerating one
    #: section rather than the whole thing.
    segment_index: int | None = Field(default=None, ge=0)


class VoicePreviewResult(BaseModel):
    """A sample, inline. Nothing was stored — see the route docstring."""

    audio_base64: str
    content_type: str
    duration_seconds: float
    provider: str
    voice_id: str
    style: str
    #: What the style turned the sliders into, so the panel can show the real
    #: numbers instead of implying the style had no effect.
    effective_rate: float
    effective_pitch: float
    characters: int
    #: True when the text was longer than a preview speaks.
    truncated: bool


class VoiceTake(BaseModel):
    """One generated voice-over, with the settings that produced it.

    Those settings travel with the take so "Regenerate" starts from what made
    it, rather than from whatever the panel happens to show now.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None = None
    title: str
    filename: str | None = None
    content_type: str
    size_bytes: int
    duration_seconds: float
    url: str
    created_at: datetime

    text: str
    voice_id: str
    provider: str
    style: str
    rate: float
    pitch: float
    volume: float
    segment_index: int | None = None
    #: Per-word timings when the provider emits them. Empty is normal.
    word_marks: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


class VoiceSegmentRequest(BaseModel):
    text: str = ""


class VoiceSegment(BaseModel):
    index: int
    text: str
    #: Character offsets in the original script, so the UI can highlight the
    #: part of the textarea a take corresponds to.
    start: int
    end: int
    characters: int


class VoiceSegmentsResult(BaseModel):
    segments: list[VoiceSegment]
    characters: int
    max_characters: int
