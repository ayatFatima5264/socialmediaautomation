"""Application settings, loaded from environment / .env file.

The AI layer is intentionally configured here so providers can be switched
without touching code: set AI_PROVIDER=groq|mock in your .env.
"""
from __future__ import annotations

from functools import lru_cache

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

    # ---- AI image generation (Pollinations: free, no key) ----------------
    # Returns a real image at a public URL — perfect for Instagram, which
    # fetches the image server-side. Default 1080x1080 (IG square).
    pollinations_base: str = "https://image.pollinations.ai"
    image_model: str = "flux"
    image_width: int = 1080
    image_height: int = 1080
    # Ordered AI image models tried by the fallback chain: if the primary
    # (flux) errors/times-out/rate-limits, the next is attempted automatically.
    # After these, non-AI photo hosts (LoremFlickr, Picsum) act as a final
    # guaranteed fallback so the user always gets a visual.
    image_fallback_models: list[str] = ["flux", "turbo"]

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

    # ---- Auth / JWT ------------------------------------------------------
    # CHANGE THIS in production (e.g. `openssl rand -hex 32`).
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 1 day
    # How long a password-reset link stays valid.
    password_reset_expire_minutes: int = 30

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
    x_client_id: str | None = None
    x_client_secret: str | None = None
    pinterest_client_id: str | None = None
    pinterest_client_secret: str | None = None
    threads_client_id: str | None = None
    threads_client_secret: str | None = None

    # ---- CORS (React frontend dev server) --------------------------------
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

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
