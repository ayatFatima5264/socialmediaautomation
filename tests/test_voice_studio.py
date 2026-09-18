"""Voice Studio: the provider abstraction, the service, and the HTTP layer.

**Nothing here reaches a TTS service.** Every test drives a fake provider
registered through the same factory the real ones use — which is itself the
first assertion worth making: if a fake can be substituted by configuration
alone, the abstraction is real rather than decorative.

What is covered, and why each matters:

  * **Text input** — empty, whitespace, over the character ceiling, and the
    `[pause]` marker. The ceiling is the one that bites: without it a user
    waits two minutes to be told no.
  * **Voice selection** — a request routes to the provider that owns the voice,
    even when it is not the configured default. That is the whole point of a
    merged catalogue.
  * **Generation** — the audio is stored in object storage and the row records
    where; the duration is the provider's measurement, not an estimate.
  * **Preview** — stores nothing. A preview the user rejects must not leave a
    file in their library or bytes in a bucket.
  * **Download** — MP3 and WAV both come back, which means the conversion is
    real; a take made as MP3 can still be downloaded as WAV.
  * **Add to project** — and the two directions it must refuse across accounts.
  * **Error handling** — a provider failure, a missing key, and a quota each
    map to a different status code, because "try shorter text", "come back
    later" and "tell your admin" are three different messages.
"""
from __future__ import annotations

import asyncio
import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.database import Base, get_db
from app.main import app
from app.models.storage_object import StorageObject
from app.models.video_asset import VideoAsset
from app.services.storage import reset_storage_cache
from app.services.video import voice as voice_service
from app.services.video.providers import (
    MediaProviderConfigError,
    MediaProviderError,
    SpeechRequest,
    SpeechResult,
    TTSProvider,
    UnsupportedVoiceError,
    Voice,
    reset_provider_cache,
)

PASSWORD = "correct-horse-battery"

# A 44-byte silent WAV. ffmpeg can decode it, which is what the download tests
# need — a fake provider returning `b"not audio"` could not be converted.
WAV_BYTES = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)


# ---------------------------------------------------------------------------
# A provider that is entirely ours
# ---------------------------------------------------------------------------


class FakeTTS(TTSProvider):
    """Records what it was asked for, returns real (silent) audio.

    Deliberately implements only the two abstract methods. If the contract ever
    grows a third, this fails to instantiate — which is the warning that every
    third-party provider is about to break too.
    """

    name = "fake"

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.fail_with = fail_with
        self.calls: list[SpeechRequest] = []

    async def list_voices(self) -> list[Voice]:
        return [
            Voice(
                id="fake-en-Ada",
                provider=self.name,
                label="Ada",
                language="en-US",
                language_label="English (US)",
                gender="female",
                supports_prosody=True,
                styles=("cheerful",),
            ),
            Voice(
                id="fake-ur-Asad",
                provider=self.name,
                label="Asad",
                language="ur-PK",
                language_label="Urdu (Pakistan)",
                gender="male",
                supports_prosody=True,
            ),
            Voice(
                id="fake-flat-Robot",
                provider=self.name,
                label="Robot",
                language="en-US",
                language_label="English (US)",
                gender="neutral",
                # The case the UI has to disable sliders for.
                supports_prosody=False,
            ),
        ]

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        self.calls.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        if request.voice_id not in {v.id for v in await self.list_voices()}:
            raise UnsupportedVoiceError(f"{request.voice_id!r} is not a voice here.")

        return SpeechResult(
            audio=WAV_BYTES,
            content_type="audio/wav",
            duration_seconds=4.25,
            voice_id=request.voice_id,
            provider=self.name,
            word_marks=[{"start": 0.0, "end": 0.4, "word": "Hello", "kind": "word"}],
        )


