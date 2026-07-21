from __future__ import annotations

import uuid

import pytest

from app.auth import jwt as ajwt


def test_issue_and_verify_access_token() -> None:
    uid = uuid.uuid4()
    token = ajwt.issue_access(uid, "alice@example.com")
    claims = ajwt.verify_access(token)
    assert claims.sub == uid
    assert claims.email == "alice@example.com"
    assert claims.type == "access"


def test_issue_and_verify_refresh_token() -> None:
    uid = uuid.uuid4()
    sid = uuid.uuid4()
    token, jti = ajwt.issue_refresh(uid, sid)
    claims = ajwt.verify_refresh(token)
    assert claims.sub == uid
    assert claims.jti == jti
    assert claims.type == "refresh"


def test_verify_access_rejects_refresh_token() -> None:
    refresh, _ = ajwt.issue_refresh(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(ajwt.InvalidTokenType):
        ajwt.verify_access(refresh)


def test_verify_refresh_rejects_access_token() -> None:
    access = ajwt.issue_access(uuid.uuid4(), "alice@example.com")
    with pytest.raises(ajwt.InvalidTokenType):
        ajwt.verify_refresh(access)


def test_verify_rejects_garbage() -> None:
    with pytest.raises(ajwt.InvalidToken):
        ajwt.verify_access("not.a.real.jwt")


def test_verify_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A token issued in the past must fail verification once exp has elapsed."""
    real_now = ajwt._now
    monkeypatch.setattr(ajwt, "_now", lambda: real_now() - 3600)
    token = ajwt.issue_access(uuid.uuid4(), "alice@example.com")
    monkeypatch.setattr(ajwt, "_now", real_now)
    with pytest.raises(ajwt.InvalidToken):
        ajwt.verify_access(token)
