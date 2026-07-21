"""Chooses the live or mock control plane and exposes it as a FastAPI dependency."""
from __future__ import annotations

from ..core.config import settings
from .http import HttpCloudControlPlane
from .mock import InMemoryCloudControlPlane
from .seam import CloudControlPlane

_cloud: CloudControlPlane = InMemoryCloudControlPlane()


def get_cloud() -> CloudControlPlane:
    return _cloud


def set_cloud(c: CloudControlPlane) -> None:
    global _cloud
    _cloud = c


def configure_default_cloud() -> None:
    """No admin URL configured => the in-memory mock. This is what makes the
    whole repo buildable and testable with no GCP account and no network."""
    if settings.CLOUD_ADMIN_API_URL:
        set_cloud(
            HttpCloudControlPlane(settings.CLOUD_ADMIN_API_URL, settings.CLOUD_ADMIN_API_KEY)
        )
    else:
        set_cloud(InMemoryCloudControlPlane())
