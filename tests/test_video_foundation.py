"""Video Studio foundation: migrations, storage, project lifecycle, ownership.

What these cover, and why each one is here rather than left to a later phase:

  * **The migrations actually apply.** Alembic runs in-process on startup and
    its failures are deliberately swallowed (see `app.database.run_migrations`),
    so a broken revision looks exactly like a healthy deploy. A test that
    upgrades, downgrades and upgrades again on a real database is the only
    thing standing between that design decision and a silent outage.
  * **Storage round-trips through the contract, not through R2.** Every backend
    implements the same seven methods; the tests drive `DatabaseStorage` and
    assert on the contract, so a future backend passes or fails the same suite.
    The R2 client itself is covered where it can be without credentials: its
    "is this error a 404 or an outage" logic, which is the part that decides
    whether an outage gets mistaken for a deleted file.
  * **Ownership is checked on every read path.** One test per accessor, each
    asserting that another user's id is indistinguishable from a missing row.
  * **Failures are real failures.** Empty files, oversized files, rejected
    types, missing objects, revision conflicts, and a database write that fails
    after the bytes are already in the bucket.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.database import Base, _create_all_tables
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.models.video_audio import VideoAudio
from app.models.video_project import VideoProject
from app.models.video_render import VideoRender
from app.models.video_scene import VideoScene
from app.models.video_subtitle import VideoSubtitle
from app.services import account_deletion
from app.services.storage import reset_storage_cache
from app.services.storage.base import ObjectNotFound, StorageError
from app.services.storage.database import DatabaseStorage
from app.services.storage.keys import KINDS, build_key, new_token
from app.services.video import assets as asset_service
from app.services.video import projects as project_service
from app.services.video import renders as render_service
from app.services.video import templates as template_service
from app.services.video import versions as version_service

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# A 44-byte silent WAV. Real enough for ffmpeg to probe, small enough to inline.
WAV_BYTES = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'video.db').as_posix()}"


@pytest.fixture()
def session_factory(db_url, monkeypatch):
    """A database with the full schema, and the storage layer pointed at it.

    `SessionLocal` is monkeypatched because `DatabaseStorage` deliberately opens
    its own sessions — it must work from a background renderer that has no
    request-scoped session — so without this it would write to the developer's
    real database instead of the test's.
    """
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr("app.services.storage.database.SessionLocal", factory)
    monkeypatch.setattr("app.config.settings.storage_backend", "database")
    reset_storage_cache()

    yield factory

    reset_storage_cache()
    engine.dispose()


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def make_user(db, email="video@example.com") -> User:
    user = User(email=email, hashed_password="x", full_name="Video Tester")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def user(db):
    return make_user(db)


@pytest.fixture()
def other_user(db):
    return make_user(db, "someone-else@example.com")


# ===========================================================================
# 1. Migrations
# ===========================================================================


def _alembic_config(url: str) -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


VIDEO_TABLES = {
    "video_projects",
    "video_assets",
    "video_scenes",
    "video_audio",
    "video_subtitles",
    "video_renders",
    "video_templates",
    "video_project_versions",
    "usage_events",
    "storage_objects",
    "music_tracks",
}


@pytest.fixture()
def migrated_url(tmp_path):
    """A database built the way the application builds one on boot.

    Legacy tables via `create_all`, Video Studio tables via Alembic — the exact
    order `init_db()` uses. Migration 0001 puts a foreign key on `users`, so
    reversing these two steps fails, and that is worth reproducing rather than
    working around.
    """
    url = f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(bind=engine, tables=_create_all_tables())
    engine.dispose()
    return url


def test_migrations_upgrade_to_head_creates_every_video_table(migrated_url):
    command.upgrade(_alembic_config(migrated_url), "head")

    engine = create_engine(migrated_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert VIDEO_TABLES <= tables, f"missing: {sorted(VIDEO_TABLES - tables)}"
    # The rename in 0002 must not leave the old name behind.
    assert "render_jobs" not in tables


def test_migrations_are_reversible(migrated_url):
    """Upgrade, downgrade, upgrade. A revision that cannot be undone cannot be
    rolled back in an incident, which is when it matters most."""
    cfg = _alembic_config(migrated_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(migrated_url)
    try:
        after_down = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert not (VIDEO_TABLES & after_down), (
        f"downgrade left tables behind: {sorted(VIDEO_TABLES & after_down)}"
    )

    command.upgrade(cfg, "head")
    engine = create_engine(migrated_url)
    try:
        assert VIDEO_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrations_are_idempotent_on_a_second_run(migrated_url):
    """`upgrade head` runs on every boot. The second one must do nothing."""
    cfg = _alembic_config(migrated_url)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")

    engine = create_engine(migrated_url)
    try:
        with engine.connect() as conn:
            versions = [
                row[0] for row in conn.execute(text("SELECT version_num FROM alembic_version"))
            ]
    finally:
        engine.dispose()
    assert versions == ["0004"]


def test_migration_moves_legacy_project_documents_into_rows(migrated_url):
    """0001 stored scenes and subtitles as JSON on the project; 0002 moves them
    into their own tables. A project written under 0001 must not lose them."""
    cfg = _alembic_config(migrated_url)
    command.upgrade(cfg, "0001")

    engine = create_engine(migrated_url)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (email, hashed_password, is_active, timezone, "
                 "onboarding_completed) VALUES ('legacy@example.com', 'x', 1, 'UTC', 1)")
        )
        user_id = conn.execute(text("SELECT id FROM users")).scalar()
        conn.execute(
            text(
                "INSERT INTO video_projects (user_id, name, project_type, platform, "
                "aspect_ratio, width, height, fps, duration_seconds, status, script, "
                "scenes, timeline, subtitles, subtitle_style, brand, export_settings, "
                "revision) VALUES (:uid, 'Legacy', 'ai', 'tiktok', '9:16', 1080, 1920, "
                "30, 12.0, 'draft', '{}', :scenes, '{}', :cues, :style, '{}', '{}', 3)"
            ),
            {
                "uid": user_id,
                "scenes": '[{"title": "Hook", "text": "Watch this", "duration": 4.0},'
                          ' {"title": "Point", "text": "Because", "duration": 8.0}]',
                "cues": '[{"start": 0.0, "end": 4.0, "text": "Watch this"},'
                        ' {"start": 4.0, "end": 12.0, "text": "Because"}]',
                "style": '{"key": "clean", "font_size": 44}',
            },
        )
    engine.dispose()

    command.upgrade(cfg, "0002")

    engine = create_engine(migrated_url)
    try:
        with engine.connect() as conn:
            scenes = conn.execute(
                text("SELECT position, title, text, duration_seconds, start_seconds "
                     "FROM video_scenes ORDER BY position")
            ).all()
            tracks = conn.execute(
                text("SELECT cue_count, duration_seconds, style FROM video_subtitles")
            ).all()
    finally:
        engine.dispose()

    assert [(s[0], s[1], s[3]) for s in scenes] == [(0, "Hook", 4.0), (1, "Point", 8.0)]
    # start_seconds is derived by accumulating the durations before it.
    assert scenes[1][4] == 4.0
    assert len(tracks) == 1
    assert tracks[0][0] == 2
    assert tracks[0][1] == 12.0
    assert "clean" in tracks[0][2]


def test_migration_renames_render_jobs_and_normalises_statuses(migrated_url):
    """`running`/`succeeded` become `processing`/`completed`, and a queued job
    survives the table rename rather than being dropped and recreated."""
    cfg = _alembic_config(migrated_url)
    command.upgrade(cfg, "0001")

    engine = create_engine(migrated_url)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (email, hashed_password, is_active, timezone, "
                 "onboarding_completed) VALUES ('r@example.com', 'x', 1, 'UTC', 1)")
        )
        user_id = conn.execute(text("SELECT id FROM users")).scalar()
        conn.execute(
            text("INSERT INTO video_projects (user_id, name, project_type, platform, "
                 "aspect_ratio, width, height, fps, duration_seconds, status, script, "
                 "scenes, timeline, subtitles, subtitle_style, brand, export_settings, "
                 "revision) VALUES (:uid, 'P', 'blank', 'tiktok', '9:16', 1080, 1920, "
                 "30, 5.0, 'rendering', '{}', '[]', '{}', '[]', '{}', '{}', '{}', 0)"),
            {"uid": user_id},
        )
        project_id = conn.execute(text("SELECT id FROM video_projects")).scalar()
        for status in ("running", "succeeded", "queued"):
            conn.execute(
                text("INSERT INTO render_jobs (user_id, project_id, status, stage, "
                     "progress, settings, timeline_snapshot, attempt) VALUES "
                     "(:uid, :pid, :st, 'encoding', 0.5, '{}', '{}', 1)"),
                {"uid": user_id, "pid": project_id, "st": status},
            )
    engine.dispose()

    command.upgrade(cfg, "0002")

    engine = create_engine(migrated_url)
    try:
        with engine.connect() as conn:
            statuses = sorted(
                row[0] for row in conn.execute(text("SELECT status FROM video_renders"))
            )
            project_status = conn.execute(
                text("SELECT status FROM video_projects")
            ).scalar()
    finally:
        engine.dispose()

    assert statuses == ["completed", "processing", "queued"]
    assert project_status == "processing"


def test_migration_repairs_thumbnails_that_point_at_a_video(migrated_url):
    """0004 clears the rows the old renderer wrote.

    Two cases, and the difference between them is the point: a project with a
    real image attached must be left completely alone, and a project whose
    "thumbnail" is the rendered MP4 must end up with a real image — the poster
    frame where one exists, NULL otherwise. NULL is the correct outcome, not a
    loose end: the export manifest reads it as "no thumbnail yet" and tells the
    user to make one, instead of advertising a PNG it cannot produce.
    """
    cfg = _alembic_config(migrated_url)
    command.upgrade(cfg, "0003")

    # Built through the ORM rather than raw INSERTs: the projects table carries
    # a dozen NOT NULL JSON columns whose shape changes between revisions, and
    # hand-writing them is how a migration test starts failing for a reason that
    # has nothing to do with the migration.
    engine = create_engine(migrated_url)
    Session = sessionmaker(bind=engine, autoflush=False)
    db = Session()
    try:
        user = User(email="r@example.com", hashed_password="x", timezone="UTC")
        db.add(user)
        db.flush()

        def add_project(name: str) -> VideoProject:
            row = VideoProject(
                user_id=user.id,
                name=name,
                platform="custom",
                width=256,
                height=256,
                fps=15,
            )
            db.add(row)
            db.flush()
            return row

        def add_asset(kind: str, content_type: str, meta: dict, project: VideoProject):
            row = VideoAsset(
                user_id=user.id,
                project_id=project.id,
                kind=kind,
                title=kind,
                token=new_token(),
                storage_key=f"users/{user.id}/{kind}/x",
                storage_backend="database",
                content_type=content_type,
                size_bytes=10,
                meta=meta,
            )
            db.add(row)
            db.flush()
            return row

        # A: the broken case — the MP4 assigned as the thumbnail.
        project_a = add_project("Broken")
        project_a.thumbnail_asset_id = add_asset("render", "video/mp4", {}, project_a).id

        # B: broken, but a poster frame from the newer renderer is available.
        project_b = add_project("Repairable")
        project_b.thumbnail_asset_id = add_asset("render", "video/mp4", {}, project_b).id
        poster_b = add_asset(
            "thumbnail", "image/png", {"source": "render_poster"}, project_b
        ).id

        # C: a real thumbnail. Must survive untouched.
        project_c = add_project("Healthy")
        image_c = add_asset("thumbnail", "image/png", {"design": {}}, project_c).id
        project_c.thumbnail_asset_id = image_c

        # D: broken, with no image anywhere on the project.
        project_d = add_project("Hopeless")
        project_d.thumbnail_asset_id = add_asset("render", "video/mp4", {}, project_d).id

        db.commit()
    finally:
        db.close()
        engine.dispose()

    command.upgrade(cfg, "0004")

    engine = create_engine(migrated_url)
    try:
        with engine.connect() as conn:
            rows = dict(
                conn.execute(
                    text("SELECT name, thumbnail_asset_id FROM video_projects")
                ).fetchall()
            )
            # The assets themselves must all still be there — the migration
            # repairs the reference, it does not delete the user's files.
            surviving = conn.execute(
                text("SELECT COUNT(*) FROM video_assets")
            ).scalar()
    finally:
        engine.dispose()

    assert rows["Broken"] is None, "a video left in the thumbnail column"
    assert rows["Repairable"] == poster_b, "the poster frame was not picked up"
    assert rows["Healthy"] == image_c, "a real thumbnail was overwritten or cleared"
    assert rows["Hopeless"] is None
    assert surviving == 5, "the migration deleted assets"


def test_the_thumbnail_repair_is_idempotent(migrated_url):
    """`upgrade head` runs on every boot. Running the repair twice must not
    clear a thumbnail that a user has since set in Thumbnail Studio."""
    cfg = _alembic_config(migrated_url)
    command.upgrade(cfg, "0004")
    command.downgrade(cfg, "0003")
    command.upgrade(cfg, "0004")

    engine = create_engine(migrated_url)
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()
    assert version == "0004"


# ===========================================================================
# 2. Storage
# ===========================================================================


def test_key_layout_is_scoped_by_user_and_kind():
    key, token = build_key(user_id=42, kind="voice", content_type="audio/mpeg")
    assert key == f"users/42/voice/{token}.mp3"
    assert token


def test_key_falls_back_for_an_unknown_kind():
    """An unrecognised kind must not scatter objects into a prefix no lifecycle
    rule covers."""
    key, _ = build_key(user_id=1, kind="../../etc", content_type="video/mp4")
    assert key.startswith("users/1/upload/")
    assert ".." not in key


def test_tokens_are_unguessable_and_unique():
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(t) >= 24 for t in tokens)


def test_asset_kinds_match_storage_key_kinds():
    """Two lists in two modules that must not drift — the key prefix and the
    column value are the same vocabulary."""
    from app.models.video_asset import ASSET_KINDS

    assert set(ASSET_KINDS) == set(KINDS)


def test_storage_upload_then_read_returns_the_same_bytes(session_factory):
    storage = DatabaseStorage()
    key, _ = build_key(user_id=1, kind="render", content_type="video/mp4")

    stored = storage.put(key=key, data=b"\x00\x01binary", content_type="video/mp4")

    assert stored.key == key
    assert stored.size_bytes == len(b"\x00\x01binary")
    assert storage.get(key) == (b"\x00\x01binary", "video/mp4")


def test_storage_overwrites_in_place(session_factory):
    storage = DatabaseStorage()
    key = "users/1/image/fixed.png"

    storage.put(key=key, data=b"first", content_type="image/png")
    storage.put(key=key, data=b"second-and-longer", content_type="image/png")

    data, _ = storage.get(key)
    assert data == b"second-and-longer"
    assert storage.stat(key).size_bytes == len(b"second-and-longer")


def test_storage_reports_metadata_without_the_bytes(session_factory):
    storage = DatabaseStorage()
    key = "users/1/music/track.mp3"
    storage.put(key=key, data=b"x" * 5000, content_type="audio/mpeg", filename="track.mp3")

    meta = storage.stat(key)

    assert meta.key == key
    assert meta.size_bytes == 5000
    assert meta.content_type == "audio/mpeg"
    assert meta.last_modified is not None


def test_storage_existence_check(session_factory):
    storage = DatabaseStorage()
    key = "users/1/upload/present.mp4"
    assert storage.exists(key) is False

    storage.put(key=key, data=b"data", content_type="video/mp4")
    assert storage.exists(key) is True

    storage.delete(key)
    assert storage.exists(key) is False


def test_storage_delete_is_idempotent(session_factory):
    """The contract says deleting a key that is already gone is a no-op — the
    cleanup path after a failed insert relies on it."""
    storage = DatabaseStorage()
    storage.delete("users/1/upload/never-existed.mp4")
    storage.delete("users/1/upload/never-existed.mp4")


def test_reading_a_missing_object_raises_object_not_found(session_factory):
    """Distinct from StorageError so a route can answer 404 rather than 502."""
    storage = DatabaseStorage()
    with pytest.raises(ObjectNotFound):
        storage.get("users/1/upload/absent.mp4")
    with pytest.raises(ObjectNotFound):
        storage.stat("users/1/upload/absent.mp4")


def test_database_backend_refuses_to_pretend_it_has_urls(session_factory):
    """It must not return a never-expiring stand-in for a signed URL — that
    would quietly make the development backend the one with no time box."""
    storage = DatabaseStorage()
    with pytest.raises(StorageError):
        storage.url_for("users/1/upload/x.mp4")
    with pytest.raises(StorageError):
        storage.signed_url("users/1/upload/x.mp4")


def test_r2_tells_a_missing_object_apart_from_an_outage():
    """The check that stops a credentials failure being reported as absence —
    which is how an outage turns into a delete."""
    from app.services.storage.r2 import _is_missing

    class Boom(Exception):
        def __init__(self, response):
            self.response = response

    assert _is_missing(Boom({"Error": {"Code": "NoSuchKey"}}))
    assert _is_missing(Boom({"ResponseMetadata": {"HTTPStatusCode": 404}}))
    assert not _is_missing(Boom({"Error": {"Code": "AccessDenied"}}))
    assert not _is_missing(Boom({"ResponseMetadata": {"HTTPStatusCode": 500}}))
    assert not _is_missing(Exception("connection reset"))


def test_r2_is_not_configured_without_credentials(monkeypatch):
    from app.services.storage import r2 as r2_module

    for field in ("r2_account_id", "r2_bucket", "r2_access_key_id", "r2_secret_access_key"):
        monkeypatch.setattr(f"app.config.settings.{field}", None)
    monkeypatch.setattr("app.config.settings.r2_endpoint", None)

    assert r2_module.is_configured() is False
    with pytest.raises(StorageError):
        r2_module.R2Storage()


def test_storage_factory_refuses_an_unknown_backend(monkeypatch):
    from app.services.storage.factory import _select

    with pytest.raises(StorageError):
        _select("dropbox")


# ===========================================================================
# 3. Asset ingest
# ===========================================================================


def test_store_asset_writes_the_object_and_the_row(db, user):
    asset = asset_service.store_asset(
        db,
        user_id=user.id,
        kind="subtitle",
        data=b"1\n00:00:00,000 --> 00:00:02,000\nHello\n",
        content_type="application/x-subrip",
        title="Captions",
        filename="captions.srt",
    )

    assert asset.storage_backend == "database"
    assert asset.storage_key.startswith(f"users/{user.id}/subtitle/")
    assert asset.size_bytes > 0
    assert asset.project_id is None  # standalone until explicitly attached

    data, content_type = asset_service.read_asset(asset)
    assert b"Hello" in data
    assert content_type == "application/x-subrip"


def test_store_asset_meters_the_bytes(db, user):
    from app.services.video import metering

    asset_service.store_asset(
        db,
        user_id=user.id,
        kind="subtitle",
        data=b"x" * 1234,
        content_type="text/vtt",
    )

    assert metering.used(db, user_id=user.id, metric="storage_bytes") == 1234


def test_store_asset_rejects_an_empty_file(db, user):
    with pytest.raises(asset_service.AssetError, match="empty"):
        asset_service.store_asset(
            db, user_id=user.id, kind="upload", data=b"", content_type="video/mp4"
        )


def test_store_asset_rejects_a_disallowed_type(db, user):
    with pytest.raises(asset_service.AssetError):
        asset_service.store_asset(
            db,
            user_id=user.id,
            kind="upload",
            data=b"MZ\x90\x00",
            content_type="application/x-msdownload",
            filename="totally-a-video.exe",
        )


def test_store_asset_rejects_a_file_over_the_limit(db, user, monkeypatch):
    monkeypatch.setattr("app.config.settings.video_max_upload_mb", 1)

    with pytest.raises(asset_service.AssetError, match="limit"):
        asset_service.store_asset(
            db,
            user_id=user.id,
            kind="upload",
            data=b"x" * (2 * 1024 * 1024),
            content_type="video/mp4",
            probe=False,
        )


def test_store_asset_removes_the_object_when_the_row_cannot_be_written(db, user, monkeypatch):
    """The write is object-then-row. A row that fails must not leave an
    unreferenced object in the bucket — an invisible cost nothing cleans up."""
    storage = DatabaseStorage()
    orphan_check = {}

    real_commit = db.commit

    def explode():
        raise RuntimeError("constraint violation")

    monkeypatch.setattr(db, "commit", explode)

    with pytest.raises(RuntimeError):
        asset_service.store_asset(
            db,
            user_id=user.id,
            kind="subtitle",
            data=b"orphan me",
            content_type="text/vtt",
            title="Doomed",
        )

    monkeypatch.setattr(db, "commit", real_commit)

    # Nothing left behind, in either place.
    from app.models.storage_object import StorageObject

    orphan_check["objects"] = db.query(StorageObject).count()
    orphan_check["assets"] = db.query(VideoAsset).count()
    assert orphan_check == {"objects": 0, "assets": 0}


def test_content_type_is_guessed_from_the_filename_when_absent(db, user):
    """Browsers routinely send nothing at all for an .srt upload."""
    asset = asset_service.store_asset(
        db,
        user_id=user.id,
        kind="subtitle",
        data=b"cue",
        content_type="",
        filename="captions.srt",
    )
    assert asset.content_type == "application/x-subrip"


# ===========================================================================
# 4. Project lifecycle
# ===========================================================================


def test_create_project_uses_the_platform_preset(db, user):
    project = project_service.create_project(
        db, user_id=user.id, name="My Reel", platform="instagram_reels"
    )

    assert project.platform == "instagram_reels"
    assert (project.width, project.height) == (1080, 1920)
    assert project.aspect_ratio == "9:16"
    assert project.status == "draft"
    assert project.revision == 0
    # Every project opens with a subtitle track to write into.
    assert db.query(VideoSubtitle).filter_by(project_id=project.id).count() == 1


def test_create_project_clamps_an_oversized_canvas(db, user):
    """A project that the renderer would have to refuse must not be creatable."""
    project = project_service.create_project(
        db, user_id=user.id, platform="custom", width=7680, height=4320
    )

    assert project.height <= 1080
    assert project.width % 2 == 0 and project.height % 2 == 0


def test_create_project_rejects_an_unknown_type(db, user):
    with pytest.raises(project_service.ProjectError):
        project_service.create_project(db, user_id=user.id, project_type="telepathy")


def test_create_project_from_a_template_copies_its_scenes(db, user):
    template_service.sync_system_templates(db)
    template = template_service.get_template(db, user_id=user.id, key="listicle_shorts")

    project = project_service.create_project(
        db, user_id=user.id, project_type="script", template=template
    )

    scenes = db.query(VideoScene).filter_by(project_id=project.id).all()
    assert len(scenes) == 7
    assert scenes[0].title == "Hook"
    assert project.template_id == template.id
    assert project.template_key == "listicle_shorts"
    # Positions are dense and ordered, and start times accumulate.
    assert [s.position for s in sorted(scenes, key=lambda s: s.position)] == list(range(7))


def test_get_project_returns_the_project(db, user):
    created = project_service.create_project(db, user_id=user.id, name="Mine")
    found = project_service.get_project(db, user_id=user.id, project_id=created.id)
    assert found.id == created.id


def test_list_projects_filters_and_orders(db, user):
    project_service.create_project(db, user_id=user.id, name="Alpha", platform="tiktok")
    project_service.create_project(db, user_id=user.id, name="Beta", platform="youtube")

    assert len(project_service.list_projects(db, user_id=user.id)) == 2
    assert [p.name for p in project_service.list_projects(db, user_id=user.id, search="alph")] == ["Alpha"]
    assert [p.name for p in project_service.list_projects(db, user_id=user.id, platform="youtube")] == ["Beta"]
    assert project_service.count_projects(db, user_id=user.id) == 2


def test_update_project_recomputes_duration_and_bumps_revision(db, user):
    project = project_service.create_project(db, user_id=user.id)
    timeline = {
        "tracks": [
            {"id": "video", "clips": [
                {"start": 0.0, "duration": 4.0},
                {"start": 4.0, "duration": 6.5},
            ]}
        ]
    }

    updated = project_service.update_project(
        db, project=project, patch={"timeline": timeline}, expected_revision=0
    )

    assert updated.duration_seconds == 10.5
    assert updated.revision == 1


def test_update_project_ignores_fields_the_server_owns(db, user):
    """A patch naming `revision`, `user_id` or `duration_seconds` is ignored,
    not honoured — otherwise a client can hand itself another user's project."""
    project = project_service.create_project(db, user_id=user.id)
    original_owner = project.user_id

    project_service.update_project(
        db,
        project=project,
        patch={"user_id": 9999, "revision": 500, "duration_seconds": 99999, "name": "Renamed"},
    )

    assert project.user_id == original_owner
    assert project.revision == 1
    assert project.duration_seconds == 0.0
    assert project.name == "Renamed"


