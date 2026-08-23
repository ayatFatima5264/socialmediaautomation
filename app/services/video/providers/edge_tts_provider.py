"""Edge TTS — the default voice provider.

Microsoft's Edge "Read Aloud" voices, reached through the `edge-tts` package.
Chosen as the default for three reasons, in order of importance:

  1. **It speaks Urdu.** The brief requires English, Urdu and Roman Urdu.
     `ur-PK-AsadNeural` and `ur-PK-UzmaNeural` (plus the two `ur-IN` voices)
     cover it, and Roman Urdu is served by sending Latin-script Urdu to those
     same voices. Groq's TTS models are English and Arabic only; most other free
     tiers are English only.
  2. **No API key and no quota**, so Video Studio works on a fresh clone and on
     a Render Free deploy with nothing configured.
  3. **322 neural voices across ~140 locales**, which is a real catalogue rather
     than a token gesture.

The honest caveat: this is an undocumented endpoint of a consumer product, not a
contracted API. It can change or rate-limit without notice. That is precisely
why it sits behind `TTSProvider` — replacing it with a paid, contracted provider
is a class and a factory line, and nothing above the factory changes.

Prosody is expressed the way this provider wants it: percentage strings for rate
and volume, and a hertz offset for pitch. The multiplier-based `SpeechRequest`
is converted here, once, so the API and the UI never learn this spelling.
"""
from __future__ import annotations

import asyncio
import logging

from app.services.video.ffmpeg import FFmpegError, probe_bytes
from app.services.video.providers.base import (
    MediaProviderError,
    SpeechRequest,
    SpeechResult,
    TTSProvider,
    UnsupportedVoiceError,
    Voice,
)

logger = logging.getLogger(__name__)

# Locale code -> the name shown in the language dropdown. Only the ones the
# brief names are spelled out; everything else falls back to the raw code plus
# the region, which is still readable ("de-DE").
_LANGUAGE_LABELS = {
    "en-US": "English (US)",
    "en-GB": "English (UK)",
    "en-AU": "English (Australia)",
    "en-IN": "English (India)",
    "ur-PK": "Urdu (Pakistan)",
    "ur-IN": "Urdu (India)",
    "hi-IN": "Hindi (India)",
    "ar-SA": "Arabic (Saudi Arabia)",
    "es-ES": "Spanish (Spain)",
    "fr-FR": "French (France)",
}


def language_label(locale: str) -> str:
    return _LANGUAGE_LABELS.get(locale, locale)


def _pct(multiplier: float) -> str:
    """A 1.0-centred multiplier as the signed percentage edge-tts expects."""
    delta = round((multiplier - 1.0) * 100)
    return f"{delta:+d}%"


def _hz(multiplier: float) -> str:
    """Pitch as a hertz offset.

    edge-tts takes `+50Hz`, not a ratio. A neural voice sits around 200 Hz, so
    mapping the 0.5–1.5 slider onto ±100 Hz gives a usable range without the
    chipmunk territory a wider one reaches.
    """
    return f"{round((multiplier - 1.0) * 200):+d}Hz"


