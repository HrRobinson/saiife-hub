from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal, Optional, cast

from authlib.integrations.httpx_client import AsyncOAuth2Client

from ..core.config import settings
from ..models.user import OAuthAccount, User

_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

Action = Literal[
    "log_in_existing",
    "link_and_log_in",
    "create_new",
    "reject_unverified_conflict",
    "reject_google_unverified",
]


@dataclass(frozen=True)
class MatchDecision:
    action: Action
    user_id: Optional[uuid.UUID] = None


def classify_match(
    *,
    google_sub: str,
    google_email: str,
    google_email_verified: bool,
    existing_oauth: Optional[OAuthAccount],
    existing_user_by_email: Optional[User],
) -> MatchDecision:
    if not google_email_verified:
        return MatchDecision("reject_google_unverified")
    if existing_oauth is not None:
        return MatchDecision("log_in_existing", user_id=existing_oauth.user_id)
    if existing_user_by_email is not None:
        if existing_user_by_email.email_verified_at is None:
            return MatchDecision("reject_unverified_conflict")
        return MatchDecision("link_and_log_in", user_id=existing_user_by_email.id)
    return MatchDecision("create_new")


def build_client(*, redirect_uri: Optional[str] = None) -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scope="openid email profile",
        redirect_uri=redirect_uri or settings.GOOGLE_OAUTH_REDIRECT_URI,
        code_challenge_method="S256",
    )


async def exchange_code(
    client: AsyncOAuth2Client, code: str, code_verifier: str
) -> dict[str, Any]:
    token = await client.fetch_token(_GOOGLE_TOKEN, code=code, code_verifier=code_verifier)
    return cast(dict[str, Any], token)


async def fetch_userinfo(client: AsyncOAuth2Client, access_token: str) -> dict[str, Any]:
    r = await client.get(
        _GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access_token}"}
    )
    r.raise_for_status()
    return cast(dict[str, Any], r.json())


GOOGLE_AUTH_URL = _GOOGLE_AUTH
