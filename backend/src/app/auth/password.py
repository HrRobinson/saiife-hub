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


# Precomputed argon2id hash (same parameters as _hasher) of a fixed, unused
# plaintext. Callers with no real password_hash to check against (unknown
# email, no local password) should still call verify_password(DUMMY_PASSWORD_HASH, ...)
# so the argon2id cost is paid on every code path — this closes the timing
# side-channel that would otherwise let an attacker distinguish "no such
# account" from "wrong password" by request latency.
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=1$N3mPSnmoxTDB2i5ne9rmow$"
    "+oBOUov9Bgk/Yk7yr48+W8jk7eAfY0PjKRJ7FiHrGU4"
)
