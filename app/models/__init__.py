"""Import all models so they register on Base.metadata."""
from app.models.ad_campaign import AdCampaign
from app.models.business_profile import BusinessProfile
from app.models.content_plan import ContentPlan, PlannerSettings
from app.models.pending_connection import PendingConnection
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.user import User

__all__ = [
    "User",
    "AdCampaign",
    "Post",
    "SocialAccount",
    "PendingConnection",
    "BusinessProfile",
    "ContentPlan",
    "PlannerSettings",
]