class ScriptedTTS(TTSProvider):
    """A catalogue and a failure plan, for fallback-chain tests.

    `fail` is a queue: each `synthesize` pops the next exception, so a test can
    script a primary that goes down once and then stay out of the way.
    """

    def __init__(self, *, name, voices, fail=()):
        self.name = name
        self.voices_provided = list(voices)
        self.fails = list(fail)
        self.calls: list[SpeechRequest] = []

    async def list_voices(self) -> list[Voice]:
        return self.voices_provided

    async def synthesize(self, request: SpeechRequest) -> SpeechResult:
        self.calls.append(request)
        if self.fails:
            raise self.fails.pop(0)
        return SpeechResult(
            audio=WAV_BYTES,
            content_type="audio/wav",
            duration_seconds=2.0,
            voice_id=request.voice_id,
            provider=self.name,
            word_marks=[],
        )


def install_providers(monkeypatch, providers: dict[str, TTSProvider]) -> None:
    """Make the voice service resolve provider names from `providers`.

    The same seam `provider` above uses, but keyed by name so a test can hold
    several providers and a fallback chain behind `settings.tts_fallback_providers`.
    """
    def provider_for(name: str | None) -> TTSProvider:
        if name is None:
            name = "fake"
        return providers[name]

    monkeypatch.setattr("app.services.video.providers.factory._build_tts", provider_for)
    monkeypatch.setattr("app.services.video.voice.get_tts_provider", provider_for)
    monkeypatch.setattr(
        "app.services.video.voice.get_tts_providers", lambda: list(providers.values())
    )
    monkeypatch.setattr(
        "app.services.video.voice.metering.check_allowance", lambda *a, **k: None
    )
    reset_provider_cache()


def a_voice(*, id, provider, language="en-US", gender="female") -> Voice:
    """One catalogue entry, with the fields the studio reads already filled."""
    return Voice(
        id=id,
        provider=provider,
        label=id,
        language=language,
        language_label=language,
        gender=gender,
        supports_prosody=True,
    )


@pytest.fixture()
def provider(monkeypatch):
    """Install the fake as the one and only TTS provider.

    Patched at the factory, which is the seam the whole design rests on: if
    this works, adding a real provider is a class and a line, exactly as the
    module docstrings claim.
    """
    fake = FakeTTS()

    def only_fake(name: str | None = None):
        return fake

    monkeypatch.setattr("app.services.video.providers.factory._build_tts", only_fake)
    monkeypatch.setattr("app.services.video.voice.get_tts_provider", only_fake)
    monkeypatch.setattr("app.services.video.voice.get_tts_providers", lambda: [fake])
    monkeypatch.setattr("app.routes.video_voice.get_tts_providers", lambda: [fake])
    reset_provider_cache()
    yield fake
    reset_provider_cache()


@pytest.fixture()
def client(tmp_path, monkeypatch, provider):
    url = f"sqlite:///{(tmp_path / 'voice.db').as_posix()}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr("app.services.storage.database.SessionLocal", factory)
    monkeypatch.setattr("app.config.settings.storage_backend", "database")
    reset_storage_cache()

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)

    app.dependency_overrides.clear()
    reset_storage_cache()
    engine.dispose()


def auth(client, email="voice@example.com") -> dict:
    client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Voice"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def generate(client, headers, **body):
    payload = {"text": "Hello there.", "voice_id": "fake-en-Ada", **body}
    return client.post("/api/video/voice/generate", headers=headers, json=payload)


# ===========================================================================
# The abstraction itself
# ===========================================================================


def test_a_provider_needs_only_the_two_contract_methods(provider):
    """FakeTTS implements list_voices and synthesize and nothing else. That it
    instantiates at all is the assertion — a contract that grew a third
    abstract method would break every third-party provider the same way."""
    assert isinstance(provider, TTSProvider)
    assert provider.name == "fake"


def test_the_factory_advertises_a_local_open_source_option():
    """"custom" is the OpenAI-compatible `/audio/speech` provider, which is
    what the self-hostable engines expose — so running with no external service
    is configuration, not a code change."""
    from app.services.video.providers.factory import available_tts_providers

    assert "custom" in available_tts_providers


def test_custom_provider_refuses_to_start_unconfigured(monkeypatch):
    from app.services.video.providers.openai_speech import OpenAISpeechProvider

    monkeypatch.setattr("app.config.settings.custom_tts_base_url", None)
    monkeypatch.setattr("app.config.settings.custom_tts_voices", None)

    with pytest.raises(MediaProviderConfigError):
        OpenAISpeechProvider()


