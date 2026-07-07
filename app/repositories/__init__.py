"""Repository layer — all social-account persistence lives behind this API.

Keeping SQLAlchemy queries in one place lets the services and routes stay free
of ORM details and makes the data access easy to test or swap.
"""
from app.repositories.social_account_repository import SocialAccountRepository

__all__ = ["SocialAccountRepository"]
