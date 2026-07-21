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


# --- hashing (pinned by saiife-cloud/packages/control-api/src/auth.ts) -------

import binascii  # noqa: E402
import hashlib  # noqa: E402
import hmac  # noqa: E402

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN = 32
SALT_LEN = 16

# 128 * N * r = 16 MiB of scratch; give OpenSSL headroom above its 32 MiB default.
_MAXMEM = 64 * 1024 * 1024

# A fixed dummy salt so the unknown-tenant path still performs scrypt work and
# cannot be used as a timing oracle. Byte-identical to cloud's `DUMMY_SALT`.
DUMMY_SALT = bytes([7]) * SALT_LEN


def _scrypt(secret: str, pepper: str, salt: bytes) -> bytes:
    # The pepper is mixed into the PASSWORD side; the salt is per-tenant and is
    # stored alongside the hash. Matches Node: scryptSync(`${pepper}:${secret}`, ...).
    return hashlib.scrypt(
        f"{pepper}:{secret}".encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_LEN,
        maxmem=_MAXMEM,
    )


def hash_account_secret(secret: str, pepper: str, salt: bytes | None = None) -> str:
    """Hash a token's secret half FOR STORAGE.

    Returns the self-describing `scrypt$N$r$p$<saltB64>$<hashB64>` — never the
    plaintext. Used at issuance; the plaintext is shown once and discarded.
    """
    salt = salt if salt is not None else secrets.token_bytes(SALT_LEN)
    digest = _scrypt(secret, pepper, salt)
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_account_secret(secret: str, pepper: str, stored: str) -> bool:
    """Constant-time verify of a presented secret against a stored hash string."""
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        salt = base64.b64decode(parts[4], validate=True)
        expected = base64.b64decode(parts[5], validate=True)
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
    except (ValueError, binascii.Error):
        return False
    if len(expected) != KEY_LEN:
        return False
    try:
        actual = hashlib.scrypt(
            f"{pepper}:{secret}".encode("utf-8"),
            salt=salt, n=n, r=r, p=p, dklen=KEY_LEN, maxmem=_MAXMEM,
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def equalize_timing(secret: str, pepper: str) -> None:
    """Burn one scrypt against the dummy salt so an unknown lookup id costs the
    same as a real verification. Never returns or logs anything."""
    _scrypt(secret, pepper, DUMMY_SALT)
    return None
