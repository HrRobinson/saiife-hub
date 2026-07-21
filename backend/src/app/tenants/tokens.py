"""Account tokens — `sfc_<tenantLookupId>_<secret>`.

PINNED BY saiife-cloud. The reference implementations are
`packages/shared/src/ids.ts` (format) and `packages/control-api/src/auth.ts`
(hashing). Any change here is a breaking change for every desktop install.

- `tenantLookupId` is NON-SECRET: it lets cloud find the tenant without a scan.
  It is HEX so it can never contain the `_` that separates it from the secret.
- `secret` is 32 random bytes (256 bits) base64url, unpadded.
- The plaintext token is shown to the user ONCE and never stored, logged, or echoed.
"""
from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass

ACCOUNT_TOKEN_PREFIX = "sfc_"

_SECRET_BYTES = 32
_LOOKUP_BYTES = 9  # -> 18 hex chars
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _base64url(raw: bytes) -> str:
    """base64url with no padding — matches Node's `buf.toString('base64url')`."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def new_tenant_lookup_id() -> str:
    """18 hex chars. Non-secret. Never contains `_`."""
    return secrets.token_bytes(_LOOKUP_BYTES).hex()


@dataclass(frozen=True)
class GeneratedAccountToken:
    token: str
    """The full plaintext — shown to the user ONCE, never stored."""
    tenant_lookup_id: str
    """Non-secret; stored so cloud can look the tenant up."""
    secret: str
    """The secret half — what gets scrypt-hashed. Never stored in plaintext."""


def generate_account_token(tenant_lookup_id: str | None = None) -> GeneratedAccountToken:
    lookup = tenant_lookup_id if tenant_lookup_id is not None else new_tenant_lookup_id()
    secret = _base64url(secrets.token_bytes(_SECRET_BYTES))
    return GeneratedAccountToken(
        token=f"{ACCOUNT_TOKEN_PREFIX}{lookup}_{secret}",
        tenant_lookup_id=lookup,
        secret=secret,
    )


@dataclass(frozen=True)
class ParsedAccountToken:
    tenant_lookup_id: str
    secret: str


def parse_account_token(token: object) -> ParsedAccountToken | None:
    """Split a presented token into its non-secret lookup id and secret half.

    Returns None for ANY malformed token; verification then fails uniformly, so
    there is no oracle telling an attacker which half was wrong.
    """
    if not isinstance(token, str) or not token.startswith(ACCOUNT_TOKEN_PREFIX):
        return None
    rest = token[len(ACCOUNT_TOKEN_PREFIX) :]
    sep = rest.find("_")
    if sep <= 0 or sep >= len(rest) - 1:
        return None
    lookup = rest[:sep]
    secret = rest[sep + 1 :]
    if not _SEGMENT_RE.match(lookup) or not _SEGMENT_RE.match(secret):
        return None
    return ParsedAccountToken(tenant_lookup_id=lookup, secret=secret)
