"""Stripe webhook signature verification.

Implemented here rather than via the SDK so it is deterministic, offline-testable,
and pinned: NO state changes until this passes. Stripe's scheme is
`Stripe-Signature: t=<unix>,v1=<hex>` where the MAC is HMAC-SHA256 over the exact
bytes `f"{t}.".encode() + raw_body` — the RAW body, never a re-serialized dict.
"""
from __future__ import annotations

import hashlib
import hmac
import time


class SignatureError(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


def _parse_header(header: str) -> tuple[int | None, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                return None, []
        elif key == "v1" and value:
            signatures.append(value)
    return timestamp, signatures


def verify_stripe_signature(
    payload: bytes,
    header: str | None,
    secret: str,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> None:
    """Raise `SignatureError` unless `header` authenticates `payload`."""
    if not secret:
        raise SignatureError(
            "webhook_secret_not_configured", "no Stripe webhook secret is configured"
        )
    if not header:
        raise SignatureError("missing_signature_header", "no Stripe-Signature header")

    timestamp, signatures = _parse_header(header)
    if timestamp is None or not signatures:
        raise SignatureError(
            "malformed_signature_header", "header carried no usable t/v1 pair"
        )

    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance_seconds:
        raise SignatureError(
            "timestamp_outside_tolerance",
            f"signature timestamp is {abs(current - timestamp)}s away from now",
        )

    expected = hmac.new(
        secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise SignatureError("signature_mismatch", "no v1 signature matched the payload")