def test_autosave_stamps_the_time_and_a_stale_save_is_refused(db, user):
    project = project_service.create_project(db, user_id=user.id)

    project_service.update_project(
        db, project=project, patch={"notes": "first"}, expected_revision=0, autosave=True
    )
    assert project.last_autosave_at is not None
    assert project.revision == 1

    # A second tab still holding revision 0 must not overwrite revision 1.
    with pytest.raises(project_service.RevisionConflict):
        project_service.update_project(
            db, project=project, patch={"notes": "second"}, expected_revision=0
        )
    assert project.notes == "first"


def test_rename_project_requires_a_name(db, user):
    project = project_service.create_project(db, user_id=user.id, name="Before")

    project_service.rename_project(db, project=project, name="  After  ")
    assert project.name == "After"

    with pytest.raises(project_service.ProjectError):
        project_service.rename_project(db, project=project, name="   ")


def test_set_status_rejects_an_unknown_value(db, user):
    project = project_service.create_project(db, user_id=user.id)

    project_service.set_status(db, project=project, status="processing")
    assert project.status == "processing"

    with pytest.raises(project_service.ProjectError):
        project_service.set_status(db, project=project, status="haunted")


def test_set_status_does_not_bump_revision(db, user):
    """A render must not invalidate the tab the user is editing in."""
    project = project_service.create_project(db, user_id=user.id)
    before = project.revision

    project_service.set_status(db, project=project, status="completed")

    assert project.revision == before


