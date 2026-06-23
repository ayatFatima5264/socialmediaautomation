"""Import all models so they register on Base.metadata."""
from app.models.post import Post
from app.models.user import User

__all__ = ["User", "Post"]
