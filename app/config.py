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
    # Which provider ai_service uses by default. Real free options:
    #   "gemini" (Google, generous free tier) or "groq" (fast free Llama).
    # "mock" (offline, no key) is still available but must be selected
    # explicitly — a real provider with a missing key now errors clearly
    # instead of silently producing placeholder text.
    ai_provider: str = "gemini"

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

    # ---- Scheduler -------------------------------------------------------
    # How often the background loop checks for due scheduled posts (seconds).
    scheduler_poll_seconds: int = 30

    # ---- CORS (React frontend dev server) --------------------------------
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
