"""Whisper transcription over any OpenAI-compatible audio endpoint.

Subtitle Studio's job is timed text, so the provider requirement is narrow and
specific: it must return timestamps, not just a transcript. Whisper's
`verbose_json` response format does, at both segment and word granularity, and
the same request shape is served by Groq, OpenAI and every local
OpenAI-compatible server — so one class covers all of them and the difference is
a base URL.

Groq is the configured default because the key is already present for text
generation, `whisper-large-v3-turbo` is fast and free-tier, and it returns real
word timings — which is what makes the karaoke and word-highlight subtitle
presets honest rather than interpolated.
"""
from __future__ import annotations

import logging

import httpx

from app.services.video.providers.base import (
    MediaProviderConfigError,
    MediaProviderError,
    Transcript,
    TranscriptionProvider,
    TranscriptSegment,
    TranscriptWord,
)

logger = logging.getLogger(__name__)


class WhisperProvider(TranscriptionProvider):
    """One provider class, pointed at whichever host is configured."""

    def __init__(
        self,
        *,
        name: str,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout: float,
    ) -> None:
        if not api_key:
            raise MediaProviderConfigError(
                f"The {name} transcription provider needs an API key."
            )
        self.name = name
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
        # `/translations` transcribes *and* renders into English in one pass —
        # which is what "translate to English" in the Subtitle Studio means.
        # Any other target language is a separate text-translation step, not
        # something Whisper's audio endpoint can do.
        endpoint = "translations" if translate_to_english else "transcriptions"

        # A dict, not a list of pairs. httpx only treats `data` as form fields
        # when it is a mapping — given a list it decides you meant raw request
        # content, builds a *sync* byte stream, and the async client then dies
        # with "Attempted to send an sync request with an AsyncClient
        # instance". A list value is how a repeated field is expressed, which
        # is what `timestamp_granularities[]` needs.
        data: dict[str, object] = {
            "model": self.model,
            "response_format": "verbose_json",
        }
        if word_timestamps and not translate_to_english:
            # Word timings are unavailable on /translations.
            data["timestamp_granularities[]"] = ["segment", "word"]
        if language and not translate_to_english:
            # Whisper wants the bare ISO-639-1 code, not a full locale.
            data["language"] = language.split("-")[0]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/audio/{endpoint}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (filename, audio, content_type)},
                    data=data,
                )
        except httpx.HTTPError as exc:
            raise MediaProviderError(f"Transcription request failed: {exc}") from exc

        if response.status_code == 413:
            raise MediaProviderError(
                "That audio is larger than the transcription service accepts. "
                "Trim it, or upload the audio track rather than the video."
            )
        if response.status_code != 200:
            raise MediaProviderError(
                f"Transcription returned {response.status_code}: "
                f"{response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise MediaProviderError(
                "The transcription service returned a response that was not JSON."
            ) from exc

        segments = [
            TranscriptSegment(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", 0.0)),
                text=(item.get("text") or "").strip(),
            )
            for item in (payload.get("segments") or [])
            if (item.get("text") or "").strip()
        ]

        words = [
            TranscriptWord(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", 0.0)),
                word=(item.get("word") or "").strip(),
            )
            for item in (payload.get("words") or [])
            if (item.get("word") or "").strip()
        ]

        text = (payload.get("text") or "").strip()

        if not text and not segments:
            raise MediaProviderError(
                "No speech was found in that file. Check that it has an audio "
                "track and that someone is speaking."
            )

        duration = float(payload.get("duration") or 0.0)
        if not duration and segments:
            duration = segments[-1].end

        return Transcript(
            text=text,
            # `language` comes back as a name ("English"), not a code.
            language=(payload.get("language") or language or "").strip(),
            duration_seconds=duration,
            segments=segments,
            words=words,
            provider=self.name,
            model=self.model,
        )
