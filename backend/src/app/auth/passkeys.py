from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    UserVerificationRequirement,
)

from ..core.config import settings


def detect_clone(*, stored: int, new: int) -> bool:
    """True if the authenticator's sign_count looks cloned."""
    if stored == 0 and new == 0:
        return False
    return new <= stored


def make_registration_options(
    *, user_id: uuid.UUID, user_email: str, excluded_credential_ids: list[bytes]
) -> tuple[bytes, str]:
    """Returns (challenge_bytes, options_json)."""
    options = generate_registration_options(
        rp_id=settings.PASSKEY_RP_ID,
        rp_name=settings.PASSKEY_RP_NAME,
        user_id=str(user_id).encode(),
        user_name=user_email,
        user_display_name=user_email,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=cid, type=PublicKeyCredentialType.PUBLIC_KEY)
            for cid in excluded_credential_ids
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )
    return options.challenge, options_to_json(options)


def verify_registration(*, challenge: bytes, response_json: str) -> dict[str, Any]:
    return verify_registration_response(
        credential=response_json,
        expected_challenge=challenge,
        expected_origin=settings.PASSKEY_ORIGIN,
        expected_rp_id=settings.PASSKEY_RP_ID,
    ).__dict__


def make_authentication_options(*, allow_credential_ids: list[bytes]) -> tuple[bytes, str]:
    options = generate_authentication_options(
        rp_id=settings.PASSKEY_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=cid, type=PublicKeyCredentialType.PUBLIC_KEY)
            for cid in allow_credential_ids
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options.challenge, options_to_json(options)


def verify_authentication(
    *, challenge: bytes, response_json: str, public_key: bytes, stored_sign_count: int
) -> dict[str, Any]:
    return verify_authentication_response(
        credential=response_json,
        expected_challenge=challenge,
        expected_origin=settings.PASSKEY_ORIGIN,
        expected_rp_id=settings.PASSKEY_RP_ID,
        credential_public_key=public_key,
        credential_current_sign_count=stored_sign_count,
    ).__dict__


def challenge_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=5)
