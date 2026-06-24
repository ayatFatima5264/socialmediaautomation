"""Post-generation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel, Field

from app.config import settings
from app.schemas.post import (
    GeneratePostRequest,
    GeneratePostResponse,
    Platform,
    Tone,
)
from app.services.ai_service import generate_posts
from app.services.image_service import ImageError, generate as generate_image
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


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=500,
                        description="What the image should depict.")
    width: int | None = Field(default=None, ge=256, le=2048)
    height: int | None = Field(default=None, ge=256, le=2048)
    # Verify the image actually renders before returning (slower but safer).
    verify: bool = False


class GenerateImageResponse(BaseModel):
    image_url: str


@router.post("/generate-image", response_model=GenerateImageResponse)
async def generate_image_endpoint(req: GenerateImageRequest) -> GenerateImageResponse:
    """Generate an AI image (Pollinations) and return its public URL."""
    try:
        url = await generate_image(
            req.prompt, verify=req.verify, width=req.width, height=req.height
        )
    except ImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GenerateImageResponse(image_url=url)


@router.get("/meta")
def meta() -> dict:
    """Dropdown options + active provider, for the frontend to consume."""
    return {
        "platforms": [p.value for p in Platform],
        "tones": [t.value for t in Tone],
        "providers": available_providers,
        "active_provider": settings.ai_provider,
    }
