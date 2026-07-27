import uuid
from datetime import datetime, timezone

from app.auth import oauth_google
from app.models.user import OAuthAccount, User


def _user(email: str, verified: bool = True) -> User:
    u = User(id=uuid.uuid4(), email=email, password_hash=None)
    if verified:
        u.email_verified_at = datetime.now(timezone.utc)
    return u


def test_match_returns_login_for_existing_oauth_account() -> None:
    user = _user("alice@example.com")
    existing = OAuthAccount(
        id=uuid.uuid4(), user_id=user.id, provider="google",
        provider_sub="g-123", email="alice@example.com",
    )
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="alice@example.com", google_email_verified=True,
        existing_oauth=existing, existing_user_by_email=user,
    )
    assert decision.action == "log_in_existing"
    assert decision.user_id == user.id


def test_match_links_to_verified_user_with_same_email() -> None:
    user = _user("alice@example.com", verified=True)
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="alice@example.com", google_email_verified=True,
        existing_oauth=None, existing_user_by_email=user,
    )
    assert decision.action == "link_and_log_in"
    assert decision.user_id == user.id


def test_match_refuses_to_link_to_unverified_user() -> None:
    user = _user("alice@example.com", verified=False)
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="alice@example.com", google_email_verified=True,
        existing_oauth=None, existing_user_by_email=user,
    )
    assert decision.action == "reject_unverified_conflict"


def test_match_creates_new_user_when_no_match() -> None:
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="new@example.com", google_email_verified=True,
        existing_oauth=None, existing_user_by_email=None,
    )
    assert decision.action == "create_new"


def test_match_rejects_unverified_google_email() -> None:
    decision = oauth_google.classify_match(
        google_sub="g-123", google_email="x@example.com", google_email_verified=False,
        existing_oauth=None, existing_user_by_email=None,
    )
    assert decision.action == "reject_google_unverified"
