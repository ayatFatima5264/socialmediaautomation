"""Data access for connected social accounts, scoped to a user.

Every method takes the owning user id so a user can only ever read or mutate
their own rows — the multi-tenancy boundary is enforced here, not left to
callers to remember.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.social_account import SocialAccount
from app.schemas.post import Platform


class SocialAccountRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(self, user_id: int) -> list[SocialAccount]:
        return list(
            self.db.scalars(
                select(SocialAccount)
                .where(SocialAccount.user_id == user_id)
                .order_by(SocialAccount.platform)
            ).all()
        )

    def get(self, user_id: int, platform: Platform) -> SocialAccount | None:
        return self.db.scalars(
            select(SocialAccount).where(
                SocialAccount.user_id == user_id,
                SocialAccount.platform == platform.value,
            )
        ).first()

    def exists(self, user_id: int, platform: Platform) -> bool:
        return self.get(user_id, platform) is not None

    def add(self, account: SocialAccount) -> SocialAccount:
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def save(self, account: SocialAccount) -> SocialAccount:
        self.db.commit()
        self.db.refresh(account)
        return account

    def delete(self, account: SocialAccount) -> None:
        self.db.delete(account)
        self.db.commit()
