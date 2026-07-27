"""The token format is pinned by saiife-cloud/packages/shared/src/ids.ts.

Every assertion here mirrors a behaviour of `generateAccountToken` /
`parseAccountToken` in that file. If one fails, hub and cloud have diverged and
cloud will reject hub-issued tokens.
"""
import base64
import re

from app.tenants.tokens import (
    ACCOUNT_TOKEN_PREFIX,
    generate_account_token,
    new_tenant_lookup_id,
    parse_account_token,
)


def test_prefix_is_sfc_underscore() -> None:
    assert ACCOUNT_TOKEN_PREFIX == "sfc_"


def test_lookup_id_is_18_lowercase_hex_chars_and_never_contains_underscore() -> None:
    """Cloud splits on the FIRST '_'; hex guarantees that split is unambiguous."""
    for _ in range(20):
        lookup = new_tenant_lookup_id()
        assert re.fullmatch(r"[0-9a-f]{18}", lookup), lookup


def test_generated_token_is_prefix_lookup_underscore_secret() -> None:
    gen = generate_account_token()
    assert gen.token == f"sfc_{gen.tenant_lookup_id}_{gen.secret}"


def test_secret_is_32_random_bytes_base64url_without_padding() -> None:
    gen = generate_account_token()
    assert "=" not in gen.secret
    assert re.fullmatch(r"[A-Za-z0-9_-]+", gen.secret)
    decoded = base64.urlsafe_b64decode(gen.secret + "=" * (-len(gen.secret) % 4))
    assert len(decoded) == 32


def test_generate_accepts_an_explicit_lookup_id() -> None:
    gen = generate_account_token("0123456789abcdef01")
    assert gen.tenant_lookup_id == "0123456789abcdef01"
    assert gen.token.startswith("sfc_0123456789abcdef01_")


def test_tokens_are_unique_across_calls() -> None:
    tokens = {generate_account_token().token for _ in range(50)}
    assert len(tokens) == 50


def test_parse_roundtrips_a_generated_token() -> None:
    gen = generate_account_token()
    parsed = parse_account_token(gen.token)
    assert parsed is not None
    assert parsed.tenant_lookup_id == gen.tenant_lookup_id
    assert parsed.secret == gen.secret


def test_parse_splits_on_the_first_underscore_so_base64url_secrets_survive() -> None:
    parsed = parse_account_token("sfc_0123456789abcdef01_aa_bb-cc")
    assert parsed is not None
    assert parsed.tenant_lookup_id == "0123456789abcdef01"
    assert parsed.secret == "aa_bb-cc"


def test_parse_returns_none_for_every_malformed_token() -> None:
    for bad in [
        None,
        42,
        "",
        "nope",
        "sfc_",
        "sfc_onlylookup",
        "sfc__secret",          # empty lookup id
        "sfc_lookup_",          # empty secret
        "sfc_look up_secret",   # space in lookup id
        "sfc_lookup_sec ret",   # space in secret
        "SFC_lookup_secret",    # wrong-case prefix
    ]:
        assert parse_account_token(bad) is None, bad
