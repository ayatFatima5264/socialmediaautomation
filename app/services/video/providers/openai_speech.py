"""Any server that speaks OpenAI's `/audio/speech` — including a local one.

This is the provider that makes "Voice Studio is not tied to one vendor" true
rather than merely claimed. It talks to a base URL, not to a company, and the
`/audio/speech` shape it uses is what the self-hostable open-source TTS servers
already expose:

    openedai-speech      Piper + Coqui XTTS behind an OpenAI-compatible API
    Kokoro-FastAPI       Kokoro-82M, same route
    LocalAI              many backends, same route
    OpenAI               the original

So running Video Studio entirely offline is configuration, not code:

    TTS_PROVIDER=custom
    CUSTOM_TTS_BASE_URL=http://localhost:8080/v1
    CUSTOM_TTS_VOICES=alloy:female:en-US,echo:male:en-US
    CUSTOM_TTS_API_KEY=            # most local servers need none

**Why the voice list is configured rather than fetched.** There is no voice
catalogue route in this API — `/audio/speech` takes a voice name and that is
all. Guessing a catalogue would mean offering voices the server may not have.
Naming them in one setting is honest, and it is the only thing about this
provider that has to be told rather than discovered.

Nothing here is specific to any one of those servers. If a future provider
needs headers or a body field none of them use, that is a new class next to
this one — which is the whole point of the abstraction.
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
    UnsupportedVoiceError,
    Voice,
)

logger = logging.getLogger(__name__)

# What the server sends back, and what we tell ffmpeg to expect. WAV is the
# default because every local engine can produce it without an MP3 encoder,
# which is not a given in a slim container.
_FORMATS = {
    "wav": ("audio/wav", ".wav"),
    "mp3": ("audio/mpeg", ".mp3"),
    "opus": ("audio/ogg", ".ogg"),
    "aac": ("audio/aac", ".aac"),
    "flac": ("audio/flac", ".flac"),
}


def parse_voice_spec(raw: str | None) -> list[tuple[str, str, str]]:
    """Read CUSTOM_TTS_VOICES into (id, gender, locale) triples.

        "alloy:female:en-US, kokoro_bella:female:en-GB, piper_asad:male:ur-PK"

    Gender and locale are optional and default to neutral / en-US, so the
    shortest usable value is a bare comma-separated list of voice names. A
    malformed entry is skipped with a warning rather than taking the whole
    provider down — one typo in an environment variable should not remove every
    voice from the dropdown.
    """
    voices: list[tuple[str, str, str]] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [part.strip() for part in chunk.split(":")]
        voice_id = parts[0]
        if not voice_id:
            logger.warning("Skipping malformed CUSTOM_TTS_VOICES entry %r", chunk)
            continue
        gender = (parts[1] if len(parts) > 1 and parts[1] else "neutral").lower()
        locale = parts[2] if len(parts) > 2 and parts[2] else "en-US"
        voices.append((voice_id, gender, locale))
    return voices


def is_configured() -> bool:
    """A base URL and at least one voice. Without either there is nothing to offer."""
    return bool(settings.custom_tts_base_url and parse_voice_spec(settings.custom_tts_voices))


class OpenAISpeechProvider(TTSProvider):
    name = "custom"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        voices: str | None = None,
        output_format: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or settings.custom_tts_base_url or "").rstrip("/")
        self.api_key = api_key if api_key is not None else settings.custom_tts_api_key
        self.model = model or settings.custom_tts_model
        self.output_format = (output_format or settings.custom_tts_format or "wav").lower()
        self.timeout = timeout
        self._voices = parse_voice_spec(
            voices if voices is not None else settings.custom_tts_voices
        )

        if not self.base_url:
            raise MediaProviderConfigError(
                "The custom TTS provider needs CUSTOM_TTS_BASE_URL — the address "
                "of an OpenAI-compatible /audio/speech server (for example a "
                "local openedai-speech or Kokoro-FastAPI instance)."
            )
        if not self._voices:
            raise MediaProviderConfigError(
                "The custom TTS provider needs CUSTOM_TTS_VOICES, e.g. "
                "\"alloy:female:en-US,echo:male:en-US\". This API has no voice "
                "catalogue route, so the voices have to be named."
            )
        if self.output_format not in _FORMATS:
            raise MediaProviderConfigError(
                f"CUSTOM_TTS_FORMAT={self.output_format!r} is not one of "
                f"{', '.join(_FORMATS)}."
            )

    async def list_voices(self) -> list[Voice]:
        from app.services.video.providers.edge_tts_provider import language_label

        return [
            Voice(
                id=voice_id,
                provider=self.name,
                label=voice_id.replace("_", " ").replace("-", " ").title(),
                language=locale,
                language_label=language_label(locale),
                gender=gender,
                # `/audio/speech` has a `speed` parameter and nothing for pitch
                # or volume. Reporting False here is what makes the UI disable
                # those two sliders instead of offering controls that do
                # nothing — see how Voice Studio reads `supports_prosody`.
                supports_prosody=False,
                styles=(),
            )
            for voice_id, gender, locale in self._voices
        ]

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        known = {voice_id for voice_id, _, _ in self._voices}
        if request.voice_id not in known:
            raise UnsupportedVoiceError(
                f"{request.voice_id!r} is not one of the configured custom voices."
            )

        content_type, suffix = _FORMATS[self.output_format]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "input": request.text,
            "voice": request.voice_id,
            "response_format": self.output_format,
            # The one prosody control this API defines. Clamped to the range the
            # spec allows; pitch and volume have no equivalent and are dropped
            # rather than approximated — a silently ignored slider is worse than
            # a disabled one.
            "speed": max(0.25, min(4.0, float(request.rate))),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/audio/speech", json=payload, headers=headers
                )
        except httpx.RequestError as exc:
            raise MediaProviderError(
                f"Could not reach the custom voice server at {self.base_url}: {exc}"
            ) from exc

        if response.status_code >= 400:
            detail = response.text[:300].strip()
            raise MediaProviderError(
                f"The custom voice server returned {response.status_code}"
                + (f": {detail}" if detail else ".")
            )

        audio = response.content
        if not audio:
            raise MediaProviderError("The custom voice server returned no audio.")

        # Measured, never estimated — the timeline places this clip by its real
        # length, and words-per-minute arithmetic would be wrong by seconds.
        try:
            duration = probe_bytes(audio, suffix=suffix).duration_seconds
        except FFmpegError:
            duration = 0.0
            logger.warning("Could not measure audio from the custom voice server")

        return SpeechResult(
            audio=audio,
            content_type=response.headers.get("content-type", content_type).split(";")[0],
            duration_seconds=duration,
            voice_id=request.voice_id,
            provider=self.name,
            # This API emits no word timings. Empty is the honest answer; the
            # subtitle path falls back to segment timing rather than inventing
            # per-word positions.
            word_marks=[],
        )
