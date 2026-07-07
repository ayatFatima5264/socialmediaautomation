"""Social Accounts module — per-platform OAuth connect/refresh services.

Public surface:
  * registry.get_provider(...) / registry.PROVIDERS — resolve a platform's
    OAuth adapter.
  * service — orchestration used by the routes (start connect, handle the
    OAuth callback, refresh, disconnect).

Each platform is a small subclass of `base.OAuthProvider`; adding a new one is
a single new file plus a registry entry — no route or UI changes needed.
"""
from __future__ import annotations

from app.services.social_accounts import service
from app.services.social_accounts.registry import PROVIDERS, get_provider

__all__ = ["PROVIDERS", "get_provider", "service"]
