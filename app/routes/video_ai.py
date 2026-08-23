"""AI video creation — the pipeline, one stage per endpoint.

    GET   /api/video/ai/options                      what the form can offer
    POST  /api/video/ai/script                       a script, no project yet
    POST  /api/video/ai/projects                     project + script + scenes

    GET   /api/video/projects/{id}/script
    PUT   /api/video/projects/{id}/script            edit it
    POST  /api/video/projects/{id}/script/regenerate

    GET   /api/video/projects/{id}/scenes
    POST  /api/video/projects/{id}/scenes/generate   script -> scenes
    PATCH /api/video/projects/{id}/scenes/{scene_id} edit one
    POST  /api/video/projects/{id}/scenes/reorder
    DELETE /api/video/projects/{id}/scenes/{scene_id}

    POST  /api/video/projects/{id}/scenes/{scene_id}/visual   one picture
    POST  /api/video/projects/{id}/scenes/{scene_id}/voice    one narration
    POST  /api/video/projects/{id}/ai/subtitles               scenes -> a track
    POST  /api/video/projects/{id}/ai/build                   scenes -> timeline

**Why the expensive stages are per scene.** Generating eight images or eight
voice-overs inside one request is a request that times out, and a spinner that
might mean "working" or "dead" for ninety seconds. One call per scene lets the
client show "5 of 8" — which is both true and useful — and lets a single scene
be retried without redoing the rest.

**Every stage writes to the real project.** The script goes on
`VideoProject.script`, the scenes are `VideoScene` rows, the pictures and the
narration are `VideoAsset`s in the user's library, the captions are a
`VideoSubtitle` track, and `build` assembles all of it into
`VideoProject.timeline` — the document the editor opens and the compositor
renders. After the pipeline runs there is nothing left that is "an AI video"
rather than a video.

**Nothing here is a new provider.** Text goes through `AIProvider`, images
through `image_service`, speech through the `TTSProvider` chain. This module
sequences them.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.models.video_project import VideoProject
from app.models.video_scene import SCENE_SOURCES, SCENE_TRANSITIONS, VideoScene
from app.schemas.video_ai import (
    AIOptions,
    AIProjectCreated,
    BuildRequest,
    CreateAIProject,
    GenerateScenes,
    SceneRead,
    SceneReorder,
    SceneUpdate,
    ScriptBrief,
    ScriptDocument,
    ScriptSave,
    ScriptSectionRewrite,
    StoryboardRead,
    SubtitleRequest,
    VisualRequest,
    VoiceRequest,
)
from app.services.video import projects as project_service
from app.services.video import scripting, storyboard, visuals
from app.services.video import subtitles as subtitle_engine
from app.services.video import voice as voice_service
from app.services.video.metering import UsageLimitExceeded
from app.services.video.providers import MediaProviderConfigError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video-ai"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _owned(db: Session, user: User, project_id: int) -> VideoProject:
    try:
        return project_service.get_project(db, user_id=user.id, project_id=project_id)
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _scene(db: Session, project: VideoProject, scene_id: int) -> VideoScene:
    row = db.get(VideoScene, scene_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="That scene does not exist.")
    return row


def _asset_url(asset: VideoAsset | None) -> str | None:
    if asset is None:
        return None
    return f"{settings.backend_url}/api/storage/o/{asset.token}"


def _scene_read(db: Session, row: VideoScene) -> SceneRead:
    data = SceneRead.model_validate(row)
    if row.asset_id:
        data.asset_url = _asset_url(db.get(VideoAsset, row.asset_id))
    if row.voice_asset_id:
        voice = db.get(VideoAsset, row.voice_asset_id)
        data.voice_url = _asset_url(voice)
        data.voice_duration = voice.duration_seconds if voice else None
    return data


def _storyboard(db: Session, project: VideoProject) -> StoryboardRead:
    rows = storyboard.load_scenes(db, project.id)
    return StoryboardRead(
        project_id=project.id,
        scenes=[_scene_read(db, row) for row in rows],
        summary=storyboard.storyboard_summary(db, project),
        script=project.script or {},
    )


def _http(exc: Exception) -> HTTPException:
    """Map a pipeline error onto a status code.

    503 for an unconfigured provider is the one that matters: it tells the user
    the deployment is missing something rather than that their input was wrong,
    which is the difference between "try again" and "ask your administrator".
    """
    if isinstance(exc, MediaProviderConfigError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, UsageLimitExceeded):
        return HTTPException(status_code=429, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


@router.get("/ai/options", response_model=AIOptions)
def ai_options(user: User = Depends(get_current_user)) -> AIOptions:
    """What the AI form can offer on this deployment."""
    from app.services.video import presets
    from app.services.providers.base import ProviderError
    from app.services.providers.factory import get_provider

    # Whether a provider can actually be built, not whether one is *named*.
    # `AI_PROVIDER` has a default, so `bool(settings.ai_provider)` was always
    # true — the banner could never appear, and a deployment with no key sent
    # the user through the whole brief before failing on the generate call.
    try:
        text_available = get_provider() is not None
    except ProviderError:
        text_available = False
    except Exception:  # noqa: BLE001 — a probe must not fail the form
        logger.warning("AI provider probe failed", exc_info=True)
        text_available = False

    data = scripting.options()
    return AIOptions(
        **data,
        platforms=[
            {"key": preset["key"], "label": preset["label"]}
            for preset in presets.as_dicts()
        ],
        text_available=text_available,
    )


# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------


@router.post("/ai/script", response_model=ScriptDocument)
async def write_script(
    body: ScriptBrief, user: User = Depends(get_current_user)
) -> ScriptDocument:
    """Write a script without creating anything.

    So the user can see what they are going to get, edit it, and only then
    commit to a project — rather than accumulating abandoned projects from
    every topic they tried.
    """
    try:
        brief = scripting.build_brief(**body.model_dump())
        script = await scripting.generate_script(brief)
    except scripting.ScriptError as exc:
        raise _http(exc) from exc

    return ScriptDocument(**script)


BRIEF_INPUT_KEYS = (
    "topic", "language", "tone", "audience", "duration_seconds",
    "platform", "content_type", "instructions", "visual_mode",
)


def _brief_from(stored: dict) -> dict:
    """A stored brief reduced to the inputs `build_brief` accepts.

    A brief on a saved script also carries computed values — the word budget,
    the language label — which are outputs, not arguments.
    """
    return {
        key: stored.get(key)
        for key in BRIEF_INPUT_KEYS
        if stored.get(key) is not None
    }


@router.post("/ai/script/section", response_model=ScriptDocument)
async def rewrite_script_section(
    body: ScriptSectionRewrite, user: User = Depends(get_current_user)
) -> ScriptDocument:
    """Rewrite one section of a script and hand back the whole document.

    Projectless, like `/ai/script`: this is an edit to a document, and whether
    that document is saved on a project is the caller's business. A project
    saves the result through the existing PUT, which is the same path a manual
    edit takes — one way for a script to change, however it changed.
    """
    script = dict(body.script or {})
    stored = body.brief.model_dump() if body.brief else (script.get("brief") or {})

    if not (stored.get("topic") or "").strip():
        raise HTTPException(
            status_code=422,
            detail="This script has no brief to rewrite from. Send one.",
        )

    try:
        brief = scripting.build_brief(**_brief_from(stored))
        updated = await scripting.regenerate_section(
            brief, script, body.section, point_id=body.point_id
        )
    except scripting.ScriptError as exc:
        raise _http(exc) from exc

    return ScriptDocument(**updated)


@router.get("/projects/{project_id}/script", response_model=ScriptDocument)
def get_script(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScriptDocument:
    project = _owned(db, user, project_id)
    return ScriptDocument(**(project.script or {}))


@router.put("/projects/{project_id}/script", response_model=ScriptDocument)
def save_script(
    project_id: int,
    body: ScriptSave,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScriptDocument:
    """Save an edited script.

    The estimate is recomputed from the words actually in it, so a user who
    cuts two sentences immediately sees the shorter runtime rather than the
    number the generator was aiming for.
    """
    project = _owned(db, user, project_id)

    # Structurally sound before it is measured or stored — the words the user
    # typed are untouched, but a `main_points` that is not a list of objects
    # would otherwise reach the duration arithmetic and fail there.
    script = scripting.sanitize_document(dict(body.script or {}))
    script.setdefault("brief", (project.script or {}).get("brief") or {})
    script["estimated_seconds"] = scripting.estimated_duration(script)
    target = (script.get("brief") or {}).get("duration_seconds") or 0
    script["fits_budget"] = not target or script["estimated_seconds"] <= target * 1.15

    try:
        project_service.update_project(
            db,
            project=project,
            patch={"script": script},
            expected_revision=body.expected_revision,
        )
    except project_service.RevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except project_service.ProjectError as exc:
        raise _http(exc) from exc

    return ScriptDocument(**script)


@router.post("/projects/{project_id}/script/regenerate", response_model=ScriptDocument)
async def regenerate_script(
    project_id: int,
    body: ScriptBrief | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScriptDocument:
    """Write the script again, optionally with a changed brief.

    Leaves the scenes alone. Regenerating a script and silently rebuilding the
    storyboard would throw away every picture the user had already chosen —
    rebuilding is a separate, explicit step.
    """
    project = _owned(db, user, project_id)
    existing = (project.script or {}).get("brief") or {}

    if body is not None:
        brief_input = body.model_dump()
    else:
        if not existing:
            raise HTTPException(
                status_code=422,
                detail="This project has no brief to regenerate from. Send one.",
            )
        brief_input = _brief_from(existing)

    try:
        brief = scripting.build_brief(**brief_input)
        script = await scripting.generate_script(brief)
    except scripting.ScriptError as exc:
        raise _http(exc) from exc

    project_service.update_project(db, project=project, patch={"script": script})
    return ScriptDocument(**script)


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/scenes", response_model=StoryboardRead)
def get_scenes(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StoryboardRead:
    return _storyboard(db, _owned(db, user, project_id))


@router.post("/projects/{project_id}/scenes/generate", response_model=StoryboardRead)
async def generate_scenes(
    project_id: int,
    body: GenerateScenes,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StoryboardRead:
    """Cut the project's script into scenes.

    Replaces the storyboard — see `storyboard.apply_scenes` for why a merge
    would be worse. The script itself is untouched, so this is safe to run
    again after editing one line of narration.
    """
    project = _owned(db, user, project_id)
    script = project.script or {}

    if not script.get("hook") and not script.get("main_points"):
        raise HTTPException(
            status_code=422,
            detail="Write or generate a script before building the scenes.",
        )

    try:
        scenes = storyboard.scenes_from_script(
            script, total_seconds=body.total_seconds
        )
        if body.describe_visuals:
            scenes = await storyboard.describe_visuals(scenes, script=script)
        storyboard.apply_scenes(db, project=project, scenes=scenes)
    except storyboard.StoryboardError as exc:
        raise _http(exc) from exc

    return _storyboard(db, project)


@router.patch(
    "/projects/{project_id}/scenes/{scene_id}", response_model=SceneRead
)
def update_scene(
    project_id: int,
    scene_id: int,
    body: SceneUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SceneRead:
    """Edit one scene — the requirement that every generated part stays
    editable, at the level of the individual scene."""
    project = _owned(db, user, project_id)
    row = _scene(db, project, scene_id)
    patch = body.model_dump(exclude_unset=True)

    if "title" in patch:
        row.title = (patch["title"] or "")[:200] or None
    if "text" in patch:
        row.text = patch["text"] or None
    if "visual_prompt" in patch:
        row.visual_prompt = patch["visual_prompt"] or None
    if "source" in patch and patch["source"] in SCENE_SOURCES:
        row.source = patch["source"]
    if "transition" in patch and patch["transition"] in SCENE_TRANSITIONS:
        row.transition = patch["transition"]
    if "duration_seconds" in patch and patch["duration_seconds"]:
        row.duration_seconds = float(patch["duration_seconds"])
    if "overlay_text" in patch:
        row.settings = {**(row.settings or {}), "overlay_text": patch["overlay_text"] or ""}

    # An asset swap is scoped to the user's own library, so a scene cannot be
    # pointed at somebody else's file.
    for field in ("asset_id", "voice_asset_id"):
        if field not in patch:
            continue
        value = patch[field]
        if value is None:
            setattr(row, field, None)
            continue
        asset = db.get(VideoAsset, value)
        if asset is None or asset.user_id != user.id:
            raise HTTPException(status_code=404, detail="That file does not exist.")
        setattr(row, field, asset.id)
        if field == "asset_id":
            row.source = "asset"

    db.commit()
    # A changed duration moves everything after it.
    storyboard.resequence(db, project.id)
    db.refresh(row)
    return _scene_read(db, row)


@router.post("/projects/{project_id}/scenes/reorder", response_model=StoryboardRead)
def reorder_scenes(
    project_id: int,
    body: SceneReorder,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StoryboardRead:
    project = _owned(db, user, project_id)
    rows = {row.id: row for row in storyboard.load_scenes(db, project.id)}

    if sorted(body.scene_ids) != sorted(rows):
        raise HTTPException(
            status_code=422,
            detail="The new order must list every scene exactly once.",
        )

    for position, scene_id in enumerate(body.scene_ids):
        rows[scene_id].position = position
    db.commit()
    storyboard.resequence(db, project.id)

    return _storyboard(db, project)


@router.delete("/projects/{project_id}/scenes/{scene_id}", status_code=204)
def delete_scene(
    project_id: int,
    scene_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Remove a scene. Its picture and narration stay in the library."""
    project = _owned(db, user, project_id)
    row = _scene(db, project, scene_id)
    db.delete(row)
    db.commit()

    for position, remaining in enumerate(storyboard.load_scenes(db, project.id)):
        remaining.position = position
    db.commit()
    storyboard.resequence(db, project.id)

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Per-scene generation
# ---------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/scenes/{scene_id}/visual", response_model=SceneRead
)
async def generate_visual(
    project_id: int,
    scene_id: int,
    body: VisualRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SceneRead:
    """Give one scene a picture: stock, generated, or a card.

    One scene per request so the client can show real progress and retry a
    single failure — see the module docstring.
    """
    project = _owned(db, user, project_id)
    row = _scene(db, project, scene_id)

    if body.prompt:
        row.visual_prompt = body.prompt[:500]
        db.commit()

    try:
        await visuals.attach_visual(
            db, project=project, scene=row, strategy=body.strategy
        )
    except visuals.VisualError as exc:
        raise _http(exc) from exc

    db.refresh(row)
    return _scene_read(db, row)


@router.post(
    "/projects/{project_id}/scenes/{scene_id}/voice", response_model=SceneRead
)
async def generate_scene_voice(
    project_id: int,
    scene_id: int,
    body: VoiceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SceneRead:
    """Narrate one scene.

    Per scene rather than one voice-over for the whole script, because that is
    what makes a scene independently re-recordable — changing one line should
    not mean re-synthesising four minutes of audio and re-timing everything
    after it.
    """
    project = _owned(db, user, project_id)
    row = _scene(db, project, scene_id)

    text = (row.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=422, detail="This scene has no narration to read."
        )

    language = ((project.script or {}).get("brief") or {}).get("language") or "en-US"
    voice_id = body.voice_id
    if not voice_id:
        # The first voice for the script's language, so a generated video is
        # narrated in the language it was written in without the user having
        # to choose.
        catalogue = await voice_service.list_voices()
        candidates = voice_service.voices_for_language(catalogue, language)
        if not candidates:
            candidates = catalogue
        if not candidates:
            raise HTTPException(
                status_code=503,
                detail="No text-to-speech voice is available on this server.",
            )
        voice_id = candidates[0].id

    try:
        asset, _ = await voice_service.synthesize(
            db,
            user_id=user.id,
            text=text,
            voice_id=voice_id,
            rate=body.rate,
            pitch=body.pitch,
            volume=body.volume,
            style=body.style,
            project_id=project.id,
            title=f"{(row.title or 'Scene')[:40]} — narration",
        )
    except (
        voice_service.VoiceError,
        UsageLimitExceeded,
        MediaProviderConfigError,
    ) as exc:
        raise _http(exc) from exc

    row.voice_asset_id = asset.id

    # The scene is stretched to fit its narration when the synthesis came out
    # longer than the estimate. The alternative is a voice-over cut off
    # mid-sentence, which is the single most obvious way a generated video
    # looks broken.
    spoken = float(asset.duration_seconds or 0)
    if spoken > row.duration_seconds:
        row.duration_seconds = round(min(spoken, storyboard.MAX_SCENE_SECONDS), 2)

    db.commit()
    storyboard.resequence(db, project.id)
    db.refresh(row)
    return _scene_read(db, row)


# ---------------------------------------------------------------------------
# Subtitles, and assembling the timeline
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/ai/subtitles", response_model=dict)
def build_subtitles(
    project_id: int,
    body: SubtitleRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Build a caption track from the scenes.

    Timed from each scene's real start and duration, not from a reading-speed
    estimate over the whole script. The storyboard already knows when every
    line is spoken — and after the voice step it knows it exactly, because the
    scenes were stretched to their narration — so estimating would be throwing
    away information we have.
    """
    from app.models.video_subtitle import VideoSubtitle
    from sqlalchemy import select

    project = _owned(db, user, project_id)
    rows = storyboard.load_scenes(db, project.id)
    if not rows:
        raise HTTPException(status_code=422, detail="This project has no scenes yet.")

    style = subtitle_engine.preset(body.style or subtitle_engine.DEFAULT_PRESET)
    language = (
        body.language
        or ((project.script or {}).get("brief") or {}).get("language")
        or "en-US"
    )

    cues: list[dict] = []
    for row in rows:
        text = (row.text or "").strip()
        if not text:
            continue
        cues.extend(
            subtitle_engine.cues_from_script(
                text,
                duration_seconds=float(row.duration_seconds),
                style=style,
                start_at=float(row.start_seconds),
            )
        )

    if not cues:
        raise HTTPException(
            status_code=422, detail="There is no narration to caption yet."
        )

    # Reuse the project's own empty track rather than adding a second one.
    track = db.scalars(
        select(VideoSubtitle)
        .where(VideoSubtitle.project_id == project.id)
        .order_by(VideoSubtitle.id)
    ).first()
    if track is None:
        track = VideoSubtitle(project_id=project.id, is_primary=True)
        db.add(track)

    track.language = language
    track.source = "script"
    track.cues = cues
    track.style = style
    track.cue_count = len(cues)
    track.duration_seconds = subtitle_engine.total_duration(cues)
    db.commit()
    db.refresh(track)

    return {
        "id": track.id,
        "project_id": project.id,
        "language": track.language,
        "cue_count": track.cue_count,
        "duration_seconds": track.duration_seconds,
        "is_primary": track.is_primary,
    }


@router.post("/projects/{project_id}/ai/build", response_model=dict)
def build_project_timeline(
    project_id: int,
    body: BuildRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Assemble the scenes into the project's timeline — the last AI step.

    After this the project is an ordinary project: the editor opens it, the
    compositor renders it, and nothing downstream knows or cares that a model
    was involved. Everything on the timeline can be dragged, trimmed, split and
    replaced like any other clip.
    """
    project = _owned(db, user, project_id)

    try:
        document = storyboard.build_timeline(
            db,
            project=project,
            include_voice=body.include_voice,
            include_text=body.include_text,
        )
    except storyboard.StoryboardError as exc:
        raise _http(exc) from exc

    project_service.update_project(db, project=project, patch={"timeline": document})

    from app.services.video import timeline as tl

    return {
        "project_id": project.id,
        "revision": project.revision,
        "summary": tl.summary(document),
        # Where the client should go next. The pipeline ends in the editor —
        # that is the point of it.
        "editor_path": f"/video/projects/{project.id}/edit",
    }


# ---------------------------------------------------------------------------
# The whole pipeline
# ---------------------------------------------------------------------------


@router.post("/ai/projects", response_model=AIProjectCreated, status_code=201)
async def create_ai_project(
    body: CreateAIProject,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIProjectCreated:
    """Create a real project, write its script, and cut it into scenes.

    Stops at the storyboard on purpose. Visuals and voice are per-scene calls
    the client drives with a progress bar — see the module docstring — and this
    endpoint stays fast enough to answer inside one request.

    What comes back is a project that already exists in the projects list, with
    a script the user can rewrite and scenes they can edit.
    """
    try:
        brief = scripting.build_brief(
            **body.model_dump(exclude={"name", "script"})
        )
        if body.script:
            # Written and edited elsewhere — Script Studio. Regenerating it here
            # would throw away the edits that made the user want to keep it.
            script = scripting.sanitize_document(dict(body.script))
            script.setdefault("brief", brief)
            script["estimated_seconds"] = scripting.estimated_duration(script)
            target = brief["duration_seconds"]
            script["fits_budget"] = (
                not target or script["estimated_seconds"] <= target * 1.15
            )
        else:
            script = await scripting.generate_script(brief)
    except scripting.ScriptError as exc:
        raise _http(exc) from exc

    try:
        project = project_service.create_project(
            db,
            user_id=user.id,
            name=(body.name or script.get("title") or brief["topic"])[:200],
            project_type="ai",
            platform=brief["platform"],
            apply_brand=True,
        )
    except project_service.ProjectError as exc:
        raise _http(exc) from exc

    project_service.update_project(db, project=project, patch={"script": script})

    try:
        scenes = storyboard.scenes_from_script(script)
        scenes = await storyboard.describe_visuals(scenes, script=script)
        storyboard.apply_scenes(db, project=project, scenes=scenes)
    except storyboard.StoryboardError as exc:
        # The project and its script survive — the user can fix the script and
        # build the scenes themselves rather than losing the generation.
        logger.warning("Storyboard failed for new project %s: %s", project.id, exc)

    rows = storyboard.load_scenes(db, project.id)

    return AIProjectCreated(
        project_id=project.id,
        project={
            "id": project.id,
            "name": project.name,
            "platform": project.platform,
            "aspect_ratio": project.aspect_ratio,
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
            "status": project.status,
        },
        script=script,
        scenes=[_scene_read(db, row) for row in rows],
        summary=storyboard.storyboard_summary(db, project),
        next_steps=["visuals", "voice", "subtitles", "build"],
    )
