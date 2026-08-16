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

from sqlalchemy import delete, inspect
from sqlalchemy.orm import Session

from app.models.ad_campaign import AdCampaign
from app.models.business_profile import BusinessProfile
from app.models.campaign_asset import CampaignAsset
from app.models.content_plan import ContentPlan, PlannerSettings
from app.models.media_asset import MediaAsset
from app.models.pending_connection import PendingConnection
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.user import User

logger = logging.getLogger(__name__)

# Child tables first: campaign assets reference campaigns, posts reference
# content plans. Deleting a parent first would trip the foreign key on Postgres,
# which does enforce them.
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


def user_owned_tables() -> set[str]:
    """Table names this module deletes from. Used by the coverage test."""
    return {model.__tablename__ for model in _USER_OWNED}


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
