"""Post-generation endpoints."""
from __future__ import annotations

import asyncio
import random

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user_optional
from app.database import get_db
from app.models.user import User
from app.services import business_profile_service
from app.schemas.post import (
    GeneratePostRequest,
    GeneratePostResponse,
    Platform,
    Tone,
)
from app.services.ai_service import (
    assist_text,
    build_visual_prompt,
    generate_article,
    generate_carousel_outline,
    generate_posts,
    generate_template_content,
    interpret_image_edit,
)
from app.services.extract_service import ExtractError, extract_file, extract_url
from app.services.image_service import (
    ASPECT_RATIOS,
    IMAGE_QUALITIES,
    IMAGE_STYLES,
    SAFE_ZONES,
    ImageError,
    build_image_candidates,
    compose_prompt,
    dimensions_for,
    generate_with_fallback,
    search_stock,
)
from app.services.image_service import generate as generate_image
from app.services.providers import ProviderConfigError, ProviderError, available_providers

router = APIRouter(prefix="/api", tags=["posts"])


@router.post("/generate-post", response_model=GeneratePostResponse)
async def generate_post(
    req: GeneratePostRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> GeneratePostResponse:
    """Generate optimized post copy for one platform, or all platforms.

    When a user is signed in, their saved business profile (if any) is added as
    context so posts are on-brand. Skipped/empty fields are ignored, and no
    profile — or even no login — is required.
    """
    business_context = (
        business_profile_service.context_for_user(db, user.id) if user else None
    )
    try:
        return await generate_posts(req, business_context=business_context)
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
    # Which provider produced the image (e.g. "pollinations-flux"). Also logged.
    provider: str = "pollinations-flux"
    # Ordered alternate sources the client can fall back to if `image_url` fails.
    fallbacks: list[str] = []


@router.post("/generate-image", response_model=GenerateImageResponse)
async def generate_image_endpoint(req: GenerateImageRequest) -> GenerateImageResponse:
    """Generate an AI image and return its public URL.

    Uses the provider fallback chain: if the primary provider errors, times
    out, is rate-limited or returns a non-image, the next provider is tried
    automatically (verify=True), and the provider that succeeded is reported.
    """
    try:
        url, provider = await generate_with_fallback(
            req.prompt, verify=req.verify, width=req.width, height=req.height
        )
    except ImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # Remaining sources, so the client keeps a safety net even post-verify.
    fallbacks = [
        c
        for c in build_image_candidates(req.prompt, width=req.width, height=req.height)
        if c != url
    ]
    return GenerateImageResponse(image_url=url, provider=provider, fallbacks=fallbacks)


# ---------------------------------------------------------------------------
# Free stock-image search — an alternative to AI generation (Openverse by
# default; Pexels/Pixabay/Unsplash when a key is configured).
# ---------------------------------------------------------------------------
class StockImage(BaseModel):
    url: str
    thumb: str
    credit: str
    source: str
    link: str | None = None


class StockImagesResponse(BaseModel):
    provider: str
    results: list[StockImage]


@router.get("/stock-images", response_model=StockImagesResponse)
async def stock_images_endpoint(query: str, per_page: int = 12) -> StockImagesResponse:
    """Search a free stock-photo provider for `query`."""
    if not query.strip():
        raise HTTPException(status_code=422, detail="A search query is required.")
    try:
        provider, results = await search_stock(query, per_page=per_page)
    except ImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return StockImagesResponse(
        provider=provider, results=[StockImage(**r) for r in results]
    )


# ---------------------------------------------------------------------------
# Image composition: single image or a distinct-per-slide carousel.
# Caption generation (generate-post) stays a separate call, so a failure here
# never costs the user their captions — the frontend composes partial success.
# ---------------------------------------------------------------------------
class ComposeImagesRequest(BaseModel):
    # Generous limit because the caller may hand over the whole post — the
    # point of `analyze` is that the post itself is the best description of
    # what the image should show.
    prompt: str = Field(..., min_length=2, max_length=6000,
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
    # ---- Brand Kit ------------------------------------------------------
    # Set when the client will overlay brand layers on the result. Changes the
    # prompt: bias toward the brand palette, reserve clean space for the
    # overlay, and suppress the garbled pseudo-text diffusion models produce.
    branded: bool = Field(default=False, description="Image will carry a brand overlay.")
    brand_colors: list[str] = Field(
        default_factory=list, description="Hex brand colours to bias the palette."
    )
    brand_reserve: str | None = Field(
        default=None,
        description="Where the overlay sits, e.g. 'bottom' — kept clean.",
    )
    # Phase 2: how the background should be composed for the chosen layout,
    # e.g. "clear space in the lower third". Without this the image competes
    # with the text drawn on top of it.
    background_hint: str | None = Field(default=None, max_length=200)
    # ---- Layout awareness ------------------------------------------------
    # The region of the frame the template reserves for text ("bottom",
    # "center", …). Drives both the scene the LLM writes and the composition
    # rules folded into the final prompt, so the headline lands on empty space
    # instead of on the subject's face.
    safe_zone: str | None = Field(default=None, max_length=20)
    template_label: str | None = Field(
        default=None, max_length=60, description="Layout name, e.g. 'Quote'."
    )
    headline: str | None = Field(
        default=None, max_length=200,
        description="On-image headline, when already written — the strongest "
                    "signal of what the picture should show.",
    )
    # Read the post and write a proper image brief before generating, instead
    # of handing raw post text to the image model. Off gives the previous
    # behaviour verbatim.
    analyze: bool = Field(default=True, description="Derive a visual brief from the post.")
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
async def generate_images_endpoint(
    req: ComposeImagesRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> ComposeImagesResponse:
    """Generate one image, or a distinct-per-slide carousel, at a chosen ratio.

    With `analyze` on (the default) the post is read first and turned into a
    concrete visual brief — a subject, a setting, lighting and framing — before
    anything is sent to the image model. Handing raw post copy to a diffusion
    model is what produces the generic, unrelated stock look: it cannot draw a
    marketing claim, only a specific thing in a specific place.

    The chosen template's safe zone and the selected style ride along, so the
    scene is framed around the space the headline, CTA and logo will occupy.
    """
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
    # An unknown zone name would silently drop the composition rules, leaving
    # text over a busy image with nothing to point at.
    if req.safe_zone and req.safe_zone.lower() not in SAFE_ZONES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported safe zone {req.safe_zone!r}. "
                   f"Allowed: {', '.join(SAFE_ZONES)}.",
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
        # Brand Kit: bias the palette, and ask for clean space plus no
        # generated lettering where the overlay layers will sit.
        "branded": req.branded,
        "brand_colors": req.brand_colors,
        "brand_reserve": req.brand_reserve,
        "background_hint": req.background_hint,
        # Layout: keep the text region readable and make the frame look
        # art-directed rather than snapshot-like.
        "safe_zone": req.safe_zone,
        "design_direction": bool(req.safe_zone or req.template_label),
    }

    business_context = (
        business_profile_service.context_for_user(db, user.id) if user else None
    )
    # The style's own description is richer direction for the LLM than its key.
    style_label = IMAGE_STYLES.get(req.style or "")

    async def visual_brief(source: str) -> str:
        """Post text -> concrete scene. Falls back to `source` on any failure."""
        if not req.analyze:
            return source
        return await build_visual_prompt(
            # A whole pasted article is more than the brief needs; the opening
            # carries the subject, and the rest just costs tokens.
            source[:2000],
            style_label=style_label,
            template_label=req.template_label,
            safe_zone=req.safe_zone,
            headline=req.headline,
            business_context=business_context,
        )

    def compose_image(prompt: str, *, seed: int, label: str | None) -> ComposedImage:
        # Multiple sources so a rate-limited primary still yields an image.
        # Keyword fallbacks search the original topic, not the art direction.
        candidates = build_image_candidates(
            prompt, width=width, height=height, seed=seed, enhance=enhance,
            keyword_source=req.prompt,
        )
        return ComposedImage(
            url=candidates[0], fallbacks=candidates[1:], label=label, prompt=prompt
        )

    try:
        if req.carousel:
            outline = await generate_carousel_outline(
                req.prompt, req.slides, platform=req.platform
            )
            # One brief per slide, in parallel — sequential LLM calls would put
            # a ten-slide carousel well past a comfortable wait.
            briefs = await asyncio.gather(
                *(
                    visual_brief(f"{desc}. Part of a series about: {req.prompt}")
                    for desc in outline
                )
            )
            images: list[ComposedImage] = []
            for i, (desc, brief) in enumerate(zip(outline, briefs)):
                # The brief leads — it is the part the image model weights
                # most — with the series cue behind it to keep slides cohesive.
                slide_base = f"{brief}. One slide of a cohesive social carousel"
                prompt = compose_prompt(slide_base, **style_opts)
                images.append(compose_image(prompt, seed=base_seed + i, label=desc))
        else:
            prompt = compose_prompt(await visual_brief(req.prompt), **style_opts)
            images = [compose_image(prompt, seed=base_seed, label=None)]
    except ImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ComposeImagesResponse(
        images=images, aspect_ratio=req.aspect_ratio,
        width=width, height=height, carousel=req.carousel,
    )


# ---------------------------------------------------------------------------
# "Create From" content extraction — URLs, YouTube, and document uploads all
# reduce to a plain-text source that feeds the normal generation prompt.
# ---------------------------------------------------------------------------
class ExtractUrlRequest(BaseModel):
    url: str = Field(..., min_length=3, max_length=2000)


class ExtractResponse(BaseModel):
    title: str | None = None
    text: str
    source: str | None = None


@router.post("/extract", response_model=ExtractResponse)
async def extract_endpoint(req: ExtractUrlRequest) -> ExtractResponse:
    """Extract readable text from a web page or YouTube link."""
    try:
        data = await extract_url(req.url)
    except ExtractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ExtractResponse(**data)


@router.post("/extract-file", response_model=ExtractResponse)
async def extract_file_endpoint(file: UploadFile = File(...)) -> ExtractResponse:
    """Extract text from an uploaded PDF / DOCX / TXT document."""
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")
    try:
        data = extract_file(file.filename or "", raw)
    except ExtractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ExtractResponse(**data)


# ---------------------------------------------------------------------------
# LinkedIn Article generation — long-form, no hashtags/short captions.
# ---------------------------------------------------------------------------
class GenerateArticleRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=8000)
    audience: str | None = Field(default=None, max_length=200)
    tone: Tone = Tone.professional
    provider: str | None = None


class GeneratedArticle(BaseModel):
    title: str
    body: str
    tags: list[str] = []
    seo_keywords: list[str] = []
    reading_time_min: int
    word_count: int
    cover_image_prompt: str
    provider: str
    model: str


@router.post("/generate-article", response_model=GeneratedArticle)
async def generate_article_endpoint(
    req: GenerateArticleRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> GeneratedArticle:
    """Generate a full LinkedIn article from a topic (with business context)."""
    from app.services.providers import get_provider

    business_context = (
        business_profile_service.context_for_user(db, user.id) if user else None
    )
    try:
        data = await generate_article(
            req.topic, audience=req.audience, tone=req.tone.value,
            provider_name=req.provider, business_context=business_context,
        )
        provider = get_provider(req.provider)
    except ProviderConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GeneratedArticle(provider=provider.name, model=provider.model, **data)


# ---------------------------------------------------------------------------
# Template content — the on-image text for a chosen layout.
#
# Separate from caption generation on purpose: this copy has to fit fixed boxes
# in a design, so it is written to per-slot character budgets rather than as
# prose that is later squeezed into the frame.
# ---------------------------------------------------------------------------
class TemplateContentRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=500)
    template_label: str = Field(..., max_length=60, description="e.g. 'Quote'")
    slots: list[str] = Field(..., description="Slot names the layout exposes.")
    tone: str = Field(default="professional", max_length=40)
    audience: str | None = Field(default=None, max_length=200)
    # Per-template character budgets. A layout may be tighter than the default
    # for a slot; it can never be looser (see ai_service._slot_limits).
    max_chars: dict[str, int] | None = Field(
        default=None, description="Slot name -> maximum characters for this layout."
    )
    provider: str | None = None


class TemplateContentResponse(BaseModel):
    # Slot name -> text. Missing slots come back empty; templates skip those.
    content: dict[str, str]


@router.post("/generate-template-content", response_model=TemplateContentResponse)
async def generate_template_content_endpoint(
    req: TemplateContentRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> TemplateContentResponse:
    """Write the text that fills a content template's slots."""
    business_context = (
        business_profile_service.context_for_user(db, user.id) if user else None
    )
    try:
        content = await generate_template_content(
            req.topic,
            slots=req.slots,
            template_label=req.template_label,
            tone=req.tone,
            audience=req.audience,
            max_chars=req.max_chars,
            provider_name=req.provider,
            business_context=business_context,
        )
    except ProviderConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TemplateContentResponse(content=content)


# ---------------------------------------------------------------------------
# AI image editing — natural language to structured layer operations.
#
# The image provider is text-to-image and cannot edit a bitmap. It rarely needs
# to: the graphic is a layer stack, so most requests ("move the logo", "use my
# brand colours") are layer edits applied client-side with the artwork
# untouched. Only requests that change what is depicted return a regenerating
# operation, and the layers survive that too.
# ---------------------------------------------------------------------------
class EditLayerSummary(BaseModel):
    id: str
    type: str
    text: str | None = None


class ImageEditRequest(BaseModel):
    instruction: str = Field(..., min_length=2, max_length=400)
    layers: list[EditLayerSummary] = Field(default_factory=list)
    style: str | None = Field(default=None, max_length=40)
    provider: str | None = None


class ImageEditResponse(BaseModel):
    operations: list[dict]
    explanation: str = ""
    # True when the client must fetch new artwork; layers are kept either way.
    needs_regeneration: bool = False


@router.post("/image-edit", response_model=ImageEditResponse)
async def image_edit_endpoint(
    req: ImageEditRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> ImageEditResponse:
    """Interpret a plain-English image edit as structured operations."""
    business_context = (
        business_profile_service.context_for_user(db, user.id) if user else None
    )
    try:
        result = await interpret_image_edit(
            req.instruction,
            layers=[l.model_dump() for l in req.layers],
            style=req.style,
            provider_name=req.provider,
            business_context=business_context,
        )
    except ProviderConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ImageEditResponse(**result)


# ---------------------------------------------------------------------------
# AI Assist — optional in-place edits for the manual composer. Transforms the
# user's existing text instead of generating a brand-new post.
# ---------------------------------------------------------------------------
class AssistRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    action: str = Field(..., description="improve|rewrite|shorten|expand|grammar|"
                                         "tone|hashtags|cta|translate")
    tone: str | None = None       # for action=tone
    language: str | None = None   # for action=translate


class AssistResponse(BaseModel):
    result: str


@router.post("/assist", response_model=AssistResponse)
async def assist_endpoint(req: AssistRequest) -> AssistResponse:
    """Apply an optional AI edit to existing text (Improve, Rewrite, Translate…)."""
    try:
        result = await assist_text(
            req.text, req.action, tone=req.tone, language=req.language
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AssistResponse(result=result)


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
        "stock_search": True,
    }
