"""Groq TTS — a keyed alternative voice provider.

Uses the same GROQ_API_KEY the text generator already needs, over the
OpenAI-compatible `/audio/speech` route. It exists to prove the abstraction is
real rather than decorative: selecting it is `TTS_PROVIDER=groq` and nothing
else in Video Studio changes.

It is **not** the default, for a reason worth stating plainly: Groq's PlayAI
voices are English (and separately Arabic) only. The brief requires Urdu, so
making this the default would quietly drop a stated requirement. It also has no
prosody controls — rate, pitch and volume are ignored, and `Voice.supports_
prosody` is False so the UI can disable those sliders rather than offering
controls that do nothing.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.services.video.ffmpeg import FFmpegError, probe_bytes
from app.services.video.providers.base import (
    MediaProviderConfigError,
    MediaProviderError,
    SpeechRequest,
    SpeechResult,
    TTSProvider,
    Voice,
)

logger = logging.getLogger(__name__)

# Groq publishes a fixed voice list per model rather than a catalogue endpoint,
# so it is named here. A voice added upstream is one line.
_ENGLISH_VOICES: tuple[tuple[str, str], ...] = (
    ("Arista-PlayAI", "female"),
    ("Atlas-PlayAI", "male"),
    ("Basil-PlayAI", "male"),
    ("Briggs-PlayAI", "male"),
    ("Calum-PlayAI", "male"),
    ("Celeste-PlayAI", "female"),
    ("Cheyenne-PlayAI", "female"),
    ("Chip-PlayAI", "male"),
    ("Cillian-PlayAI", "male"),
    ("Deedee-PlayAI", "female"),
    ("Fritz-PlayAI", "male"),
    ("Gail-PlayAI", "female"),
    ("Indigo-PlayAI", "neutral"),
    ("Mamaw-PlayAI", "female"),
    ("Mason-PlayAI", "male"),
    ("Mikail-PlayAI", "male"),
    ("Mitch-PlayAI", "male"),
    ("Quinn-PlayAI", "neutral"),
    ("Thunder-PlayAI", "male"),
)


class GroqTTSProvider(TTSProvider):
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout: float,
    ) -> None:
        if not api_key:
            raise MediaProviderConfigError(
                "GROQ_API_KEY is not set — the Groq voice provider needs it."
            )
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def list_voices(self) -> list[Voice]:
        return [
            Voice(
                id=name,
                provider=self.name,
                label=name.removesuffix("-PlayAI"),
                language="en-US",
                language_label="English (US)",
                gender=gender,
                # The API takes no speed, pitch or volume parameter.
                supports_prosody=False,
            )
            for name, gender in _ENGLISH_VOICES
        ]

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        payload = {
            "model": self.model,
            "voice": request.voice_id,
            "input": request.text,
            "response_format": "wav",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/audio/speech",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise MediaProviderError(f"Groq TTS request failed: {exc}") from exc

        if response.status_code != 200:
            # The body is JSON on error and audio on success, so it is only
            # safe to read as text here.
            raise MediaProviderError(
                f"Groq TTS returned {response.status_code}: "
                f"{response.text[:300]}"
            )

        audio = response.content
        if not audio:
            raise MediaProviderError("Groq TTS returned no audio.")

        try:
            duration = probe_bytes(audio, suffix=".wav").duration_seconds
        except FFmpegError:
            duration = 0.0
            logger.warning("Could not measure Groq TTS audio duration")

        return SpeechResult(
            audio=audio,
            content_type="audio/wav",
            duration_seconds=duration,
            voice_id=request.voice_id,
            provider=self.name,
        )
