"""Import all models so they register on Base.metadata."""
from app.models.ad_campaign import AdCampaign
from app.models.business_profile import BusinessProfile
from app.models.campaign_asset import CampaignAsset
from app.models.contact_message import ContactMessage
from app.models.content_plan import ContentPlan, PlannerSettings
from app.models.media_asset import MediaAsset
from app.models.music_track import MusicTrack
from app.models.pending_connection import PendingConnection
from app.models.post import Post
from app.models.social_account import SocialAccount
from app.models.storage_object import StorageObject
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

__all__ = [
    "User",
    "AdCampaign",
    "CampaignAsset",
    "Post",
    "SocialAccount",
    "MediaAsset",
    "PendingConnection",
    "BusinessProfile",
    "ContentPlan",
    "PlannerSettings",
    "ContactMessage",
    # ---- Video Studio ----------------------------------------------------
    # These tables are created by Alembic, not by create_all — see the
    # `alembic_only` note in app/database.py. They still have to be imported
    # here so autogenerate can see them.
    "StorageObject",
    "VideoTemplate",
    "VideoProject",
    "VideoAsset",
    "VideoScene",
    "VideoAudio",
    "VideoSubtitle",
    "VideoRender",
    "VideoProjectVersion",
    "MusicTrack",
    "UsageEvent",
]
