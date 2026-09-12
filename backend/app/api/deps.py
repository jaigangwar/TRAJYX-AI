"""FastAPI dependencies: shared singletons, authentication and authorisation.

Authorisation is enforced **here**, on the server, for every protected route.
The dashboard also hides sections a role cannot use, but that is a convenience:
hiding a menu item is not access control, and a hand-written request must be
refused just the same.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from trajyx_shared.domain import Role

from app.core.config import AuthBackend, Settings, get_settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.repositories.base import DocumentStore
from app.services.auth.base import AuthenticatedPrincipal, AuthProvider
from app.services.storage import ObjectStorage
from app.services.user_service import UserService

log = structlog.get_logger(__name__)

# auto_error=False so a missing header produces the shared error envelope
# rather than FastAPI's own 403 shape.
_bearer = HTTPBearer(auto_error=False, scheme_name="TRAJYX bearer token")


# ------------------------------------------------------------------ singletons
# Built once in the app lifespan and read from app.state, so a request never
# pays to construct a Firestore client or re-read settings.


def get_store(request: Request) -> DocumentStore:
    store = getattr(request.app.state, "store", None)
    if store is None:  # pragma: no cover - indicates a broken lifespan
        raise RuntimeError("Document store was not initialised during startup.")
    return store


def get_storage(request: Request) -> ObjectStorage:
    storage = getattr(request.app.state, "storage", None)
    if storage is None:  # pragma: no cover
        raise RuntimeError("Object storage was not initialised during startup.")
    return storage


def get_auth_provider(request: Request) -> AuthProvider:
    provider = getattr(request.app.state, "auth_provider", None)
    if provider is None:  # pragma: no cover
        raise RuntimeError("Auth provider was not initialised during startup.")
    return provider


def get_user_service(
    store: Annotated[DocumentStore, Depends(get_store)],
    provider: Annotated[AuthProvider, Depends(get_auth_provider)],
) -> UserService:
    return UserService(store, provider)


# -------------------------------------------------------------- authentication


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    provider: Annotated[AuthProvider, Depends(get_auth_provider)],
) -> AuthenticatedPrincipal:
    """Resolve the caller from the bearer token.

    Raises 401 when no usable token is present, and 403 when the token is
    valid but the account is suspended.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required. Provide a bearer token.")
    if credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Authorization header must use the Bearer scheme.")

    return await provider.verify_token(credentials.credentials)


async def get_optional_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    provider: Annotated[AuthProvider, Depends(get_auth_provider)],
) -> AuthenticatedPrincipal | None:
    """Resolve the caller if a token is present, otherwise return None.

    For endpoints whose response varies with the caller but which do not
    require one. An invalid token still fails: silently treating a bad token as
    anonymous would mask a client bug.
    """
    if credentials is None or not credentials.credentials:
        return None
    return await provider.verify_token(credentials.credentials)


CurrentUser = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]
OptionalUser = Annotated[AuthenticatedPrincipal | None, Depends(get_optional_principal)]


# --------------------------------------------------------------- authorisation


def require_roles(*roles: Role) -> Callable[..., Awaitable[AuthenticatedPrincipal]]:
    """Build a dependency admitting only the listed roles.

    Usage::

        @router.get("/analytics", dependencies=[Depends(require_roles(Role.ADMIN, Role.ANALYST))])

    or, to also use the principal::

        async def handler(user: AuthenticatedPrincipal = Depends(require_roles(Role.ADMIN))):
    """
    permitted = frozenset(roles)
    if not permitted:
        raise ValueError("require_roles needs at least one role.")

    async def dependency(principal: CurrentUser) -> AuthenticatedPrincipal:
        if principal.role not in permitted:
            log.info(
                "authz.denied",
                user_id=principal.user_id,
                role=principal.role.value,
                required=sorted(role.value for role in permitted),
            )
            raise AuthorizationError(
                "Your role does not have access to this resource.",
                details={"required_roles": sorted(role.value for role in permitted)},
            )
        return principal

    return dependency


#: Any dashboard user.
require_staff = require_roles(Role.ADMIN, Role.TRAFFIC_OPERATOR, Role.ANALYST)

#: Administrators only: user management, settings, destructive operations.
require_admin = require_roles(Role.ADMIN)

#: Camera configuration, video analysis, live monitoring, event review.
require_operator = require_roles(Role.ADMIN, Role.TRAFFIC_OPERATOR)

#: Analytics, reports, model health.
require_analyst = require_roles(Role.ADMIN, Role.ANALYST)

#: The mobile driver experience. Administrators are included so a deployment
#: can be smoke-tested from one account.
require_driver = require_roles(Role.ADMIN, Role.DRIVER)


def require_self_or_admin(principal: AuthenticatedPrincipal, target_user_id: str) -> None:
    """Guard a per-user resource.

    Call inside a handler once the target id is known, for example a driver
    reading their own trip history.
    """
    if principal.role is Role.ADMIN or principal.user_id == target_user_id:
        return
    raise AuthorizationError("You can only access your own records.")


# ------------------------------------------------------------------- utilities


def require_local_auth(settings: Annotated[Settings, Depends(get_settings)]) -> Settings:
    """Guard endpoints that only exist on the local development auth path.

    ``/auth/login`` accepts a password, which the Firebase path deliberately
    cannot do. Rather than returning a confusing failure from deep inside the
    provider, such routes reject early with an explanation.
    """
    if settings.resolved_auth_backend is not AuthBackend.LOCAL:
        raise AuthorizationError(
            "Password sign-in is not available: this deployment uses Firebase Authentication. "
            "Sign in with the Firebase client SDK and exchange the ID token at /auth/firebase."
        )
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]
StoreDep = Annotated[DocumentStore, Depends(get_store)]
StorageDep = Annotated[ObjectStorage, Depends(get_storage)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
AuthProviderDep = Annotated[AuthProvider, Depends(get_auth_provider)]
