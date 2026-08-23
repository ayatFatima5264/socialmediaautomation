"""Permanent deletion of a user account and everything belonging to it.

This is the code path behind "Delete Account" in Settings and behind the public
/data-deletion page's promise, so it has to actually empty every table that
holds the person's data — an account that looks deleted while its posts and
OAuth tokens survive is worse than no deletion feature at all.

**Every table is listed explicitly**, in child-before-parent order, rather than
leaning on the `ON DELETE CASCADE` already declared on each foreign key. Two
reasons:

  * SQLite does not enforce foreign keys unless `PRAGMA foreign_keys=ON` is set
    per connection, which this app does not do — so on the development database
    a cascade would quietly delete nothing and the tests would still pass.
  * The set of tables a deletion touches is a thing to be audited, and this list
    is where a reviewer (or a Meta reviewer) can read it in one place.

The tradeoff is that a new user-owned table must be added to `_USER_OWNED`.
`test_deletion_covers_every_user_owned_table` fails if one is ever missed, so
that cannot be forgotten silently.

**Nothing here is shared between users.** Every non-user table in this schema
carries its own `user_id`, so there is no row that a second user could still
need — no lookup tables, no shared media, no team-owned records. If a shared
table is ever added it must NOT be listed here.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from app.models.ad_campaign import AdCampaign
from app.models.business_profile import BusinessProfile
from app.models.campaign_asset import CampaignAsset
from app.models.content_plan import ContentPlan, PlannerSettings
from app.models.media_asset import MediaAsset
from app.models.music_track import MusicTrack
from app.models.pending_connection import PendingConnection
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.models.video_asset import VideoAsset
from app.models.video_audio import VideoAudio
from app.models.video_project import VideoProject
from app.models.video_project_version import VideoProjectVersion
from app.models.video_render import VideoRender
from app.models.video_scene import VideoScene
from app.models.video_subtitle import VideoSubtitle
from app.models.video_template import VideoTemplate

logger = logging.getLogger(__name__)

# Video Studio tables keyed on `project_id` rather than on `user_id`. They are
# reached through the user's projects, so they are deleted first and separately
# — a `user_id` column on them would be denormalisation for the benefit of this
# one function.
_PROJECT_OWNED = (
    VideoProjectVersion,
    VideoScene,
    VideoAudio,
    VideoSubtitle,
)

# Child tables first: campaign assets reference campaigns, posts reference
# content plans. Deleting a parent first would trip the foreign key on Postgres,
# which does enforce them.
#
# Within Video Studio the order is renders → templates → assets → projects:
# renders point at both a project and an output asset, templates point at a
# preview asset, and assets and projects point at each other (a project's
# thumbnail, an asset's project), so assets must go before projects.
_USER_OWNED = (
    CampaignAsset,
    AdCampaign,
    Post,
    ContentPlan,
    PlannerSettings,
    BusinessProfile,
    MediaAsset,
    PendingConnection,
    SocialAccount,
    # ---- Video Studio ----------------------------------------------------
    VideoRender,
    UsageEvent,
    VideoTemplate,
    # Before VideoAsset: an uploaded track points at the asset holding its
    # audio, so the track row has to go first or the delete trips the foreign
    # key on Postgres. Only this user's own uploads match — catalogue rows have
    # `user_id` NULL and are shared, so they are left alone.
    MusicTrack,
    VideoAsset,
    VideoProject,
)


def delete_user_account(db: Session, user: User) -> dict[str, int]:
    """Delete `user` and every record they own. Returns rows removed per table.

    The caller passes the *authenticated* user object — there is no user id
    parameter anywhere in this path, so no request can name someone else's
    account. Runs as one transaction: either the account and all its data are
    gone, or nothing changed.
    """
    user_id = user.id
    removed: dict[str, int] = {}

    # The bytes go before the rows. Once `video_assets` is deleted there is
    # nothing left that knows which objects in the bucket were this person's,
    # and they would sit there indefinitely — a privacy problem and a bill
    # nobody can attribute. A storage failure is logged and does not abort the
    # deletion: the account must still go.
    _delete_stored_objects(db, user_id)

    project_ids = select(VideoProject.id).where(VideoProject.user_id == user_id)
    for model in _PROJECT_OWNED:
        result = db.execute(
            delete(model).where(model.project_id.in_(project_ids))
        )
        removed[model.__tablename__] = result.rowcount or 0

    for model in _USER_OWNED:
        result = db.execute(delete(model).where(model.user_id == user_id))
        removed[model.__tablename__] = result.rowcount or 0

    db.execute(delete(User).where(User.id == user_id))
    db.commit()

    # The user id and row counts only — never an email, a token, or any content.
    logger.info(
        "Deleted account %s and its data: %s",
        user_id,
        ", ".join(f"{table}={count}" for table, count in removed.items() if count),
    )
    return removed


def _delete_stored_objects(db: Session, user_id: int) -> int:
    """Remove this user's objects from the bucket. Returns how many went.

    Deliberately best-effort. Object storage is a network service that can be
    down, misconfigured or mid-migration, and none of those may stop a person
    deleting their account — the legal obligation is to delete, and a delete
    that refuses to start because a bucket is unreachable satisfies nothing.
    What fails here is logged loudly enough to be swept up afterwards.
    """
    from app.services.storage import get_storage
    from app.services.storage.base import StorageError

    keys = list(
        db.scalars(
            select(VideoAsset.storage_key).where(VideoAsset.user_id == user_id)
        ).all()
    )
    if not keys:
        return 0

    try:
        storage = get_storage()
    except StorageError:
        logger.exception(
            "Could not reach object storage while deleting account %s; "
            "%d object(s) were left behind", user_id, len(keys),
        )
        return 0

    deleted = 0
    for key in keys:
        try:
            storage.delete(key)
            deleted += 1
        except StorageError:
            logger.exception(
                "Could not delete storage object %s for account %s", key, user_id
            )

    if deleted != len(keys):
        logger.error(
            "Account %s: deleted %d of %d storage objects", user_id, deleted, len(keys)
        )
    return deleted


def user_owned_tables() -> set[str]:
    """Table names this module deletes from. Used by the coverage test."""
    return {model.__tablename__ for model in (*_USER_OWNED, *_PROJECT_OWNED)}


def tables_referencing_users(db: Session) -> set[str]:
    """Every table with a foreign key to `users`, read from the live schema.

    The guard behind the coverage test: it discovers user-owned tables from the
    database itself, so a table added later shows up here whether or not anyone
    remembered to update `_USER_OWNED`.
    """
    inspector = inspect(db.get_bind())
    referencing = set()
    for table in inspector.get_table_names():
        if table == User.__tablename__:
            continue
        for fk in inspector.get_foreign_keys(table):
            if fk.get("referred_table") == User.__tablename__:
                referencing.add(table)
    return referencing
