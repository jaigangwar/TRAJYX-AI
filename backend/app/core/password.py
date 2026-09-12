"""Password hashing.

Uses ``bcrypt`` directly rather than passlib. passlib 1.7.4 is unmaintained and
breaks against bcrypt 5.x: its backend probe hashes a secret longer than 72
bytes, which bcrypt now rejects instead of silently truncating.

Three details matter for correctness:

1. **Pre-hashing.** bcrypt accepts at most 72 bytes, and older versions
   truncated silently, so an 80-character passphrase and its first 72 bytes
   would verify identically — a weaker password than the user believes they
   set. Hashing with SHA-256 and base64-encoding first gives a fixed 44-byte
   input, so the whole passphrase always contributes.

2. **Timing equalisation.** Verifying against :attr:`PasswordHasher.dummy_hash`
   costs the same as verifying a real hash, so login response time does not
   reveal whether an address is registered. The dummy hash uses the same cost
   factor as real hashes, which is why it belongs to the hasher instance
   rather than being a module constant.

3. **Configurable cost.** The work factor is a deliberate expense in
   production and a pointless one in tests: at 12 rounds each hash costs
   roughly 250 ms, which turns a suite that creates a few dozen accounts into
   minutes of bcrypt. It is therefore a setting, floored at a safe value for
   any non-test environment.
"""

from __future__ import annotations

import base64
import functools
import hashlib

import bcrypt

#: Production work factor. Roughly 250 ms on current server hardware: slow
#: enough to make offline cracking expensive, fast enough for interactive
#: sign-in. Existing hashes carry their own cost, so raising this does not
#: invalidate them.
DEFAULT_BCRYPT_ROUNDS = 12

#: Floor for anything that is not a test run. bcrypt permits 4, which is far
#: too cheap to protect a real credential.
MINIMUM_PRODUCTION_ROUNDS = 10


def _prepare(password: str) -> bytes:
    """Reduce a password to a fixed-length value bcrypt can take whole.

    SHA-256 then base64: base64 keeps the result free of NUL bytes, which
    would otherwise terminate the C string bcrypt reads.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


class PasswordHasher:
    """bcrypt hashing at a fixed cost factor."""

    def __init__(self, rounds: int = DEFAULT_BCRYPT_ROUNDS) -> None:
        if not 4 <= rounds <= 16:
            raise ValueError(f"bcrypt rounds must be between 4 and 16, got {rounds}")
        self._rounds = rounds

    @property
    def rounds(self) -> int:
        return self._rounds

    def hash(self, password: str) -> str:
        """Return a bcrypt hash, salt included, safe to store."""
        if not password:
            raise ValueError("Password must not be empty.")
        return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=self._rounds)).decode("ascii")

    def verify(self, password: str, stored_hash: str) -> bool:
        """Check a password against a stored hash.

        Returns ``False`` rather than raising on a malformed or empty hash: a
        corrupt record is an authentication failure, not a 500 that tells the
        caller something about the database.
        """
        if not password or not stored_hash:
            return False
        try:
            return bcrypt.checkpw(_prepare(password), stored_hash.encode("ascii"))
        except (ValueError, TypeError):
            return False

    @functools.cached_property
    def dummy_hash(self) -> str:
        """A hash to verify against when no credential record exists.

        Computed once per hasher, at this hasher's cost, so an unknown address
        takes the same time as a known one.
        """
        return self.hash("trajyx-timing-equalisation-placeholder")


@functools.lru_cache(maxsize=4)
def get_password_hasher(rounds: int = DEFAULT_BCRYPT_ROUNDS) -> PasswordHasher:
    """Return a cached hasher.

    Cached so ``dummy_hash`` is computed once per process rather than once per
    request.
    """
    return PasswordHasher(rounds)
