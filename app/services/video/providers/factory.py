"""Media provider registry + selection.

The single switch point for Video Studio's voice and transcription backends,
mirroring app/services/providers/factory.py so the two read the same way:

    TTS_PROVIDER=edge|groq|custom
    TRANSCRIPTION_PROVIDER=groq|openai

Instances are cached per process. Both hold an HTTP client or a fetched
catalogue that should outlive a single request, and neither carries per-user
state — a provider is configuration, not session.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings
from app.services.video.providers.base import (
    MediaProviderConfigError,
    TranscriptionProvider,
    TTSProvider,
)
from app.services.video.providers.edge_tts_provider import EdgeTTSProvider
from app.services.video.providers.elevenlabs_tts import ElevenLabsTTSProvider
from app.services.video.providers.google_tts import GoogleTTSProvider
from app.services.video.providers.cartesia_tts import CartesiaTTSProvider
from app.services.video.providers.groq_tts import GroqTTSProvider
from app.services.video.providers.openai_speech import OpenAISpeechProvider
from app.services.video.providers.whisper import WhisperProvider

logger = logging.getLogger(__name__)

#: What the API advertises to clients.
available_tts_providers: list[str] = [
    "elevenlabs",
    "google",
    "edge",
    "cartesia",
    "groq",
    "custom",
]
available_transcription_providers: list[str] = ["groq", "openai"]


def _build_tts(name: str) -> TTSProvider:
    name = (name or "").lower()

    if name == "elevenlabs":
        return ElevenLabsTTSProvider(
            api_key=settings.elevenlabs_api_key,
            model=settings.elevenlabs_tts_model,
            base_url=settings.elevenlabs_tts_base_url,
        )

    if name == "google":
        return GoogleTTSProvider(
            api_key=settings.google_tts_api_key,
            base_url=settings.google_tts_base_url,
        )

    if name == "cartesia":
        return CartesiaTTSProvider(
            api_key=settings.cartesia_api_key,
            model=settings.cartesia_tts_model,
            base_url=settings.cartesia_tts_base_url,
            version=settings.cartesia_version,
        )

    if name == "edge":
        return EdgeTTSProvider()

    if name == "groq":
        return GroqTTSProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_tts_model,
            base_url=settings.groq_base_url,
            timeout=settings.ai_request_timeout * 4,
        )

    if name == "custom":
        # Any OpenAI-compatible /audio/speech server, including a local
        # open-source one. See openai_speech.py.
        # Timeout is 8x the base (vs 4x for Groq) because self-hosted models
        # (Piper, Coqui XTTS, Kokoro) can be slower on cold start or when
        # loading large models on first request.
        return OpenAISpeechProvider(
            timeout=settings.ai_request_timeout * 8
        )

    raise MediaProviderConfigError(
        f"Unknown TTS provider {name!r}. "
        f"Available: {', '.join(available_tts_providers)}"
    )


@lru_cache
def _cached_tts(name: str) -> TTSProvider:
    return _build_tts(name)


def get_tts_provider(name: str | None = None) -> TTSProvider:
    """The configured voice provider, or a named override.

    An override is what lets one Voice Studio request use a provider that is
    not the default — for example picking a Groq voice from the merged
    catalogue while `TTS_PROVIDER` stays on edge.
    """
    return _cached_tts((name or settings.tts_provider).lower())


def get_tts_providers() -> list[TTSProvider]:
    """Every provider that is actually usable right now.

    Voice Studio builds one catalogue out of all of them, so a provider whose
    key is missing must drop out silently rather than failing the whole list —
    the same rule the AI text fallback chain follows.
    """
    names = [settings.tts_provider.lower()]
    for extra in available_tts_providers:
        if extra not in names:
            names.append(extra)

    usable: list[TTSProvider] = []
    for name in names:
        try:
            usable.append(_cached_tts(name))
        except MediaProviderConfigError as exc:
            logger.debug("TTS provider %r unavailable: %s", name, exc)
    return usable


def _build_transcription(name: str) -> TranscriptionProvider:
    name = (name or "").lower()
    if name == "groq":
        return WhisperProvider(
            name="groq",
            api_key=settings.groq_api_key,
            model=settings.groq_transcription_model,
            base_url=settings.groq_base_url,
            timeout=settings.transcription_request_timeout,
        )
    if name == "openai":
        base = settings.transcription_base_url or "https://api.openai.com/v1"
        return WhisperProvider(
            name="openai",
            api_key=settings.transcription_api_key,
            model=settings.transcription_model,
            base_url=base,
            timeout=settings.transcription_request_timeout,
        )
    raise MediaProviderConfigError(
        f"Unknown transcription provider {name!r}. "
        f"Available: {', '.join(available_transcription_providers)}"
    )


@lru_cache
def _cached_transcription(name: str) -> TranscriptionProvider:
    return _build_transcription(name)


def get_transcription_provider(name: str | None = None) -> TranscriptionProvider:
    return _cached_transcription((name or settings.transcription_provider).lower())


def reset_provider_cache() -> None:
    """Drop cached providers. For tests that change configuration."""
    _cached_tts.cache_clear()
    _cached_transcription.cache_clear()
