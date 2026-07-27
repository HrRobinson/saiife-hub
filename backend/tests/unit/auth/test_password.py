from app.auth import password


def test_hash_and_verify_roundtrip() -> None:
    h = password.hash_password("hunter2-correct-horse-battery")
    assert password.verify_password(h, "hunter2-correct-horse-battery") is True


def test_verify_rejects_wrong_password() -> None:
    h = password.hash_password("hunter2-correct-horse-battery")
    assert password.verify_password(h, "wrong-password-attempt") is False


def test_hash_uses_security_enhanced_params() -> None:
    """OWASP security-enhanced floor: m >= 64 MiB, t >= 3, p = 1.

    argon2-cffi encodes params in the hash string, so we read them back.
    """
    h = password.hash_password("anything")
    assert "argon2id" in h
    assert "m=65536" in h
    assert "t=3" in h
    assert "p=1" in h


def test_needs_rehash_returns_false_for_current_params() -> None:
    h = password.hash_password("anything")
    assert password.needs_rehash(h) is False


def test_verify_returns_false_for_garbage_hash() -> None:
    assert password.verify_password("not-a-valid-hash", "any-password") is False
