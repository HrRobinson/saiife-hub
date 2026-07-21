"""Importing this package registers every table on `Base.metadata`."""

from . import user  # noqa: F401

__all__ = ["user"]
