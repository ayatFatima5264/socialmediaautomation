import base64
import re

import httpx

from app.services.video.providers.base import (
    MediaProviderConfigError,
    MediaProviderError,
    TTSProvider,
    Voice,
    SpeechRequest,
    SpeechResult,
    pitch_semitones,
    volume_gain_db,
)

# Google voice IDs are "xx-XX-Engine-Voice": en-US-Standard-A, cmn-CN-Wavenet-B,
# yue-HK-Standard-C. The locale is the leading BCP-47 tag. It is matched from
# the front rather than spliced out of the hyphenated name, because those names
# are a de facto shape, not a contract: languages are two *or three* letters
# (cmn-CN, yue-HK), and a script tag (sr-Latn-…) is not always in the same
# segment — so indexing the split is a guess at the format that a regex on the
# tag's grammar is not.
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?")


class GoogleTTSProvider(TTSProvider):
    name = "google"

    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def list_voices(self) -> list[Voice]:
        if not self.api_key:
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/v1/voices",
                headers={"X-Goog-Api-Key": self.api_key},
            )

        if response.status_code >= 400:
            raise MediaProviderError(
                f"Google TTS voices error {response.status_code}: {response.text}"
            )

        data = response.json()
        voices = []

        for item in data.get("voices", []):
            for language in item.get("languageCodes", []):
                if "-Standard-" not in item.get("name", ""):
                    continue

                voices.append(
                    Voice(
                        id=item["name"],
                        provider=self.name,
                        label=item["name"],
                        language=language,
                        language_label=language,
                        gender=str(item.get("ssmlGender", "UNKNOWN")).lower(),
                        supports_prosody=True,
                    )
                )

        return voices

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        if not self.api_key:
            raise MediaProviderConfigError(
                "GOOGLE_TTS_API_KEY is not configured."
            )

        match = _LOCALE_RE.match(request.voice_id)
        if not match:
            raise MediaProviderError(
                f"Invalid Google voice ID: {request.voice_id}"
            )
        language_code = match.group(0)

        payload = {
            "input": {
                "text": request.text,
            },
            "voice": {
                "languageCode": language_code,
                "name": request.voice_id,
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": request.rate,
                # Google speaks in semitones relative to the voice; the shared
                # multiplier→semitones mapping keeps this provider's pitch arm
                # consistent with any other that uses the same conversion.
                "pitch": round(pitch_semitones(request.pitch), 2),
                # Same convention for gain: 1.0 is unity (0 dB), 0.5 is −6 dB.
                "volumeGainDb": round(volume_gain_db(request.volume), 2),
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/v1/text:synthesize",
                headers={
                    "X-Goog-Api-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if response.status_code >= 400:
            raise MediaProviderError(
                f"Google TTS error {response.status_code}: {response.text}"
            )

        data = response.json()
        audio = base64.b64decode(data["audioContent"])

        return SpeechResult(
            audio=audio,
            content_type="audio/mpeg",
            duration_seconds=0,
            voice_id=request.voice_id,
            provider=self.name,
        )