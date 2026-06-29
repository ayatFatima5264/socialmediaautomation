"""Post-generation endpoints."""
from __future__ import annotations

import random

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel, Field

from app.config import settings
from app.schemas.post import (
    GeneratePostRequest,
    GeneratePostResponse,
    Platform,
    Tone,
)
from app.services.ai_service import generate_carousel_outline, generate_posts
from app.services.image_service import (
    ASPECT_RATIOS,
    IMAGE_QUALITIES,
    IMAGE_STYLES,
    ImageError,
    build_image_candidates,
    compose_prompt,
    dimensions_for,
)
from app.services.image_service import generate as generate_image
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


# ---------------------------------------------------------------------------
# Image composition: single image or a distinct-per-slide carousel.
# Caption generation (generate-post) stays a separate call, so a failure here
# never costs the user their captions — the frontend composes partial success.
# ---------------------------------------------------------------------------
class ComposeImagesRequest(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=500,
                        description="Base idea/topic the image(s) depict.")
    platform: Platform | None = Field(
        default=None, description="Optional platform, used to theme the carousel."
    )
    aspect_ratio: str = Field(default="1:1", description="One of the supported ratios.")
    carousel: bool = False
    slides: int = Field(default=1, ge=1, le=10)
    style: str | None = Field(default=None, description="Visual style preset.")
    quality: str = Field(default="standard", description="'standard' or 'hd'.")
    negative_prompt: str | None = Field(
        default=None, max_length=300, description="Things to avoid, comma separated."
    )
    prompt_enhancer: bool = Field(
        default=False, description="Auto-enrich the prompt for a stronger image."
    )
    # Verify each image actually renders before returning (slower but safer).
    verify: bool = False


class ComposedImage(BaseModel):
    url: str
    # Ordered alternate sources tried by the client if `url` fails (e.g. rate
    # limited). Guarantees the user still gets an image.
    fallbacks: list[str] = []
    label: str | None = None
    prompt: str | None = None


class ComposeImagesResponse(BaseModel):
    images: list[ComposedImage]
    aspect_ratio: str
    width: int
    height: int
    carousel: bool


@router.post("/generate-images", response_model=ComposeImagesResponse)
async def generate_images_endpoint(req: ComposeImagesRequest) -> ComposeImagesResponse:
    """Generate one image, or a distinct-per-slide carousel, at a chosen ratio."""
    if req.aspect_ratio not in ASPECT_RATIOS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported aspect ratio {req.aspect_ratio!r}. "
                   f"Allowed: {', '.join(ASPECT_RATIOS)}.",
        )
    if req.quality not in IMAGE_QUALITIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported quality {req.quality!r}. "
                   f"Allowed: {', '.join(IMAGE_QUALITIES)}.",
        )
    if req.carousel and not (2 <= req.slides <= 10):
        raise HTTPException(
            status_code=422, detail="Carousel slides must be between 2 and 10."
        )

    width, height = dimensions_for(req.aspect_ratio)
    enhance = req.quality == "hd"
    # Random base seed so each (re)generation yields fresh images; carousel
    # slides get consecutive seeds for variety while staying cohesive.
    base_seed = random.randint(1, 1_000_000)

    style_opts = {
        "style": req.style,
        "negative": req.negative_prompt,
        "prompt_enhancer": req.prompt_enhancer,
    }

    def compose_image(prompt: str, *, seed: int, label: str | None) -> ComposedImage:
        # Multiple sources so a rate-limited primary still yields an image.
        candidates = build_image_candidates(
            prompt, width=width, height=height, seed=seed, enhance=enhance
        )
        return ComposedImage(
            url=candidates[0], fallbacks=candidates[1:], label=label, prompt=prompt
        )

    try:
        if req.carousel:
            outline = await generate_carousel_outline(
                req.prompt, req.slides, platform=req.platform
            )
            images: list[ComposedImage] = []
            for i, desc in enumerate(outline):
                slide_base = f"{desc}. Cohesive social carousel about {req.prompt}"
                prompt = compose_prompt(slide_base, **style_opts)
                images.append(compose_image(prompt, seed=base_seed + i, label=desc))
        else:
            prompt = compose_prompt(req.prompt, **style_opts)
            images = [compose_image(prompt, seed=base_seed, label=None)]
    except ImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ComposeImagesResponse(
        images=images, aspect_ratio=req.aspect_ratio,
        width=width, height=height, carousel=req.carousel,
    )


@router.get("/meta")
def meta() -> dict:
    """Dropdown options + active provider, for the frontend to consume."""
    return {
        "platforms": [p.value for p in Platform],
        "tones": [t.value for t in Tone],
        "providers": available_providers,
        "active_provider": settings.ai_provider,
        "aspect_ratios": list(ASPECT_RATIOS),
        "image_styles": list(IMAGE_STYLES),
        "image_qualities": list(IMAGE_QUALITIES),
    }