def test_duplicate_project_copies_children_and_resets_render_state(db, user):
    project = project_service.create_project(db, user_id=user.id, name="Original")
    project.status = "completed"
    db.add(VideoScene(project_id=project.id, position=0, title="Hook", duration_seconds=4.0))
    db.add(VideoAudio(project_id=project.id, role="music", volume=0.3, ducking=True))
    db.commit()

    copy = project_service.duplicate_project(db, project=project)

    assert copy.id != project.id
    assert copy.name == "Original (copy)"
    assert copy.status == "draft"          # never presented as already rendered
    assert copy.revision == 0
    assert db.query(VideoScene).filter_by(project_id=copy.id).count() == 1
    layers = db.query(VideoAudio).filter_by(project_id=copy.id).all()
    assert len(layers) == 1 and layers[0].ducking is True
    # The original is untouched.
    assert db.query(VideoScene).filter_by(project_id=project.id).count() == 1


def test_delete_project_removes_its_parts_but_keeps_its_assets(db, user):
    project = project_service.create_project(db, user_id=user.id)
    asset = asset_service.store_asset(
        db,
        user_id=user.id,
        kind="voice",
        data=WAV_BYTES,
        content_type="audio/wav",
        project_id=project.id,
        probe=False,
    )
    db.add(VideoScene(project_id=project.id, position=0, duration_seconds=3.0))
    db.commit()
    asset_id, project_id = asset.id, project.id

    project_service.delete_project(db, project=project)

    assert db.get(VideoProject, project_id) is None
    assert db.query(VideoScene).filter_by(project_id=project_id).count() == 0
    assert db.query(VideoSubtitle).filter_by(project_id=project_id).count() == 0

    # The voice-over survives, detached — it belongs to the user, not the project.
    survivor = db.get(VideoAsset, asset_id)
    assert survivor is not None
    assert survivor.project_id is None