def test_custom_provider_parses_its_voice_spec():
    from app.services.video.providers.openai_speech import parse_voice_spec

    parsed = parse_voice_spec("alloy:female:en-US, piper_asad:male:ur-PK , echo")

    assert parsed == [
        ("alloy", "female", "en-US"),
        ("piper_asad", "male", "ur-PK"),
        # Gender and locale are optional.
        ("echo", "neutral", "en-US"),
    ]


def test_a_malformed_voice_entry_does_not_empty_the_list():
    """One typo in an environment variable must not remove every voice."""
    from app.services.video.providers.openai_speech import parse_voice_spec

    assert parse_voice_spec(",,alloy:female:en-US,,") == [("alloy", "female", "en-US")]


# ===========================================================================
# Text input
# ===========================================================================


@pytest.mark.parametrize("text", ["", "   ", "\n\n\t "])
def test_empty_text_is_refused_before_anything_is_synthesized(provider, text):
    with pytest.raises(voice_service.VoiceError):
        voice_service.clean_text(text)
    assert provider.calls == []


def test_text_over_the_ceiling_is_refused_with_the_number(provider, monkeypatch):
    """Refused up front, not after a two-minute wait."""
    monkeypatch.setattr("app.config.settings.tts_max_characters", 50)

    with pytest.raises(voice_service.VoiceError, match="split a longer script"):
        voice_service.clean_text("x" * 51)
    assert provider.calls == []


def test_the_pause_marker_becomes_a_real_break():
    """`[pause]` is the only markup accepted — SSML from a user would be an
    injection surface and providers disagree on it."""
    cleaned = voice_service.clean_text("First thing. [pause] Second thing.")

    assert "[pause]" not in cleaned.lower()
    assert "…" in cleaned


def test_runs_of_blank_lines_are_collapsed():
    assert "\n\n\n" not in voice_service.clean_text("One.\n\n\n\n\nTwo.")


def test_segments_split_on_blank_lines_with_real_offsets():
    text = "Opening line.\n\nSecond section.\n\n\nThird section."

    segments = voice_service.split_segments(text)

    assert [s["text"] for s in segments] == [
        "Opening line.", "Second section.", "Third section.",
    ]
    assert [s["index"] for s in segments] == [0, 1, 2]
    # The offsets must address the original text, so the UI can highlight the
    # part of the textarea a take came from.
    for segment in segments:
        assert text[segment["start"]:segment["end"]] == segment["text"]


def test_a_script_with_no_blank_lines_is_one_segment():
    """Not a degenerate case: an unbroken paragraph has no seam to record
    separately, and splitting mid-sentence would produce takes that do not
    join cleanly."""
    segments = voice_service.split_segments("One sentence. And another one.")
    assert len(segments) == 1


# ===========================================================================
# Styles
# ===========================================================================


def test_a_style_composes_with_the_sliders_rather_than_replacing_them():
    rate, pitch, key = voice_service.apply_style("energetic", 1.0, 1.0)

    assert key == "energetic"
    assert rate > 1.0 and pitch > 1.0


def test_a_style_cannot_push_prosody_out_of_range():
    """"Energetic" plus a rate of 2.0 is still 2.0 — no combination may produce
    an unusable file."""
    rate, _, _ = voice_service.apply_style("energetic", 2.0, 1.0)
    assert rate == 2.0

    _, pitch, _ = voice_service.apply_style("calm", 1.0, 0.5)
    assert pitch >= 0.5


def test_an_unknown_style_falls_back_to_default():
    rate, pitch, key = voice_service.apply_style("interpretive-dance", 1.0, 1.0)
    assert (rate, pitch, key) == (1.0, 1.0, "default")


# ===========================================================================
# Voice selection
# ===========================================================================


