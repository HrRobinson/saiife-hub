"""Hashing is pinned by saiife-cloud/packages/control-api/src/auth.ts.

The golden vector below was produced with BOTH Python's hashlib.scrypt and Node's
crypto.scryptSync and is byte-identical in each. If it fails, cloud will reject
every token hub issues.
"""
import base64
import hashlib

import pytest

from app.tenants import tokens

# pepper="test-pepper", secret="s3cret", salt = 16 bytes of 0x07
GOLDEN = (
    "scrypt$16384$8$1$BwcHBwcHBwcHBwcHBwcHBw==$"
    "mxQuZODDRxgYwpXcqbCDE3nCvTiE47xP78i9l3YCC5k="
)


def test_scrypt_parameters_match_cloud() -> None:
    assert tokens.SCRYPT_N == 16384
    assert tokens.SCRYPT_R == 8
    assert tokens.SCRYPT_P == 1
    assert tokens.KEY_LEN == 32
    assert tokens.SALT_LEN == 16
    assert tokens.DUMMY_SALT == bytes([7]) * 16


def test_golden_vector_matches_node_scrypt_byte_for_byte() -> None:
    got = tokens.hash_account_secret("s3cret", "test-pepper", salt=bytes([7]) * 16)
    assert got == GOLDEN


def test_stored_format_is_self_describing() -> None:
    stored = tokens.hash_account_secret("anything", "pep")
    parts = stored.split("$")
    assert parts[0] == "scrypt"
    assert parts[1:4] == ["16384", "8", "1"]
    assert len(base64.b64decode(parts[4])) == 16
    assert len(base64.b64decode(parts[5])) == 32


def test_password_side_is_pepper_colon_secret() -> None:
    """Cloud hashes `${pepper}:${secret}` — the colon is part of the contract."""
    salt = bytes(range(16))
    expected = hashlib.scrypt(
        b"pep:s3cret", salt=salt, n=16384, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024
    )
    stored = tokens.hash_account_secret("s3cret", "pep", salt=salt)
    assert stored.split("$")[5] == base64.b64encode(expected).decode()


def test_salt_is_random_per_call() -> None:
    a = tokens.hash_account_secret("same", "pep")
    b = tokens.hash_account_secret("same", "pep")
    assert a != b


def test_verify_accepts_the_right_secret() -> None:
    stored = tokens.hash_account_secret("s3cret", "pep")
    assert tokens.verify_account_secret("s3cret", "pep", stored) is True


def test_verify_rejects_the_wrong_secret() -> None:
    stored = tokens.hash_account_secret("s3cret", "pep")
    assert tokens.verify_account_secret("wrong", "pep", stored) is False


def test_verify_rejects_the_wrong_pepper() -> None:
    """A leak of the hash store alone must not yield usable tokens."""
    stored = tokens.hash_account_secret("s3cret", "pep")
    assert tokens.verify_account_secret("s3cret", "other-pepper", stored) is False


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "garbage",
        "argon2id$16384$8$1$c2FsdA==$aGFzaA==",
        "scrypt$16384$8$1$c2FsdA==",
        "scrypt$16384$8$1$c2FsdA==$aGFzaA==$extra",
    ],
)
def test_verify_rejects_malformed_stored_hashes_without_raising(stored: str) -> None:
    assert tokens.verify_account_secret("s3cret", "pep", stored) is False


def test_verify_rejects_a_hash_of_the_wrong_length() -> None:
    short = "scrypt$16384$8$1$" + base64.b64encode(bytes(16)).decode() + "$" + \
        base64.b64encode(bytes(8)).decode()
    assert tokens.verify_account_secret("s3cret", "pep", short) is False


def test_equalize_timing_does_real_scrypt_work_and_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unknown-lookup-id path must still burn a scrypt so it is not a timing
    oracle for 'does this tenant exist'.

    Regression guard: a stub `equalize_timing` that just `return`s None without
    doing any scrypt work would previously satisfy this test's only assertion
    (the return value). Spying on hashlib.scrypt makes that regression fail.
    """
    real_scrypt = hashlib.scrypt
    calls: list[tuple[bytes, bytes]] = []

    def spy_scrypt(password: bytes, *, salt: bytes, **kwargs: object) -> bytes:
        calls.append((password, salt))
        return real_scrypt(password, salt=salt, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(hashlib, "scrypt", spy_scrypt)

    assert tokens.equalize_timing("s3cret", "pep") is None
    assert calls == [(b"pep:s3cret", tokens.DUMMY_SALT)]