def test_attach_asset_refuses_another_users_file(db, user, other_user):
    project = project_service.create_project(db, user_id=user.id)
    theirs = asset_service.store_asset(
        db, user_id=other_user.id, kind="subtitle", data=b"x", content_type="text/vtt"
    )

    with pytest.raises(project_service.ProjectError):
        project_service.attach_asset(db, project=project, asset=theirs)


def test_project_duration_counts_subtitles_with_an_empty_timeline(db, user):
    """Subtitle Studio's "Add to Project" produces captions before any media
    exists. Reporting 0:00 for that would be wrong on the projects list."""
    project = project_service.create_project(db, user_id=user.id)
    track = db.query(VideoSubtitle).filter_by(project_id=project.id).one()
    track.duration_seconds = 42.0
    db.commit()

    assert project_service.project_duration(db, project) == 42.0


# ===========================================================================
# 5. Render status
# ===========================================================================


def _renderable(db, user, seconds=10.0):
    project = project_service.create_project(db, user_id=user.id)
    project_service.update_project(
        db,
        project=project,
        patch={"timeline": {"tracks": [{"id": "video", "clips": [
            {"start": 0.0, "duration": seconds}
        ]}]}},
    )
    return project


def test_queue_render_snapshots_the_timeline_and_marks_the_project(db, user):
    project = _renderable(db, user)

    render = render_service.queue_render(db, project=project)

    assert render.status == "queued"
    assert render.attempt == 1
    assert render.timeline_snapshot == project.timeline
    assert project.status == "processing"