def test_catalogue_lists_voices_languages_and_styles(client):
    headers = auth(client)

    body = client.get("/api/video/voice/catalogue", headers=headers).json()

    assert {v["id"] for v in body["voices"]} == {
        "fake-en-Ada", "fake-ur-Asad", "fake-flat-Robot",
    }
    # Languages are derived from the voices, so a language with no voices
    # behind it can never appear as a dead end in the dropdown.
    assert {l["code"] for l in body["languages"]} >= {"en-US", "ur-PK"}
    assert {s["key"] for s in body["styles"]} >= {"default", "narration", "energetic"}
    assert body["max_characters"] > 0


def test_roman_urdu_is_offered_and_routed_to_the_urdu_voices(client):
    """It is Urdu in Latin script, not a locale any engine ships. Presenting it
    honestly costs one mapping."""
    headers = auth(client)

    languages = client.get("/api/video/voice/catalogue", headers=headers).json()["languages"]
    roman = next((l for l in languages if l["code"] == voice_service.ROMAN_URDU), None)

    assert roman is not None
    assert roman["note"]
    assert voice_service.resolve_language(voice_service.ROMAN_URDU) == "ur-PK"


def test_a_voice_carries_whether_it_supports_prosody(client):
    """The UI disables the pitch and volume sliders off this flag rather than
    offering controls that do nothing."""
    headers = auth(client)

    voices = {v["id"]: v for v in client.get("/api/video/voice/catalogue", headers=headers).json()["voices"]}

    assert voices["fake-en-Ada"]["supports_prosody"] is True
    assert voices["fake-flat-Robot"]["supports_prosody"] is False


def test_an_unknown_voice_is_refused(client, provider):
    headers = auth(client)

    response = generate(client, headers, voice_id="not-a-voice")

    assert response.status_code == 422


# ===========================================================================
# Generation and storage
# ===========================================================================


def test_generate_stores_the_audio_and_returns_a_take(client, provider):
    headers = auth(client)

    response = generate(client, headers, text="Welcome to the studio.")

    assert response.status_code == 201
    take = response.json()
    assert take["provider"] == "fake"
    assert take["voice_id"] == "fake-en-Ada"
    # The provider's measurement, not an estimate from the text length.
    assert take["duration_seconds"] == 4.25
    assert take["size_bytes"] == len(WAV_BYTES)
    assert "/api/storage/o/" in take["url"]
    # No project: Voice Studio works without one, and that is structural.
    assert take["project_id"] is None
    # The text and settings travel with the take so a regeneration can start
    # from what made it.
    assert take["text"] == "Welcome to the studio."
    assert take["style"] == "default"


def test_the_audio_goes_to_object_storage_not_a_project_column(client, provider):
    """The bytes live behind the storage abstraction and the row keeps only a
    key. That is the rule the whole storage layer exists to enforce."""
    headers = auth(client)
    generate(client, headers)

    db = next(app.dependency_overrides[get_db]())
    asset = db.query(VideoAsset).one()
    stored = db.query(StorageObject).one()
    db.close()

    assert asset.kind == "voice"
    assert asset.storage_key.endswith(".wav")
    assert f"/voice/" in asset.storage_key
    # The row points at the object; it does not contain it.
    assert not hasattr(asset, "data")
    assert stored.key == asset.storage_key
    assert stored.data == WAV_BYTES


def test_generation_meters_the_seconds_it_produced(client, provider):
    from app.models.usage_event import UsageEvent

    headers = auth(client)
    generate(client, headers)

    db = next(app.dependency_overrides[get_db]())
    events = db.query(UsageEvent).filter_by(metric="voice_seconds").all()
    db.close()

    assert [e.quantity for e in events] == [4.25]


def test_the_style_reaches_the_provider_as_composed_prosody(client, provider):
    headers = auth(client)

    generate(client, headers, style="energetic", rate=1.0)

    request = provider.calls[-1]
    assert request.rate > 1.0
    assert request.style == "energetic"


def test_the_default_style_is_not_sent_as_a_style(client, provider):
    """A provider should receive None rather than the word "default", which it
    would have to know to ignore."""
    headers = auth(client)

    generate(client, headers, style="default")

    assert provider.calls[-1].style is None


