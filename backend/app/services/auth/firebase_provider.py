"""Firebase Authentication identity provider.

The role is stored as a Firebase **custom claim**, which makes it part of the
signed ID token. That is what lets the Firestore security rules enforce roles
directly — `request.auth.token.role` — instead of having every rule read a
user document, which would be both slower and circular.

The user document mirrors the claim for querying and administration. The claim
is authoritative for authorisation; where they disagree, the document is
treated as stale and repaired.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog
from trajyx_shared.domain import Role

from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DependencyUnavailableError,
)
from app.repositories.base import DocumentStore, utc_now
from app.services.auth.base import AuthenticatedPrincipal, AuthProvider, IssuedToken

log = structlog.get_logger(__name__)

USERS = "users"

#: Firebase custom-claim key holding the TRAJYX role.
ROLE_CLAIM = "role"


class FirebaseAuthProvider(AuthProvider):
    """Verifies Firebase ID tokens and manages Firebase users."""

    def __init__(self, store: DocumentStore, settings: Settings, firebase_app: Any) -> None:
        self._store = store
        self._settings = settings
        self._app = firebase_app

    @property
    def name(self) -> str:
        return "firebase"

    # ------------------------------------------------------------------ verify

    async def verify_token(self, token: str) -> AuthenticatedPrincipal:
        from firebase_admin import auth as firebase_auth

        def _verify() -> dict[str, Any]:
            # check_revoked catches a session invalidated by an administrator
            # suspending the account, at the cost of one extra lookup.
            return firebase_auth.verify_id_token(token, app=self._app, check_revoked=True)

        try:
            claims = await asyncio.to_thread(_verify)
        except firebase_auth.RevokedIdTokenError as error:
            raise AuthenticationError("This session has been revoked. Sign in again.") from error
        except firebase_auth.ExpiredIdTokenError as error:
            raise AuthenticationError("This session has expired. Sign in again.") from error
        except (firebase_auth.InvalidIdTokenError, ValueError) as error:
            raise AuthenticationError("Invalid session token.") from error
        except Exception as error:  # noqa: BLE001 - transport boundary
            log.error("firebase_auth.verify_failed", error=str(error), error_type=type(error).__name__)
            raise DependencyUnavailableError(
                "Firebase Authentication is unreachable. The request was not completed."
            ) from error

        user_id = str(claims["uid"])
        email = str(claims.get("email") or "")

        document = await self._store.get(USERS, user_id)
        if document is None:
            # Authenticated with Firebase but never provisioned in TRAJYX.
            # Provisioning happens explicitly in exchange_id_token, so a
            # request arriving here without a profile is refused rather than
            # silently granted a default role.
            raise AuthorizationError(
                "This account is not provisioned for TRAJYX. Contact an administrator."
            )

        claim_role = _parse_role(claims.get(ROLE_CLAIM), user_id)
        document_role = _parse_role(document.get("role"), user_id)

        if claim_role is None:
            # No claim yet: trust the document and repair the claim so the
            # Firestore rules start working for this user.
            role = document_role or Role.DRIVER
            await self._sync_claim(user_id, role)
        else:
            role = claim_role
            if document_role != claim_role:
                log.warning(
                    "firebase_auth.role_mismatch_repaired",
                    user_id=user_id,
                    claim=claim_role.value,
                    document=document_role.value if document_role else None,
                )
                await self._store.update(USERS, user_id, {"role": claim_role.value})

        status = str(document.get("status", "active"))
        if status != "active":
            raise AuthorizationError("This account is suspended. Contact an administrator.")

        return AuthenticatedPrincipal(
            user_id=user_id,
            email=email or str(document.get("email", "")),
            role=role,
            display_name=document.get("display_name") or claims.get("name"),
            status=status,
        )

    # ---------------------------------------------------------------- sign-in

    async def authenticate(self, email: str, password: str) -> tuple[AuthenticatedPrincipal, IssuedToken]:
        """Not supported.

        The Firebase Admin SDK deliberately cannot verify a password: that is
        the client SDK's job, and routing passwords through this backend would
        mean handling credentials it has no need to see. Clients sign in with
        the Firebase SDK and exchange the resulting ID token via
        :meth:`exchange_id_token`.
        """
        del email, password
        raise AuthenticationError(
            "Password sign-in is handled by the Firebase client SDK. "
            "Sign in on the client, then POST the ID token to /auth/firebase."
        )

    async def exchange_id_token(self, id_token: str) -> AuthenticatedPrincipal:
        """Verify a client ID token and ensure a TRAJYX profile exists.

        This is the provisioning path. A first-time Firebase user gets a
        ``DRIVER`` profile: the least-privileged role, so an account created
        through public sign-up cannot reach operator data. Staff roles are
        granted only by an administrator.
        """
        from firebase_admin import auth as firebase_auth

        def _verify() -> dict[str, Any]:
            return firebase_auth.verify_id_token(id_token, app=self._app)

        try:
            claims = await asyncio.to_thread(_verify)
        except (firebase_auth.InvalidIdTokenError, firebase_auth.ExpiredIdTokenError, ValueError) as error:
            raise AuthenticationError("Invalid or expired Firebase ID token.") from error

        user_id = str(claims["uid"])
        email = str(claims.get("email") or "")

        document = await self._store.get(USERS, user_id)
        if document is None:
            role = _parse_role(claims.get(ROLE_CLAIM), user_id) or Role.DRIVER
            document = await self._store.create(
                USERS,
                {
                    "email": email.lower(),
                    "display_name": claims.get("name"),
                    "role": role.value,
                    "status": "active",
                    "created_at": utc_now(),
                    "last_login_at": utc_now(),
                    "auth_provider": "firebase",
                },
                document_id=user_id,
            )
            await self._sync_claim(user_id, role)
            log.info("firebase_auth.user_provisioned", user_id=user_id, role=role.value)
        else:
            await self._store.update(USERS, user_id, {"last_login_at": utc_now()})

        status = str(document.get("status", "active"))
        if status != "active":
            raise AuthorizationError("This account is suspended. Contact an administrator.")

        return AuthenticatedPrincipal(
            user_id=user_id,
            email=email or str(document.get("email", "")),
            role=_parse_role(document.get("role"), user_id) or Role.DRIVER,
            display_name=document.get("display_name"),
            status=status,
        )

    # ----------------------------------------------------------- user records

    async def create_credential(self, email: str, password: str, display_name: str | None) -> str:
        from firebase_admin import auth as firebase_auth

        def _create() -> str:
            record = firebase_auth.create_user(
                email=email.strip().lower(),
                password=password,
                display_name=display_name,
                app=self._app,
            )
            return str(record.uid)

        try:
            return await asyncio.to_thread(_create)
        except firebase_auth.EmailAlreadyExistsError as error:
            raise ConflictError("An account with this email address already exists.") from error
        except ValueError as error:
            # Firebase rejects weak passwords and malformed addresses here.
            raise ConflictError(str(error)) from error

    async def set_role(self, user_id: str, role: Role) -> None:
        await self._sync_claim(user_id, role)

    async def _sync_claim(self, user_id: str, role: Role) -> None:
        """Write the role into the Firebase custom claims.

        Existing claims are preserved: ``set_custom_user_claims`` replaces the
        whole object, so blindly writing only the role would discard anything
        else stored there.
        """
        from firebase_admin import auth as firebase_auth

        def _set() -> None:
            record = firebase_auth.get_user(user_id, app=self._app)
            claims = dict(record.custom_claims or {})
            claims[ROLE_CLAIM] = role.value
            firebase_auth.set_custom_user_claims(user_id, claims, app=self._app)

        await asyncio.to_thread(_set)

    async def delete_credential(self, user_id: str) -> None:
        from firebase_admin import auth as firebase_auth

        def _delete() -> None:
            # Deleting an already-absent user is not an error.
            with contextlib.suppress(firebase_auth.UserNotFoundError):
                firebase_auth.delete_user(user_id, app=self._app)

        await asyncio.to_thread(_delete)

    async def revoke_sessions(self, user_id: str) -> None:
        """Invalidate every existing token for a user.

        Called on suspension and on role downgrade, so a revoked operator
        cannot keep working until their hour-long token expires.
        """
        from firebase_admin import auth as firebase_auth

        def _revoke() -> None:
            with contextlib.suppress(firebase_auth.UserNotFoundError):
                firebase_auth.revoke_refresh_tokens(user_id, app=self._app)

        await asyncio.to_thread(_revoke)
        log.info("firebase_auth.sessions_revoked", user_id=user_id)


def _parse_role(value: Any, user_id: str) -> Role | None:
    if value is None:
        return None
    try:
        return Role(str(value))
    except ValueError:
        # Never fail open to a privileged role on unrecognised input.
        log.error("firebase_auth.unknown_role", role=str(value), user_id=user_id)
        return Role.DRIVER
