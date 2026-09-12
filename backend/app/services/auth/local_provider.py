"""Local development identity provider.

Exists so the product runs end to end without a Firebase project, and so the
authorisation code path exercised in tests is the same one production uses.

Passwords are hashed with bcrypt and tokens are signed JWTs, because a
development path that stored plaintext or skipped signature checks would be a
liability the moment someone exposed it. It is nonetheless **not** a production
identity system: there is no rate limiting, no MFA, no password reset, no
account recovery and no audit trail. Startup refuses it outright when
``TRAJYX_ENVIRONMENT=production``.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from jose import JWTError, jwt
from trajyx_shared.domain import Role

from app.core.config import Settings
from app.core.errors import AuthenticationError, AuthorizationError, ConflictError, NotFoundError
from app.core.password import get_password_hasher
from app.repositories.base import DocumentStore, Filter, Query, utc_now
from app.services.auth.base import AuthenticatedPrincipal, AuthProvider, IssuedToken

log = structlog.get_logger(__name__)

USERS = "users"
CREDENTIALS = "auth_credentials"


class LocalAuthProvider(AuthProvider):
    """Password credentials in the document store, sessions as signed JWTs."""

    def __init__(self, store: DocumentStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings
        self._hasher = get_password_hasher(settings.bcrypt_rounds)

    @property
    def name(self) -> str:
        return "local"

    # ------------------------------------------------------------------ tokens

    def _issue(self, principal: AuthenticatedPrincipal) -> IssuedToken:
        now = datetime.now(timezone.utc)
        ttl = timedelta(minutes=self._settings.access_token_ttl_minutes)
        expires_at = now + ttl

        claims: dict[str, Any] = {
            "sub": principal.user_id,
            "email": principal.email,
            # Namespaced to match the Firebase custom-claim shape, so token
            # consumers read the role from the same place either way.
            "role": principal.role.value,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": "trajyx-local",
            "jti": secrets.token_urlsafe(16),
        }
        token = jwt.encode(claims, self._settings.jwt_secret, algorithm=self._settings.jwt_algorithm)

        return IssuedToken(
            access_token=token,
            expires_in_seconds=int(ttl.total_seconds()),
            expires_at=expires_at,
        )

    async def verify_token(self, token: str) -> AuthenticatedPrincipal:
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[self._settings.jwt_algorithm],
                issuer="trajyx-local",
            )
        except JWTError as error:
            # One generic message: distinguishing "expired" from "bad
            # signature" to the client tells an attacker which half to work on.
            raise AuthenticationError("Invalid or expired session token.") from error

        user_id = claims.get("sub")
        if not user_id:
            raise AuthenticationError("Session token is missing a subject.")

        # The user document is re-read rather than trusted from the token, so a
        # role change or suspension takes effect on the next request instead of
        # waiting for the token to expire.
        document = await self._store.get(USERS, str(user_id))
        if document is None:
            raise AuthenticationError("The account for this session no longer exists.")

        principal = _principal_from_document(document)
        if not principal.is_active:
            raise AuthorizationError("This account is suspended.")
        return principal

    # -------------------------------------------------------------- passwords

    async def authenticate(self, email: str, password: str) -> tuple[AuthenticatedPrincipal, IssuedToken]:
        normalised = _normalise_email(email)

        page = await self._store.query(
            CREDENTIALS, Query().where(Filter.eq("email", normalised)).take(1)
        )
        credential = page.documents[0] if page.documents else None

        stored_hash = (
            str(credential.get("password_hash", "")) if credential else self._hasher.dummy_hash
        )
        password_ok = self._hasher.verify(password, stored_hash)

        if credential is None or not password_ok:
            log.info("auth.login_failed", email_domain=normalised.partition("@")[2])
            raise AuthenticationError("Incorrect email address or password.")

        user_id = str(credential["user_id"])
        document = await self._store.get(USERS, user_id)
        if document is None:
            # Credential without a profile: a broken state, not a login failure.
            log.error("auth.orphaned_credential", user_id=user_id)
            raise AuthenticationError("Incorrect email address or password.")

        principal = _principal_from_document(document)
        if not principal.is_active:
            raise AuthorizationError("This account is suspended. Contact an administrator.")

        await self._store.update(USERS, user_id, {"last_login_at": utc_now()})
        log.info("auth.login_succeeded", user_id=user_id, role=principal.role.value)

        return principal, self._issue(principal)

    async def create_credential(self, email: str, password: str, display_name: str | None) -> str:
        del display_name  # stored on the user document, not the credential
        normalised = _normalise_email(email)

        existing = await self._store.query(
            CREDENTIALS, Query().where(Filter.eq("email", normalised)).take(1)
        )
        if existing.documents:
            raise ConflictError("An account with this email address already exists.")

        user_id = secrets.token_hex(16)
        await self._store.create(
            CREDENTIALS,
            {
                "user_id": user_id,
                "email": normalised,
                "password_hash": self._hasher.hash(password),
                "created_at": utc_now(),
            },
        )
        return user_id

    async def set_role(self, user_id: str, role: Role) -> None:
        """No-op for this provider.

        The role lives on the user document, which is the single source of
        truth here; ``verify_token`` reads it from there on every request.
        """
        del user_id, role

    async def delete_credential(self, user_id: str) -> None:
        page = await self._store.query(
            CREDENTIALS, Query().where(Filter.eq("user_id", user_id)).take(1)
        )
        for document in page.documents:
            await self._store.delete(CREDENTIALS, str(document["id"]))

    async def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        """Change a password after verifying the current one."""
        page = await self._store.query(
            CREDENTIALS, Query().where(Filter.eq("user_id", user_id)).take(1)
        )
        if not page.documents:
            raise NotFoundError("No credential record exists for this account.")

        credential = page.documents[0]
        if not self._hasher.verify(current_password, str(credential.get("password_hash", ""))):
            raise AuthenticationError("The current password is incorrect.")

        await self._store.update(
            CREDENTIALS,
            str(credential["id"]),
            {"password_hash": self._hasher.hash(new_password), "updated_at": utc_now()},
        )


def _normalise_email(email: str) -> str:
    """Lowercase and trim.

    Email local parts are technically case-sensitive, but no real provider
    treats them that way, and letting ``Admin@x.com`` and ``admin@x.com`` be
    two accounts is a security problem rather than a feature.
    """
    return email.strip().lower()


def _principal_from_document(document: dict[str, Any]) -> AuthenticatedPrincipal:
    raw_role = str(document.get("role", Role.DRIVER.value))
    try:
        role = Role(raw_role)
    except ValueError:
        # An unrecognised role must not fail open to something privileged.
        log.error("auth.unknown_role", role=raw_role, user_id=document.get("id"))
        role = Role.DRIVER

    return AuthenticatedPrincipal(
        user_id=str(document["id"]),
        email=str(document.get("email", "")),
        role=role,
        display_name=document.get("display_name"),
        status=str(document.get("status", "active")),
    )


def constant_time_equals(left: str, right: str) -> bool:
    """Compare secrets without leaking length or content through timing."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