def test_a_take_can_record_which_section_it_covers(client, provider):
    headers = auth(client)

    take = generate(client, headers, text="Second block.", segment_index=1).json()

    assert take["segment_index"] == 1


def test_takes_are_listed_newest_first_and_scoped_to_the_owner(client, provider):
    mine = auth(client, "mine@example.com")
    theirs = auth(client, "theirs@example.com")

    generate(client, mine, text="First one.")
    generate(client, mine, text="Second one.")
    generate(client, theirs, text="Not yours.")

    listed = client.get("/api/video/voice/takes", headers=mine).json()

    assert [t["text"] for t in listed] == ["Second one.", "First one."]


# ===========================================================================
# Preview
# ===========================================================================


def test_preview_returns_audio_inline_and_stores_nothing(client, provider):
    """A preview the user rejects must not leave a file in their library or
    bytes in a bucket they pay for."""
    headers = auth(client)

    response = client.post(
        "/api/video/voice/preview",
        headers=headers,
        json={"text": "Just checking this voice.", "voice_id": "fake-en-Ada"},
    )

    assert response.status_code == 200
    body = response.json()
    assert base64.b64decode(body["audio_base64"]) == WAV_BYTES
    assert body["duration_seconds"] == 4.25

    db = next(app.dependency_overrides[get_db]())
    assets = db.query(VideoAsset).count()
    objects = db.query(StorageObject).count()
    db.close()

    assert (assets, objects) == (0, 0)


def test_preview_truncates_long_text_and_says_so(client, provider):
    headers = auth(client)

    body = client.post(
        "/api/video/voice/preview",
        headers=headers,
        json={"text": "word " * 400, "voice_id": "fake-en-Ada"},
    ).json()

    assert body["truncated"] is True
    assert body["characters"] <= 240
    assert len(provider.calls[-1].text) <= 240


def test_preview_reports_what_the_style_actually_did(client, provider):
    """The panel shows the effective numbers, so a style never looks like it
    had no effect."""
    headers = auth(client)

    body = client.post(
        "/api/video/voice/preview",
        headers=headers,
        json={"text": "Testing.", "voice_id": "fake-en-Ada", "style": "calm"},
    ).json()

    assert body["style"] == "calm"
    assert body["effective_rate"] < 1.0


def test_preview_needs_text(client, provider):
    headers = auth(client)

    response = client.post(
        "/api/video/voice/preview",
        headers=headers,
        json={"text": "   ", "voice_id": "fake-en-Ada"},
    )

    assert response.status_code == 422


# ===========================================================================
# Download
# ===========================================================================


def test_a_take_downloads_as_both_mp3_and_wav(client, provider):
    """The provider produced WAV. Offering only that would be the studio
    deciding what the user is allowed to have, so the MP3 is converted on
    demand — which means this test also proves the conversion is real."""
    headers = auth(client)
    take = generate(client, headers, text="Convert me.").json()

    wav = client.get(f"/api/video/voice/{take['id']}/download?format=wav", headers=headers)
    mp3 = client.get(f"/api/video/voice/{take['id']}/download?format=mp3", headers=headers)

    assert wav.status_code == 200
    assert wav.headers["content-type"] == "audio/wav"
    assert wav.content.startswith(b"RIFF")

    assert mp3.status_code == 200
    assert mp3.headers["content-type"] == "audio/mpeg"
    # A real MP3, not the WAV renamed: it must not still be a RIFF container.
    assert not mp3.content.startswith(b"RIFF")
    assert len(mp3.content) > 0


def test_a_download_is_named_after_the_take(client, provider):
    """"voiceover-Xk3p9.mp3" is not a name anyone can find in a folder."""
    headers = auth(client)
    take = generate(client, headers, title="Autumn menu promo").json()

    response = client.get(
        f"/api/video/voice/{take['id']}/download?format=wav", headers=headers
    )

    assert "Autumn menu promo" in response.headers["content-disposition"]


def test_an_unsupported_download_format_is_refused(client, provider):
    headers = auth(client)
    take = generate(client, headers).json()

    response = client.get(
        f"/api/video/voice/{take['id']}/download?format=flac", headers=headers
    )

    assert response.status_code == 422