class EdgeTTSProvider(TTSProvider):
    name = "edge"

    def __init__(self) -> None:
        self._voices: list[Voice] | None = None
        # The catalogue is fetched once per process. Concurrent first requests
        # would otherwise each make the same network call.
        self._lock = asyncio.Lock()

    async def list_voices(self) -> list[Voice]:
        if self._voices is not None:
            return self._voices

        async with self._lock:
            if self._voices is not None:
                return self._voices

            try:
                import edge_tts

                raw = await edge_tts.list_voices()
            except Exception as exc:
                raise MediaProviderError(
                    f"Could not load the Edge voice catalogue: {exc}"
                ) from exc

            voices: list[Voice] = []
            for item in raw:
                locale = item.get("Locale") or ""
                short = item.get("ShortName") or ""
                if not short:
                    continue
                tags = item.get("VoiceTag") or {}
                voices.append(
                    Voice(
                        id=short,
                        provider=self.name,
                        # "en-US-AriaNeural" -> "Aria". The locale is already a
                        # separate field; repeating it in the label makes every
                        # dropdown entry start with the same eight characters.
                        label=short.split("-")[-1].removesuffix("Neural")
                        or item.get("FriendlyName", short),
                        language=locale,
                        language_label=language_label(locale),
                        gender=(item.get("Gender") or "").lower() or "neutral",
                        supports_prosody=True,
                        styles=tuple(tags.get("VoicePersonalities") or ()),
                    )
                )

            voices.sort(key=lambda v: (v.language, v.label))
            self._voices = voices
            logger.info("Edge TTS catalogue loaded: %d voices", len(voices))
            return voices

    @staticmethod
    def _boundary_kwargs(edge_tts_module) -> dict:
        """`{"boundary": "WordBoundary"}` when this wheel accepts it, else {}.

        Checked by signature rather than by version string: a fork or a
        backport would report a version this code has never heard of, and the
        question being asked is only ever "does this accept the argument".
        """
        import inspect

        try:
            parameters = inspect.signature(
                edge_tts_module.Communicate.__init__
            ).parameters
        except (TypeError, ValueError):  # pragma: no cover - exotic build
            return {}
        return {"boundary": "WordBoundary"} if "boundary" in parameters else {}

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - packaging problem
            raise MediaProviderError("edge-tts is not installed.") from exc

        # `boundary="WordBoundary"` is not the default — edge-tts 7.x asks for
        # SentenceBoundary unless told otherwise, and a request that does not
        # ask for word timings simply never receives any. Without this the
        # word-mark list comes back empty on every synthesis, silently, and
        # karaoke subtitles would have nothing to work from.
        #
        # Passed through `_communicate_kwargs` because the parameter did not
        # exist before edge-tts 6.2: an older wheel raises TypeError on it, and
        # word timings are not worth failing a synthesis over.
        communicate = edge_tts.Communicate(
            request.text,
            request.voice_id,
            rate=_pct(request.rate),
            pitch=_hz(request.pitch),
            volume=_pct(request.volume),
            **self._boundary_kwargs(edge_tts),
        )

        audio = bytearray()
        marks: list[dict] = []
        try:
            async for chunk in communicate.stream():
                kind = chunk.get("type")
                if kind == "audio":
                    audio.extend(chunk["data"])
                elif kind in ("WordBoundary", "SentenceBoundary"):
                    # edge-tts reports these in 100-nanosecond ticks.
                    #
                    # Sentence boundaries are kept too, as a fallback: they are
                    # what an older wheel (or a voice that emits nothing finer)
                    # returns, and a cue timed to a sentence is far better than
                    # a subtitle track with no timing at all.
                    marks.append(
                        {
                            "start": chunk["offset"] / 10_000_000,
                            "end": (chunk["offset"] + chunk["duration"]) / 10_000_000,
                            "word": chunk["text"],
                            "kind": "word" if kind == "WordBoundary" else "sentence",
                        }
                    )
        except Exception as exc:
            message = str(exc)
            # The service answers an unknown voice with a protocol-level error
            # rather than a named one, so this is where it becomes a sentence a
            # user can act on.
            if "No audio was received" in message or "Invalid voice" in message:
                raise UnsupportedVoiceError(
                    f"{request.voice_id!r} is not a voice this provider can speak."
                ) from exc
            raise MediaProviderError(f"Voice generation failed: {message}") from exc

        if not audio:
            raise MediaProviderError(
                "The voice service returned no audio. The text may be empty or "
                "contain only unsupported characters."
            )

        data = bytes(audio)

        # Measured, never estimated. The timeline places this clip by its real
        # length, and words-per-minute arithmetic would be wrong by seconds.
        try:
            duration = probe_bytes(data, suffix=".mp3").duration_seconds
        except FFmpegError:
            # A duration we cannot read is not a reason to lose the audio the
            # user just waited for. Word marks give a usable lower bound.
            duration = max((m["end"] for m in marks), default=0.0)
            logger.warning("Could not measure synthesized audio; using word marks")

        return SpeechResult(
            audio=data,
            content_type="audio/mpeg",
            duration_seconds=duration,
            voice_id=request.voice_id,
            provider=self.name,
            word_marks=marks,
        )
