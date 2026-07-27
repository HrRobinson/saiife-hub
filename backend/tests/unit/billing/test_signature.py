"""Stripe's `Stripe-Signature` scheme: t=<unix>,v1=<hex hmac-sha256 of "t.payload">.

The golden signature below was computed with the same HMAC Stripe uses.
"""
import hashlib
import hmac

import pytest

from app.billing.signature import SignatureError, verify_stripe_signature

PAYLOAD = b'{"id":"evt_test_1","type":"checkout.session.completed"}'
SECRET = "whsec_test_secret"
TS = 1750000000
GOLDEN_HEADER = (
    "t=1750000000,"
    "v1=038b44452344cb66f6b4328b0ef62957e8fbc2dd84284365b2cbe32d49d81305"
)


def _sign(payload: bytes, secret: str, ts: int) -> str:
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


def test_accepts_a_valid_signature() -> None:
    verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, SECRET, now=TS)


def test_golden_header_matches_a_freshly_computed_one() -> None:
    assert _sign(PAYLOAD, SECRET, TS) == GOLDEN_HEADER


def test_rejects_a_missing_header() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, None, SECRET, now=TS)
    assert exc.value.reason == "missing_signature_header"


def test_rejects_a_malformed_header() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, "not-a-signature", SECRET, now=TS)
    assert exc.value.reason == "malformed_signature_header"


def test_rejects_a_tampered_payload() -> None:
    tampered = PAYLOAD.replace(b"evt_test_1", b"evt_test_2")
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(tampered, GOLDEN_HEADER, SECRET, now=TS)
    assert exc.value.reason == "signature_mismatch"


def test_rejects_the_wrong_secret() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, "whsec_other", now=TS)
    assert exc.value.reason == "signature_mismatch"


def test_rejects_a_stale_timestamp_outside_the_tolerance() -> None:
    """Replay defence: an old, otherwise-valid signature is refused."""
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, SECRET, tolerance_seconds=300, now=TS + 301)
    assert exc.value.reason == "timestamp_outside_tolerance"


def test_rejects_a_future_timestamp_outside_the_tolerance() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, SECRET, tolerance_seconds=300, now=TS - 301)
    assert exc.value.reason == "timestamp_outside_tolerance"


def test_accepts_a_timestamp_at_the_edge_of_the_tolerance() -> None:
    verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, SECRET, tolerance_seconds=300, now=TS + 300)


def test_accepts_a_header_carrying_multiple_v1_signatures() -> None:
    """Stripe sends several v1 values during secret rotation; any match is valid."""
    header = GOLDEN_HEADER + ",v1=" + "0" * 64
    verify_stripe_signature(PAYLOAD, header, SECRET, now=TS)


def test_rejects_a_header_with_only_unknown_schemes() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, f"t={TS},v0=deadbeef", SECRET, now=TS)
    assert exc.value.reason == "malformed_signature_header"


def test_rejects_an_empty_secret() -> None:
    with pytest.raises(SignatureError) as exc:
        verify_stripe_signature(PAYLOAD, GOLDEN_HEADER, "", now=TS)
    assert exc.value.reason == "webhook_secret_not_configured"