# ===========================================================================
# Add to project
# ===========================================================================


def test_a_take_can_be_added_to_a_project_without_having_been_made_in_one(client, provider):
    headers = auth(client)
    take = generate(client, headers).json()
    assert take["project_id"] is None

    project = client.post("/api/video/projects", headers=headers, json={}).json()
    attached = client.post(
        f"/api/video/voice/{take['id']}/attach?project_id={project['id']}",
        headers=headers,
    )

    assert attached.status_code == 200
    assert attached.json()["project_id"] == project["id"]


def test_deleting_a_project_leaves_its_voice_over_in_the_library(client, provider):
    """A voice-over belongs to the user, not to the project."""
    headers = auth(client)
    take = generate(client, headers).json()
    project = client.post("/api/video/projects", headers=headers, json={}).json()
    client.post(
        f"/api/video/voice/{take['id']}/attach?project_id={project['id']}", headers=headers
    )

    client.delete(f"/api/video/projects/{project['id']}", headers=headers)

    remaining = client.get("/api/video/voice/takes", headers=headers).json()
    assert [t["id"] for t in remaining] == [take["id"]]
    assert remaining[0]["project_id"] is None


def test_a_take_cannot_be_added_to_another_accounts_project(client, provider):
    mine = auth(client, "a@example.com")
    theirs = auth(client, "b@example.com")

    take = generate(client, mine).json()
    their_project = client.post("/api/video/projects", headers=theirs, json={}).json()

    response = client.post(
        f"/api/video/voice/{take['id']}/attach?project_id={their_project['id']}",
        headers=mine,
    )

    assert response.status_code == 404


def test_another_accounts_take_cannot_be_attached_downloaded_or_deleted(client, provider):
    mine = auth(client, "one@example.com")
    theirs = auth(client, "two@example.com")

    their_take = generate(client, theirs).json()
    my_project = client.post("/api/video/projects", headers=mine, json={}).json()

    assert client.post(
        f"/api/video/voice/{their_take['id']}/attach?project_id={my_project['id']}",
        headers=mine,
    ).status_code == 404
    assert client.get(
        f"/api/video/voice/{their_take['id']}/download?format=mp3", headers=mine
    ).status_code == 404
    assert client.delete(
        f"/api/video/voice/{their_take['id']}", headers=mine
    ).status_code == 404


def test_deleting_a_take_removes_its_object_too(client, provider):
    headers = auth(client)
    take = generate(client, headers).json()

    assert client.delete(f"/api/video/voice/{take['id']}", headers=headers).status_code == 204

    db = next(app.dependency_overrides[get_db]())
    counts = (db.query(VideoAsset).count(), db.query(StorageObject).count())
    db.close()
    assert counts == (0, 0)


# ===========================================================================
# Error handling
# ===========================================================================


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/video/voice/catalogue"),
        ("get", "/api/video/voice/takes"),
        ("post", "/api/video/voice/preview"),
        ("post", "/api/video/voice/generate"),
        ("post", "/api/video/voice/segments"),
        ("get", "/api/video/voice/1/download"),
        ("delete", "/api/video/voice/1"),
    ],
)
def test_every_voice_route_requires_a_token(client, method, path):
    kwargs = {"json": {}} if method in ("post", "patch") else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_a_provider_failure_is_a_422_with_the_reason(client, provider):
    """Not a 500. The user needs to know whether to change something or wait."""
    provider.fail_with = MediaProviderError("The voice service is rate limiting.")
    headers = auth(client)

    response = generate(client, headers)

    assert response.status_code == 422
    assert "rate limiting" in response.json()["detail"]