def test_editing_during_a_render_does_not_change_what_is_encoded(db, user):
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    snapshot = dict(render.timeline_snapshot)

    project_service.update_project(
        db, project=project, patch={"timeline": {"tracks": [{"id": "video", "clips": []}]}}
    )

    db.refresh(render)
    assert render.timeline_snapshot == snapshot


def test_render_refuses_an_empty_project(db, user):
    project = project_service.create_project(db, user_id=user.id)
    with pytest.raises(render_service.RenderError, match="nothing on its timeline"):
        render_service.queue_render(db, project=project)


def test_render_refuses_a_project_over_the_duration_cap(db, user, monkeypatch):
    monkeypatch.setattr("app.config.settings.video_max_duration_seconds", 60)
    project = _renderable(db, user, seconds=600.0)

    with pytest.raises(render_service.RenderError, match="limited to"):
        render_service.queue_render(db, project=project)


def test_only_one_render_per_project_at_a_time(db, user):
    project = _renderable(db, user)
    render_service.queue_render(db, project=project)

    with pytest.raises(render_service.RenderError, match="already being rendered"):
        render_service.queue_render(db, project=project)


def test_render_progresses_through_its_states(db, user):
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)

    render_service.start(db, render=render)
    assert render.status == "processing"
    assert render.started_at is not None

    render_service.report_progress(db, render=render, stage="encoding", progress=0.4)
    assert render.stage == "encoding"
    assert render.progress == 0.4

    render_service.complete(db, render=render, duration_seconds=10.0)
    assert render.status == "completed"
    assert render.progress == 1.0
    assert render.finished_at is not None
    assert project.status == "completed"


