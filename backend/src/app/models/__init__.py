"""Importing this package registers every table on `Base.metadata`."""

from . import billing, install, tenant, user  # noqa: F401

__all__ = ["billing", "install", "tenant", "user"]
