import httpx

from app.services.video.providers.base import (
    TTSProvider,
    Voice,
    SpeechRequest,
    SpeechResult,
)
from app.services.video.providers.base import (
    MediaProviderConfigError,
    MediaProviderError,
)


class ElevenLabsTTSProvider(TTSProvider):
    name = "elevenlabs"

    def __init__(self, api_key, model, base_url):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def list_voices(self) -> list[Voice]:
        if not self.api_key:
            return []

        headers = {"xi-api-key": self.api_key}

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/v1/voices",
                headers=headers,
            )

        if response.status_code >= 400:
            raise MediaProviderError(
                f"ElevenLabs voices error {response.status_code}: {response.text}"
            )

        data = response.json()
        voices = []

        for item in data.get("voices", []):
            languages = item.get("verified_languages") or []

            if languages:
                language = languages[0].get("language_code", "en")
            else:
                language = "en"

            gender = (item.get("labels") or {}).get("gender", "unknown")

            voices.append(
                Voice(
                    id=item["voice_id"],
                    provider=self.name,
                    label=item.get("name", item["voice_id"]),
                    language=language,
                    language_label=language,
                    gender=gender,
                    supports_prosody=True,
                )
            )

        return voices

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        if not self.api_key:
            raise MediaProviderConfigError(
                "ELEVENLABS_API_KEY is not configured."
            )

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": request.text,
            "model_id": self.model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
                # ElevenLabs clamps speed to [0.7, 1.2]. Other providers accept
                # the full [0.5, 2.0] range from the UI. We clamp here so the
                # request never returns a 400 from the API; callers should be
                # aware that values outside this range have no effect on this
                # provider.
                "speed": max(0.7, min(request.rate, 1.2)),
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/v1/text-to-speech/{request.voice_id}",
                params={"output_format": "mp3_44100_128"},
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise MediaProviderError(
                f"ElevenLabs TTS error {response.status_code}: {response.text}"
            )

        audio = response.content

        return SpeechResult(
            audio=audio,
            content_type="audio/mpeg",
            duration_seconds=0,
            voice_id=request.voice_id,
            provider=self.name,
        )