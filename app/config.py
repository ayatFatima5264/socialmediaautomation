"""Application settings, loaded from environment / .env file.

The AI layer is intentionally configured here so providers can be switched
without touching code: set AI_PROVIDER=groq|mock in your .env.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- AI provider selection -------------------------------------------
    # Primary provider ai_service uses. Real free options:
    #   "groq" (fast free Llama) or "gemini" (Google, generous free tier).
    # "mock" (offline, no key) is still available but must be selected
    # explicitly — a real provider with a missing key now errors clearly
    # instead of silently producing placeholder text.
    ai_provider: str = "groq"

    # Providers tried, in order, if the primary fails at request time (rate
    # limit, timeout, bad response). Any without an API key are skipped. Set to
    # [] to disable fallback. Parsed as a JSON list from the env var, e.g.
    #   AI_FALLBACK_PROVIDERS=["gemini"]
    ai_fallback_providers: list[str] = ["gemini"]

    # ---- Google Gemini (free tier) ---------------------------------------
    # Get a free key at https://aistudio.google.com/apikey
    # Uses Gemini's OpenAI-compatibility endpoint.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    # ---- Groq (free tier) -------------------------------------------------
    # Get a free key at https://console.groq.com/keys
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # ---- Shared generation knobs -----------------------------------------
    ai_request_timeout: float = 30.0
    ai_max_tokens: int = 1024
    ai_temperature: float = 0.8

    # ---- AI image generation (Pollinations) -------------------------------
    # Returns a real image at a public URL — perfect for Instagram, which
    # fetches the image server-side. Default 1080x1080 (IG square).
    #
    # NOTE ON MODELS AND COST (verified against the live API):
    #   GET https://image.pollinations.ai/models  ->  ["sana"]
    # `flux` and `turbo` are no longer served. Requesting them does not error
    # cleanly — the request is routed to `sana` anyway, which is a PAID model,
    # and anonymous calls come back as HTTP 500 wrapping an upstream
    # "402 Insufficient balance ... available balance is 0.0000".
    #
    # So the model list below names what the API actually offers. It does not
    # make generation work: `sana` needs Pollen, and this app sends no API key
    # (there is no key setting — calls are anonymous). Until a key with a
    # balance or grant is configured, every AI attempt fails and the chain
    # falls through to the photo hosts. See the fallback note in image_service.
    pollinations_base: str = "https://image.pollinations.ai"
    image_model: str = "sana"
    image_width: int = 1080
    image_height: int = 1080
    # Ordered AI image models tried by the fallback chain: if the primary
    # errors/times-out/rate-limits, the next is attempted automatically.
    # After these, non-AI photo hosts (LoremFlickr, Picsum) act as a final
    # guaranteed fallback so the user always gets a visual.
    image_fallback_models: list[str] = ["sana"]

    # ---- Free stock image search -----------------------------------------
    # A free alternative to AI generation: search & pick a real stock photo.
    # Default source is Openverse (keyless, CC-licensed, works out of the box).
    # Add any one API key below and that higher-quality provider is used
    # instead — no code change needed.
    #   stock_provider="auto" picks the first configured key, else Openverse.
    stock_provider: str = "auto"  # auto | openverse | pexels | pixabay | unsplash
    openverse_base: str = "https://api.openverse.org"
    pexels_api_key: str | None = None       # https://www.pexels.com/api/
    pixabay_api_key: str | None = None       # https://pixabay.com/api/docs/
    unsplash_access_key: str | None = None   # https://unsplash.com/developers

    # ---- Database --------------------------------------------------------
    # Production target is PostgreSQL, e.g.
    #   postgresql+psycopg://user:pass@localhost:5432/social_saas
    # Defaults to a local SQLite file so the app runs before Postgres is set up.
    # The ORM models are DB-agnostic; only this URL changes between the two.
    database_url: str = "sqlite:///./social_saas.db"

    # ---- Object storage (Cloudflare R2) ----------------------------------
    # Where Video Studio keeps the bytes it produces: uploads, voice-overs,
    # rendered videos, thumbnails. NOT the database and NOT the container's
    # disk — Render wipes the disk on every deploy, and a rendered MP4 is two
    # orders of magnitude larger than the images `media_assets` was sized for.
    #
    # The whole layer sits behind app/services/storage, so this switch is the
    # only thing that knows which bucket vendor is in use:
    #   "auto"     — R2 when its credentials are set, else the database
    #   "r2"       — Cloudflare R2 (production); errors if unconfigured
    #   "database" — bytes in Postgres. Development only; see the module docs.
    storage_backend: str = "auto"

    # From the R2 dashboard: Account ID, then an API token with Object
    # Read & Write on the bucket. The endpoint is derived from the account id
    # unless overridden (custom domains, S3-compatible stand-ins like MinIO).
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None
    r2_endpoint: str | None = None
    # Set when the bucket is served on a public domain (r2.dev or a custom
    # one). Unset means the bucket stays private and reads are presigned.
    r2_public_base_url: str | None = None
    # Lifetime of a presigned GET, in seconds. Only used for a private bucket.
    storage_signed_url_ttl: int = 3600

    # ---- Video Studio: MVP compute limits --------------------------------
    # Render Free is one small shared CPU. These caps are what keep a single
    # long render from starving every other request in the process; raise them
    # when rendering moves to a dedicated worker.
    video_max_duration_seconds: int = 180
    video_max_resolution_height: int = 1080
    video_max_upload_mb: int = 200
    video_max_concurrent_renders: int = 1

    # ---- Video Studio: text-to-speech ------------------------------------
    # "edge" is free and needs no key, and is the only option here that speaks
    # Urdu. Keyed providers are used when selected explicitly.
    #   edge | groq | custom
    tts_provider: str = "edge"
    tts_fallback_providers: list[str] = []
    # Groq's TTS models (English / Arabic only, so not a fallback for Urdu).
    groq_tts_model: str = "playai-tts"
    # Hard ceiling on one synthesis request, in characters.
    tts_max_characters: int = 5000

    # ---- Video Studio: custom / self-hosted TTS ---------------------------
    # Any server exposing OpenAI's POST /audio/speech, which is what the
    # self-hostable open-source engines already speak — openedai-speech (Piper,
    # Coqui XTTS), Kokoro-FastAPI, LocalAI. Setting these runs Voice Studio with
    # no external service at all:
    #
    #   TTS_PROVIDER=custom
    #   CUSTOM_TTS_BASE_URL=http://localhost:8080/v1
    #   CUSTOM_TTS_VOICES=alloy:female:en-US,piper_asad:male:ur-PK
    #
    # There is no voice-catalogue route in that API, so the voices have to be
    # named here: "id:gender:locale", comma-separated. Gender and locale are
    # optional and default to neutral / en-US.
    custom_tts_base_url: str | None = None
    custom_tts_api_key: str | None = None
    custom_tts_model: str = "tts-1"
    custom_tts_voices: str | None = None
    # wav | mp3 | opus | aac | flac. WAV by default because every local engine
    # can produce it without an MP3 encoder, which a slim container may lack.
    custom_tts_format: str = "wav"

    # ---- Video Studio: transcription -------------------------------------
    # Whisper on Groq, using the same GROQ_API_KEY as text generation.
    #   groq | openai
    transcription_provider: str = "groq"
    groq_transcription_model: str = "whisper-large-v3-turbo"
    transcription_base_url: str | None = None
    transcription_api_key: str | None = None
    transcription_model: str = "whisper-1"
    # Groq's audio endpoint caps uploads; keep ours below it.
    transcription_max_upload_mb: int = 24
    transcription_request_timeout: float = 180.0

    # ---- Auth / JWT ------------------------------------------------------
    # CHANGE THIS in production (e.g. `openssl rand -hex 32`).
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 1 day
    # How long a password-reset link stays valid.
    password_reset_expire_minutes: int = 30

    # ---- OAuth token encryption at rest ----------------------------------
    # Fernet key(s) protecting the access/refresh tokens in `social_accounts`.
    # Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Comma-separated for key rotation: the first key encrypts, all of them are
    # tried when decrypting, so old rows keep working until they are rewritten.
    # Unset means tokens are stored in plaintext (the pre-encryption behaviour),
    # which keeps a deploy that has not set it yet from losing every connection.
    token_encryption_key: str | None = None

    # ---- Email (SMTP) — password reset & transactional mail --------------
    # Set these to enable outbound email. Works with any SMTP provider
    # (Gmail app password, SendGrid, Mailgun, Resend SMTP, Amazon SES, ...).
    # Port 465 = implicit SSL; any other port (587) uses STARTTLS.
    # When unset, reset emails are skipped and the reset link is logged instead
    # (so the flow is still testable in development).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None  # defaults to smtp_user; e.g. "AutoSocial AI <no-reply@…>"

    # Where public contact-form messages are emailed. Unset falls back to
    # smtp_from / smtp_user, so a working SMTP setup needs no extra config.
    # Every message is stored in the contact_messages table regardless, so an
    # unset value (or no SMTP at all) never loses a submission.
    contact_to_email: str | None = None

    # ---- Scheduler -------------------------------------------------------
    # How often the background loop checks for due scheduled posts (seconds).
    scheduler_poll_seconds: int = 30

    # ---- Meta / Instagram Graph API --------------------------------------
    # Instagram publishing goes through the Meta Graph API. Create an app at
    # https://developers.facebook.com, add the Instagram product, and put its
    # credentials here. App id/secret are only needed to exchange short-lived
    # tokens for long-lived ones and to run the OAuth redirect flow; you can
    # connect with an already-long-lived token without them.
    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_graph_version: str = "v21.0"

    # Exact OAuth redirect URIs registered in the developer portals. If left
    # unset they default to the standard {backend_url}/api/auth/{platform}/callback
    # form; set them explicitly when the registered value must match to the letter.
    meta_redirect_uri: str | None = None
    instagram_redirect_uri: str | None = None
    # Where the OAuth callback sends the browser back to after connecting.
    frontend_url: str = "http://localhost:5173"

    # ---- Social Accounts: OAuth 2.0 per platform -------------------------
    # Public base URL of THIS backend. Callback URLs are derived from it as
    #   {backend_url}/api/auth/{platform}/callback
    # so every provider's redirect URI is stable and documented (see
    # docs/OAUTH_CALLBACKS.md) — register those exact URLs in each portal.
    # In production set this to your https domain.
    backend_url: str = "http://localhost:8000"

    # Client credentials, one pair per platform. Create an app in each
    # developer portal, register the matching callback URL, and paste the
    # id/secret here (or in .env). A platform with no credentials is reported
    # as "not configured" instead of offering a broken Connect flow.
    #
    # Facebook & Instagram are the exception: both use the Meta app credentials
    # (META_APP_ID / META_APP_SECRET) — Instagram connects via Facebook Login and
    # the user picks a linked Instagram Business account.
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    # LinkedIn's versioned REST API requires a YYYYMM version header, and each
    # version is retired ~1 year after release. Keep this within the last ~12
    # months or posts fail with "Requested version … is not active". Override via
    # LINKEDIN_API_VERSION without a code change; bump the default periodically
    # (see the developer.linkedin.com changelog for currently-active versions).
    linkedin_api_version: str = "202606"
    x_client_id: str | None = None
    x_client_secret: str | None = None
    pinterest_client_id: str | None = None
    pinterest_client_secret: str | None = None
    # Pinterest's access tiers decide which host may create Pins. A Trial-tier
    # app can only create them in the Sandbox environment — creating one in
    # production comes back as 403. Sandbox mirrors the v5 API on a separate
    # host with its own tokens, so switching is a host change plus a reconnect.
    #
    # Leave this true until the Pinterest app is granted Standard access, then
    # set PINTEREST_SANDBOX=false and reconnect. Nothing else changes.
    pinterest_sandbox: bool = True
    # Pinterest matches the redirect URI byte-for-byte against the one registered
    # in the developer dashboard. Leave unset to use the standard
    # {backend_url}/api/auth/pinterest/callback form; set it when the registered
    # value must differ (e.g. the backend is behind a proxy on another host).
    pinterest_redirect_uri: str | None = None
    threads_client_id: str | None = None
    threads_client_secret: str | None = None
    # Meta's dashboard labels these the App ID / App secret, so both namings are
    # accepted for Threads; *_client_* wins if both are set.
    threads_app_id: str | None = None
    threads_app_secret: str | None = None
    # Exact redirect URI registered for Threads, when it must match to the
    # letter. Unset falls back to {backend_url}/api/auth/threads/callback.
    threads_redirect_uri: str | None = None

    # ---- CORS (React frontend dev server) --------------------------------
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # Any origin matching this regex is also allowed, on top of cors_origins.
    # This keeps the deployed frontend working even if CORS_ORIGINS is unset or
    # misconfigured on the host — it allows the Vercel production alias *and*
    # every preview deployment (https://<anything>.vercel.app). Set to an empty
    # string to disable, or override for a custom domain.
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    @field_validator("frontend_url", "backend_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Normalize the public URLs so joining a path can't double the slash.

        Both are used as `{url}/some/path`. A trailing slash in the environment
        (easy to leave in a dashboard field) would produce `https://host//path`
        — which is a *different* path: the SPA router doesn't match `//accounts`
        and shows its 404, and an OAuth redirect URI with a doubled slash no
        longer matches the one registered in the provider's portal.
        """
        return value.rstrip("/")

    def oauth_credentials(self, platform: str) -> tuple[str | None, str | None]:
        """Return (client_id, client_secret) for a platform, or (None, None)."""
        return (
            getattr(self, f"{platform}_client_id", None),
            getattr(self, f"{platform}_client_secret", None),
        )

    def callback_url(self, platform: str) -> str:
        """The exact redirect URI to register in the platform's portal."""
        return f"{self.backend_url}/api/auth/{platform}/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
