"""Post-generation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.post import (
    GeneratePostRequest,
    GeneratePostResponse,
    Platform,
    Tone,
)
from app.services.ai_service import generate_posts
from app.services.providers import ProviderConfigError, ProviderError, available_providers

router = APIRouter(prefix="/api", tags=["posts"])


@router.post("/generate-post", response_model=GeneratePostResponse)
async def generate_post(req: GeneratePostRequest) -> GeneratePostResponse:
    """Generate optimized post copy for one platform, or all platforms."""
    try:
        return await generate_posts(req)
    except ProviderConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/meta")
def meta() -> dict:
    """Dropdown options + active provider, for the frontend to consume."""
    return {
        "platforms": [p.value for p in Platform],
        "tones": [t.value for t in Tone],
        "providers": available_providers,
        "active_provider": settings.ai_provider,
    }