def test_an_unconfigured_provider_is_a_503(client, provider):
    """The operator has to fix this, not the user — so it must not read as a
    problem with what they typed."""
    provider.fail_with = MediaProviderConfigError("GROQ_API_KEY is not set.")
    headers = auth(client)

    response = generate(client, headers)

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_an_exhausted_allowance_is_a_429(client, provider, monkeypatch):
    """Distinct from a failure: "come back next month" and "that did not work"
    are different messages."""
    from app.services.video import metering

    monkeypatch.setitem(
        metering.LIMITS,
        "voice_seconds",
        metering.Limit("voice_seconds", monthly=0.1, unit="seconds", enforced=True),
    )
    headers = auth(client)

    response = generate(client, headers, text="x" * 200)

    assert response.status_code == 429
    assert "allowance" in response.json()["detail"]


def test_a_failed_generation_stores_nothing(client, provider):
    """No half-written asset, and no bytes in the bucket nothing points at."""
    provider.fail_with = MediaProviderError("boom")
    headers = auth(client)

    generate(client, headers)

    db = next(app.dependency_overrides[get_db]())
    counts = (db.query(VideoAsset).count(), db.query(StorageObject).count())
    db.close()
    assert counts == (0, 0)


def test_the_catalogue_says_so_when_no_provider_is_available(client, monkeypatch):
    """An empty dropdown with no explanation is the worst version of this."""
    monkeypatch.setattr("app.services.video.voice.get_tts_providers", lambda: [])
    headers = auth(client)

    response = client.get("/api/video/voice/catalogue", headers=headers)

    assert response.status_code == 503
    assert "TTS_PROVIDER" in response.json()["detail"]


def test_one_unreachable_provider_does_not_empty_the_catalogue(monkeypatch, provider):
    """A provider that fails to answer is skipped, not fatal — otherwise one
    flaky catalogue removes every working voice from the dropdown."""
    import asyncio

    class Broken(TTSProvider):
        name = "broken"

        async def list_voices(self):
            raise MediaProviderError("upstream is down")

        async def synthesize(self, request):  # pragma: no cover - never called
            raise MediaProviderError("upstream is down")

    monkeypatch.setattr(
        "app.services.video.voice.get_tts_providers", lambda: [Broken(), provider]
    )

    voices = asyncio.run(voice_service.list_voices())

    assert {v.provider for v in voices} == {"fake"}


# ===========================================================================
# The fallback chain
# ===========================================================================


def test_a_fallback_uses_its_own_closest_voice_not_the_shared_voice_id(monkeypatch):
    """The collision case: the same voice id exists in two providers with
    nothing in common but the id.

    The user's voice belongs to the primary. When the primary fails at request
    time, the fallback has to speak in *its* closest voice to the one picked —
    sending the shared id to the fallback would hand the synthesis to a voice
    whose language and gender are not the ones the user chose.
    """
    primary = ScriptedTTS(
        name="primary",
        voices=[a_voice(id="shared", provider="primary")],
        fail=(MediaProviderError("primary is down"),),
    )
    fallback = ScriptedTTS(
        name="fallback",
        voices=[
            a_voice(id="shared", provider="fallback", language="ur-PK", gender="male"),
            a_voice(id="fallback-Lilac", provider="fallback"),
        ],
    )
    install_providers(monkeypatch, {"primary": primary, "fallback": fallback})
    monkeypatch.setattr("app.config.settings.tts_fallback_providers", ["fallback"])

    _, details = asyncio.run(voice_service.synthesize(
        None, user_id=1, text="Hello.", voice_id="shared", save=False,
    ))

    assert details["provider"] == "fallback"
    assert details["voice_id"] == "fallback-Lilac"
    # The id the fallback was actually asked to speak.
    assert [call.voice_id for call in fallback.calls] == ["fallback-Lilac"]


def test_a_config_error_on_the_chosen_provider_does_not_consult_the_chain(monkeypatch):
    """A missing API key on the provider the user chose is 503 — it will not
    succeed on retry, so the fallback chain must not be consulted at all."""
    primary = ScriptedTTS(
        name="primary",
        voices=[a_voice(id="prime", provider="primary")],
        fail=(MediaProviderConfigError("PRIMARY_KEY is not set."),),
    )
    fallback = ScriptedTTS(
        name="fallback", voices=[a_voice(id="fallback-Lilac", provider="fallback")]
    )
    install_providers(monkeypatch, {"primary": primary, "fallback": fallback})
    monkeypatch.setattr("app.config.settings.tts_fallback_providers", ["fallback"])

    with pytest.raises(MediaProviderConfigError):
        asyncio.run(voice_service.synthesize(
            None, user_id=1, text="Hello.", voice_id="prime", save=False,
        ))

    assert fallback.calls == [], "a fixable-by-operator error silently changed voices"