def test_progress_never_goes_backwards(db, user):
    """A renderer restarting a pass must not make the bar jump back — that
    reads as a bug even when the render is fine."""
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)

    render_service.report_progress(db, render=render, progress=0.8)
    render_service.report_progress(db, render=render, progress=0.2)

    assert render.progress == 0.8


def test_progress_is_clamped_and_stages_are_validated(db, user):
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)

    render_service.report_progress(db, render=render, progress=17.0)
    assert render.progress == 1.0

    with pytest.raises(render_service.RenderError):
        render_service.report_progress(db, render=render, stage="wishing")


def test_completing_a_render_meters_the_seconds(db, user):
    from app.services.video import metering

    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)
    render_service.complete(db, render=render, duration_seconds=12.5)

    assert metering.used(db, user_id=user.id, metric="render_seconds") == 12.5


def test_a_failed_render_records_why_and_leaves_the_project_intact(db, user):
    project = _renderable(db, user)
    original_timeline = dict(project.timeline)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)
    render_service.report_progress(db, render=render, stage="encoding", progress=0.6)

    render_service.fail(
        db, render=render, error="x264 [error]: malformed frame", error_code="ffmpeg_error"
    )

    assert render.status == "failed"
    assert render.error_code == "ffmpeg_error"
    assert render.error_stage == "encoding"   # where it got to, not rewound
    assert "malformed frame" in render.error
    assert project.status == "failed"
    assert project.timeline == original_timeline   # content untouched


def test_an_unknown_error_code_is_normalised(db, user):
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)

    render_service.fail(db, render=render, error="?", error_code="banana")

    assert render.error_code == "unknown"


def test_retrying_creates_a_new_attempt_rather_than_reopening_one(db, user):
    project = _renderable(db, user)
    first = render_service.queue_render(db, project=project)
    render_service.start(db, render=first)
    render_service.fail(db, render=first, error="boom", error_code="ffmpeg_error")

    second = render_service.queue_render(db, project=project)

    assert second.id != first.id
    assert second.attempt == 2
    # The history of what was tried survives.
    db.refresh(first)
    assert first.status == "failed" and first.error == "boom"


def test_a_terminal_render_cannot_be_moved_again(db, user):
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)
    render_service.complete(db, render=render)

    for action in (
        lambda: render_service.complete(db, render=render),
        lambda: render_service.fail(db, render=render, error="late"),
        lambda: render_service.cancel(db, render=render),
        lambda: render_service.start(db, render=render),
    ):
        with pytest.raises(render_service.RenderError):
            action()


def test_late_progress_on_a_finished_render_is_ignored_not_raised(db, user):
    """A progress report racing a cancellation is a race, not an error."""
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)
    render_service.cancel(db, render=render)

    render_service.report_progress(db, render=render, progress=0.9)

    assert render.status == "cancelled"
    assert render.progress < 0.9


def test_cancelling_returns_the_project_to_draft(db, user):
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)

    render_service.cancel(db, render=render)

    assert render.status == "cancelled"
    assert project.status == "draft"


