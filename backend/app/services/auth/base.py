"""Identity provider interface.

Two implementations: Firebase Authentication for real deployments, and a local
password store for development. Routes depend only on this interface, so the
authorisation logic is identical either way — which is the point. If the
development path had its own shortcut through the role checks, those checks
would be untested where they matter.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime

from trajyx_shared.domain import Role


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """A verified caller.

    ``role`` is authoritative and comes from the token's claims or the user
    document — never from a request body or header.
    """

    user_id: str
    email: str
    role: Role
    display_name: str | None = None
    status: str = "active"

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_staff(self) -> bool:
        return self.role in {Role.ADMIN, Role.TRAFFIC_OPERATOR, Role.ANALYST}


@dataclass(frozen=True, slots=True)
class IssuedToken:
    access_token: str
    expires_in_seconds: int
    refresh_token: str | None = None
    expires_at: datetime | None = None


class AuthProvider(abc.ABC):
    """Verifies credentials and tokens, and owns the credential record."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """``firebase`` or ``local``. Reported on /health."""

    @abc.abstractmethod
    async def verify_token(self, token: str) -> AuthenticatedPrincipal:
        """Verify a bearer token.

        Raises:
            AuthenticationError: if the token is absent, malformed, expired,
                signed by the wrong key, or belongs to a user who no longer
                exists.
        """

    @abc.abstractmethod
    async def authenticate(self, email: str, password: str) -> tuple[AuthenticatedPrincipal, IssuedToken]:
        """Exchange an email and password for a session.

        Raises:
            AuthenticationError: on bad credentials. The message must not
                reveal whether the address exists, since that turns the login
                form into an account-enumeration oracle.
            AuthorizationError: if the account is suspended.
        """

    @abc.abstractmethod
    async def create_credential(self, email: str, password: str, display_name: str | None) -> str:
        """Create the credential record and return its user id.

        Raises:
            ConflictError: if the email is already registered.
        """

    @abc.abstractmethod
    async def set_role(self, user_id: str, role: Role) -> None:
        """Set the authoritative role for a user."""

    @abc.abstractmethod
    async def delete_credential(self, user_id: str) -> None:
        """Remove the credential record. Missing is not an error."""

    async def revoke_sessions(self, user_id: str) -> None:
        """Invalidate the user's existing tokens where the provider supports it."""
        return
