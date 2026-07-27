"""Errors for the saiife-cloud seam.

`NotWiredError` mirrors saiife-cloud's own deferred-transport pattern
(`packages/shared/src/errors.ts`): the transport CONSTRUCTS at startup, but any
real call raises this loud, legible error until the cloud admin API lands.
"""
from __future__ import annotations


class NotWiredError(Exception):
    transport: str

    def __init__(self, transport: str) -> None:
        super().__init__(
            f"{transport} is not wired yet — saiife-cloud does not implement the admin "
            f"API this repo specifies (see docs/2026-07-21-saiife-cloud-admin-api-contract.md). "
            f"This transport is deferred behind its seam; the offline core runs against the "
            f"in-memory mock."
        )
        self.transport = transport


class CloudError(Exception):
    """A structured failure returned by the cloud admin API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