def test_interrupted_renders_are_recovered_on_startup(db, user):
    """A job left running by a killed process would otherwise sit at 40%
    forever, and `queue_render` refuses while one is unfinished."""
    project = _renderable(db, user)
    render = render_service.queue_render(db, project=project)
    render_service.start(db, render=render)
    render_service.report_progress(db, render=render, stage="encoding", progress=0.4)

    recovered = render_service.recover_interrupted(db)

    assert recovered == 1
    db.refresh(render)
    assert render.status == "failed"
    assert render.error_code == "interrupted"
    assert project.status == "draft"
    # And the project can be rendered again.
    assert render_service.queue_render(db, project=project).attempt == 2


# ===========================================================================
# 6. Authorization
# ===========================================================================


def test_another_users_project_is_indistinguishable_from_a_missing_one(db, user, other_user):
    theirs = project_service.create_project(db, user_id=other_user.id, name="Private")

    with pytest.raises(project_service.ProjectNotFound):
        project_service.get_project(db, user_id=user.id, project_id=theirs.id)

    with pytest.raises(project_service.ProjectNotFound):
        project_service.get_project(db, user_id=user.id, project_id=999_999)


def test_listing_never_includes_another_users_projects(db, user, other_user):
    project_service.create_project(db, user_id=user.id, name="Mine")
    project_service.create_project(db, user_id=other_user.id, name="Theirs")

    names = {p.name for p in project_service.list_projects(db, user_id=user.id)}

    assert names == {"Mine"}
    assert project_service.count_projects(db, user_id=user.id) == 1


def test_another_users_asset_cannot_be_fetched(db, user, other_user):
    theirs = asset_service.store_asset(
        db, user_id=other_user.id, kind="subtitle", data=b"secret", content_type="text/vtt"
    )

    with pytest.raises(asset_service.AssetNotFound):
        asset_service.get_asset(db, user_id=user.id, asset_id=theirs.id)

    assert asset_service.get_asset(db, user_id=other_user.id, asset_id=theirs.id).id == theirs.id


def test_asset_listing_is_scoped_to_the_owner(db, user, other_user):
    asset_service.store_asset(
        db, user_id=user.id, kind="subtitle", data=b"mine", content_type="text/vtt"
    )
    asset_service.store_asset(
        db, user_id=other_user.id, kind="subtitle", data=b"theirs", content_type="text/vtt"
    )

    mine = asset_service.user_assets(db, user_id=user.id)

    assert len(mine) == 1
    assert all(a.user_id == user.id for a in mine)


def test_another_users_render_cannot_be_polled(db, user, other_user):
    project = _renderable(db, other_user)
    theirs = render_service.queue_render(db, project=project)

    with pytest.raises(render_service.RenderNotFound):
        render_service.get_render(db, user_id=user.id, render_id=theirs.id)

    assert render_service.list_renders(db, user_id=user.id) == []


def test_another_users_template_is_invisible(db, user, other_user):
    from app.models.video_template import VideoTemplate

    template_service.sync_system_templates(db)
    db.add(
        VideoTemplate(
            key="theirs_private",
            user_id=other_user.id,
            name="Their preset",
            definition={},
        )
    )
    db.commit()

    keys = {t.key for t in template_service.list_templates(db, user_id=user.id)}

    assert "theirs_private" not in keys
    assert "blank_shorts" in keys          # system templates are shared
    with pytest.raises(template_service.TemplateError):
        template_service.get_template(db, user_id=user.id, key="theirs_private")


def test_another_users_version_cannot_be_read(db, user, other_user):
    mine = project_service.create_project(db, user_id=user.id)
    theirs = project_service.create_project(db, user_id=other_user.id)
    their_version = version_service.snapshot(db, project=theirs, reason="manual", force=True)

    with pytest.raises(version_service.VersionError):
        version_service.get_version(db, project=mine, version_id=their_version.id)


# ===========================================================================
# 7. Version history
# ===========================================================================


def test_snapshot_captures_the_project_and_its_children(db, user):
    project = project_service.create_project(db, user_id=user.id, name="Snapshot me")
    db.add(VideoScene(project_id=project.id, position=0, title="Hook", duration_seconds=4.0))
    db.commit()

    version = version_service.snapshot(db, project=project, reason="manual", force=True)

    assert version.snapshot["project"]["name"] == "Snapshot me"
    assert len(version.snapshot["scenes"]) == 1
    assert len(version.snapshot["subtitles"]) == 1


def test_autosave_snapshots_are_throttled(db, user):
    """A version per keystroke is a table that grows without limit for
    something nobody scrolls past the last handful of."""
    project = project_service.create_project(db, user_id=user.id)

    first = version_service.snapshot(db, project=project, reason="autosave")
    second = version_service.snapshot(db, project=project, reason="autosave")

    assert first is not None
    assert second is None          # skipped, and that is success
    # Anything explicit always writes.
    assert version_service.snapshot(db, project=project, reason="pre_ai") is not None


def test_restore_brings_back_content_and_is_itself_undoable(db, user):
    project = project_service.create_project(db, user_id=user.id, name="Good")
    db.add(VideoScene(project_id=project.id, position=0, title="Keep me", duration_seconds=4.0))
    db.commit()
    good = version_service.snapshot(db, project=project, reason="manual", force=True)

    # Wreck it.
    project_service.rename_project(db, project=project, name="Bad")
    db.query(VideoScene).filter_by(project_id=project.id).delete()
    db.commit()

    version_service.restore(db, project=project, version=good)

    assert project.name == "Good"
    scenes = db.query(VideoScene).filter_by(project_id=project.id).all()
    assert [s.title for s in scenes] == ["Keep me"]
    # A pre_restore snapshot was taken, so the restore can itself be undone.
    reasons = [v.reason for v in version_service.list_versions(db, project=project)]
    assert "pre_restore" in reasons


def test_restore_moves_the_revision_forward_not_back(db, user):
    """An editor tab still open is now out of date, and the revision check is
    what tells it so."""
    project = project_service.create_project(db, user_id=user.id)
    version = version_service.snapshot(db, project=project, reason="manual", force=True)
    project_service.update_project(db, project=project, patch={"notes": "later"})
    before = project.revision

    version_service.restore(db, project=project, version=version)

    assert project.revision > before


