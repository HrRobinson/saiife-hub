from __future__ import annotations

import argon2

# OWASP security-enhanced parameters for a product that advertises security.
# memory_cost=64 MiB, time_cost=3, parallelism=1 -> ~50-80ms per hash on 2 vCPU.
_hasher = argon2.PasswordHasher(
    memory_cost=65536,
    time_cost=3,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(hashed: str, plaintext: str) -> bool:
    try:
        _hasher.verify(hashed, plaintext)
    except argon2.exceptions.VerifyMismatchError:
        return False
    except argon2.exceptions.InvalidHashError:
        return False
    except argon2.exceptions.VerificationError:
        return False
    return True


def needs_rehash(hashed: str) -> bool:
    """True if the stored hash uses outdated params and should be rehashed
    on the next successful login."""
    return _hasher.check_needs_rehash(hashed)
