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


class CartesiaTTSProvider(TTSProvider):
    name = "cartesia"

    def __init__(self, api_key, model, base_url, version):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.version = version

    async def list_voices(self) -> list[Voice]:
        if not self.api_key:
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Cartesia-Version": self.version,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/voices",
                headers=headers,
            )

        if response.status_code >= 400:
            raise MediaProviderError(
                f"Cartesia voices error {response.status_code}: {response.text}"
            )

        data = response.json()
        voices = []

        for item in data.get("voices", []):
            language = item.get("language", "en")

            voices.append(
                Voice(
                    id=item["id"],
                    provider=self.name,
                    label=item.get("name", item["id"]),
                    language=language,
                    language_label=language,
                    gender=item.get("gender", "unknown"),
                    supports_prosody=True,
                )
            )

        return voices

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        if not self.api_key:
            raise MediaProviderConfigError(
                "CARTESIA_API_KEY is not configured."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Cartesia-Version": self.version,
            "Content-Type": "application/json",
        }

        payload = {
            "model_id": self.model,
            "transcript": request.text,
            "voice": {
                "mode": "id",
                "id": request.voice_id,
            },
            "output_format": {
                "container": "mp3",
                "bit_rate": 128000,
                "sample_rate": 44100,
            },
            "generation_config": {
                "speed": request.rate,
                "volume": request.volume,
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/tts/bytes",
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise MediaProviderError(
                f"Cartesia TTS error {response.status_code}: {response.text}"
            )

        return SpeechResult(
            audio=response.content,
            content_type="audio/mpeg",
            duration_seconds=0,
            voice_id=request.voice_id,
            provider=self.name,
        )