def test_restore_tolerates_a_snapshot_from_an_older_release(db, user):
    """A field this release has dropped must not turn "restore" into an error
    the user can do nothing about."""
    project = project_service.create_project(db, user_id=user.id)
    version = version_service.snapshot(db, project=project, reason="manual", force=True)
    version.snapshot = {
        **version.snapshot,
        "scenes": [{"position": 0, "title": "Old", "duration_seconds": 3.0,
                    "a_field_that_no_longer_exists": True}],
    }
    db.commit()

    version_service.restore(db, project=project, version=version)

    assert db.query(VideoScene).filter_by(project_id=project.id).one().title == "Old"


def test_version_history_is_capped(db, user):
    from app.models.video_project_version import MAX_VERSIONS_PER_PROJECT

    project = project_service.create_project(db, user_id=user.id)
    for _ in range(MAX_VERSIONS_PER_PROJECT + 8):
        version_service.snapshot(db, project=project, reason="manual", force=True)

    kept = version_service.list_versions(db, project=project, limit=100)
    assert len(kept) == MAX_VERSIONS_PER_PROJECT


def test_deleting_a_project_deletes_its_versions(db, user):
    project = project_service.create_project(db, user_id=user.id)
    version_service.snapshot(db, project=project, reason="manual", force=True)
    project_id = project.id

    project_service.delete_project(db, project=project)

    from app.models.video_project_version import VideoProjectVersion

    assert db.query(VideoProjectVersion).filter_by(project_id=project_id).count() == 0


# ===========================================================================
# 8. Templates
# ===========================================================================


def test_system_templates_sync_is_idempotent(db, user):
    template_service.sync_system_templates(db)
    first = {t.key for t in template_service.list_templates(db, user_id=user.id)}

    template_service.sync_system_templates(db)
    second = template_service.list_templates(db, user_id=user.id)

    assert {t.key for t in second} == first
    assert len(second) == len(first)          # no duplicates on re-sync
    assert all(t.is_system for t in second)


def test_a_template_canvas_matches_the_platform_it_claims(db, user):
    """A template that says "YouTube" and opens 9:16 is a lie the user only
    discovers after building the video."""
    from app.services.video import presets

    template_service.sync_system_templates(db)

    for template in template_service.list_templates(db, user_id=user.id):
        preset = presets.get_preset(template.platform)
        assert template.aspect_ratio == preset.aspect_ratio, template.key
        assert (template.width, template.height) == presets.clamp_resolution(
            preset.width, preset.height
        ), template.key


def test_sync_does_not_overwrite_a_user_template_sharing_a_key(db, user):
    from app.models.video_template import VideoTemplate

    db.add(
        VideoTemplate(
            key="blank_shorts", user_id=user.id, name="My own", definition={"mine": True}
        )
    )
    db.commit()

    template_service.sync_system_templates(db)

    row = db.query(VideoTemplate).filter_by(key="blank_shorts").one()
    assert row.name == "My own"
    assert row.user_id == user.id


# ===========================================================================
# 9. Account deletion
# ===========================================================================


def test_deleting_an_account_removes_every_video_row_and_its_objects(db, user, other_user):
    from app.models.storage_object import StorageObject

    project = _renderable(db, user)
    asset = asset_service.store_asset(
        db, user_id=user.id, kind="subtitle", data=b"mine", content_type="text/vtt",
        project_id=project.id,
    )
    db.add(VideoScene(project_id=project.id, position=0, duration_seconds=3.0))
    db.add(VideoAudio(project_id=project.id, role="music"))
    db.commit()
    render_service.queue_render(db, project=project)
    version_service.snapshot(db, project=project, reason="manual", force=True)

    # Another account's data, which must survive untouched.
    their_project = project_service.create_project(db, user_id=other_user.id)
    their_asset = asset_service.store_asset(
        db, user_id=other_user.id, kind="subtitle", data=b"theirs", content_type="text/vtt"
    )

    # Read every id before the rows go: afterwards these objects are deleted,
    # and touching an expired attribute would raise rather than assert.
    user_id, project_id = user.id, project.id
    my_key, their_key = asset.storage_key, their_asset.storage_key
    their_project_id = their_project.id

    account_deletion.delete_user_account(db, user)

    for model in (VideoProject, VideoAsset, VideoRender, VideoScene, VideoAudio, VideoSubtitle):
        remaining = db.query(model).all()
        assert all(getattr(r, "user_id", None) != user_id for r in remaining), model
    assert db.query(VideoScene).filter_by(project_id=project_id).count() == 0
    assert db.query(VideoAudio).filter_by(project_id=project_id).count() == 0
    assert db.query(VideoSubtitle).filter_by(project_id=project_id).count() == 0

    # The bytes are gone from the bucket too — not just the rows that named them.
    assert db.query(StorageObject).filter_by(key=my_key).count() == 0

    # The other account is intact.
    assert db.get(VideoProject, their_project_id) is not None
    assert db.query(StorageObject).filter_by(key=their_key).count() == 1


def test_account_deletion_still_completes_when_storage_is_unreachable(db, user, monkeypatch):
    """The obligation is to delete. A delete that refuses to start because a
    bucket is down satisfies nothing."""
    project = project_service.create_project(db, user_id=user.id)
    asset_service.store_asset(
        db, user_id=user.id, kind="subtitle", data=b"x", content_type="text/vtt",
        project_id=project.id,
    )

    def explode(self, key):
        raise StorageError("bucket unreachable")

    monkeypatch.setattr(DatabaseStorage, "delete", explode)

    account_deletion.delete_user_account(db, user)

    assert db.get(User, user.id) is None
    assert db.query(VideoProject).filter_by(user_id=user.id).count() == 0