def test_an_unconfigured_fallback_is_skipped_and_the_next_one_answers(monkeypatch):
    """The keyless "edge" case: a fallback whose key is missing fails with a
    config error, is skipped, and the next fallback in the chain answers."""
    primary = ScriptedTTS(
        name="primary",
        voices=[a_voice(id="prime", provider="primary")],
        fail=(MediaProviderError("primary is down"),),
    )
    unconfigured = ScriptedTTS(
        name="unconfigured",
        voices=[a_voice(id="uc-Lilac", provider="unconfigured")],
        fail=(MediaProviderConfigError("NO_KEY is not set."),),
    )
    last = ScriptedTTS(
        name="last", voices=[a_voice(id="last-Lilac", provider="last")]
    )
    install_providers(
        monkeypatch,
        {"primary": primary, "unconfigured": unconfigured, "last": last},
    )
    monkeypatch.setattr(
        "app.config.settings.tts_fallback_providers", ["unconfigured", "last"]
    )

    _, details = asyncio.run(voice_service.synthesize(
        None, user_id=1, text="Hello.", voice_id="prime", save=False,
    ))

    assert details["provider"] == "last"
    assert [call.voice_id for call in last.calls] == ["last-Lilac"]


def test_when_no_fallback_answers_the_chain_fails_as_one_clear_error(monkeypatch):
    """A single user-facing error, not a partial result or a three-error
    summary — the failure is reported as the last provider's reason."""
    primary = ScriptedTTS(
        name="primary",
        voices=[a_voice(id="prime", provider="primary")],
        fail=(MediaProviderError("rate limited"),),
    )
    install_providers(monkeypatch, {"primary": primary})
    monkeypatch.setattr("app.config.settings.tts_fallback_providers", [])

    with pytest.raises(voice_service.VoiceError, match="rate limited"):
        asyncio.run(voice_service.synthesize(
            None, user_id=1, text="Hello.", voice_id="prime", save=False,
        ))


# ===========================================================================
# Provider prosody and locale handling
# ===========================================================================


def test_the_prosody_conversions_are_shared_and_sane():
    """The multiplier the studio uses means the same thing in every provider."""
    from app.services.video.providers.base import pitch_semitones, volume_gain_db

    # Unity is exactly nothing; an octave up is a full octave; half volume is
    # −6 dB — the convention any provider that takes gain documents.
    assert pitch_semitones(1.0) == 0.0
    assert pitch_semitones(2.0) == pytest.approx(12.0)
    assert volume_gain_db(1.0) == 0.0
    assert volume_gain_db(0.5) == pytest.approx(-6.02, abs=0.01)
    # Silence is clamped to the −96 dB floor providers accept, not −infinity.
    assert volume_gain_db(0.0) == -96.0


def test_google_locale_is_matched_as_a_bcp47_tag_not_split_from_the_name():
    """Splicing the first two hyphen segments breaks on the third and fourth
    forms Google actually ships — three-letter languages, script tags."""
    from app.services.video.providers.google_tts import _LOCALE_RE

    assert _LOCALE_RE.match("en-US-Standard-C").group(0) == "en-US"
    assert _LOCALE_RE.match("en-GB-Wavenet-B").group(0) == "en-GB"
    assert _LOCALE_RE.match("pt-BR-Wavenet-A").group(0) == "pt-BR"
    # Three-letter language code — the two-hyphen-segment splice breaks here
    # because "cmn-CN-Wavenet-B" would demand CN be the voice, not the region.
    assert _LOCALE_RE.match("cmn-CN-Wavenet-B").group(0) == "cmn-CN"
    assert _LOCALE_RE.match("yue-HK-Standard-C").group(0) == "yue-HK"
