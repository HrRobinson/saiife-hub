from app.auth.passkeys import detect_clone


def test_detect_clone_returns_false_for_increment() -> None:
    assert detect_clone(stored=5, new=6) is False


def test_detect_clone_returns_true_for_decrement() -> None:
    assert detect_clone(stored=5, new=4) is True


def test_detect_clone_returns_true_for_equal_count() -> None:
    """An equal sign_count means the authenticator failed to increment —
    treat as clone evidence per WebAuthn 6.1.1."""
    assert detect_clone(stored=5, new=5) is True


def test_detect_clone_returns_false_when_stored_and_new_are_zero() -> None:
    """A freshly registered passkey has stored=0; some authenticators also
    report 0 on first login. Treat (0, 0) as legitimate first use."""
    assert detect_clone(stored=0, new=0) is False
