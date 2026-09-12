"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, status
from trajyx_shared.domain import Role

from app.api.deps import (
    AuthProviderDep,
    CurrentUser,
    SettingsDep,
    UserServiceDep,
    require_local_auth,
)
from app.core.config import AuthBackend, Settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.schemas.auth import (
    DriverRegistrationRequest,
    FirebaseExchangeRequest,
    LoginRequest,
    PasswordChangeRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.schemas.common import Acknowledgement

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in with email and password (local auth only)",
    responses={
        401: {"description": "Incorrect email address or password."},
        403: {"description": "Account suspended, or this deployment uses Firebase."},
    },
)
async def login(
    payload: LoginRequest,
    provider: AuthProviderDep,
    users: UserServiceDep,
    _guard: Annotated[Settings, Depends(require_local_auth)],
) -> TokenResponse:
    """Exchange credentials for a session token.

    Available only on the local development auth path. With Firebase, the
    client SDK performs sign-in and posts the resulting ID token to
    `/auth/firebase` — the backend never handles a password it does not need
    to see.
    """
    principal, token = await provider.authenticate(payload.email, payload.password)
    profile = await users.get(principal.user_id)

    return TokenResponse(
        access_token=token.access_token,
        expires_in=token.expires_in_seconds,
        refresh_token=token.refresh_token,
        user=profile,
    )


@router.post(
    "/firebase",
    response_model=UserResponse,
    summary="Exchange a Firebase ID token for a TRAJYX profile",
    responses={
        401: {"description": "Invalid or expired Firebase ID token."},
        403: {"description": "Account suspended or not provisioned."},
    },
)
async def exchange_firebase_token(
    payload: FirebaseExchangeRequest,
    provider: AuthProviderDep,
    users: UserServiceDep,
    settings: SettingsDep,
) -> UserResponse:
    """Verify a Firebase ID token and return the caller's TRAJYX profile.

    No TRAJYX token is issued: with Firebase the ID token *is* the session, and
    the client SDK refreshes it. This endpoint exists to verify the token, to
    provision a profile on first sign-in, and to tell the client which role it
    actually has.
    """
    if settings.resolved_auth_backend is not AuthBackend.FIREBASE:
        raise AuthorizationError(
            "This deployment does not use Firebase Authentication. Use /auth/login instead."
        )

    from app.services.auth.firebase_provider import FirebaseAuthProvider

    if not isinstance(provider, FirebaseAuthProvider):  # pragma: no cover - defensive
        raise AuthorizationError("Firebase token exchange is not available.")

    principal = await provider.exchange_id_token(payload.id_token)
    return await users.get(principal.user_id)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current user profile and role",
)
async def read_me(principal: CurrentUser, users: UserServiceDep) -> UserResponse:
    """Return the signed-in user.

    Clients call this on load to discover their role, rather than trusting a
    role cached in browser storage.
    """
    return await users.get(principal.user_id)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update own profile",
)
async def update_me(
    payload: UserUpdateRequest, principal: CurrentUser, users: UserServiceDep
) -> UserResponse:
    """Update the caller's own profile.

    The request schema has no role or status field, so neither can be changed
    here regardless of what a client sends.
    """
    return await users.update_profile(principal.user_id, payload.display_name)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a driver account",
    responses={409: {"description": "Email address already registered."}},
)
async def register_driver(
    payload: DriverRegistrationRequest, users: UserServiceDep
) -> UserResponse:
    """Create a driver account.

    The only self-service registration path. The role is fixed to `DRIVER` in
    code — the request carries no role field — so this cannot be used to
    obtain access to operator or analyst data.
    """
    return await users.create_user(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role=Role.DRIVER,
    )


@router.post(
    "/bootstrap-admin",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the first administrator",
    responses={403: {"description": "An administrator already exists."}},
)
async def bootstrap_admin(
    payload: DriverRegistrationRequest, users: UserServiceDep, settings: SettingsDep
) -> UserResponse:
    """Create the first administrator on an empty deployment.

    Refuses once any administrator exists, so it cannot mint a second one. It
    solves the genuine chicken-and-egg problem that creating a user requires an
    administrator.

    Disabled entirely in production: there, the first administrator is created
    with `python scripts/seed_admin.py`, which requires filesystem access to
    the deployment rather than only network access to it.
    """
    if settings.is_production:
        raise AuthorizationError(
            "Bootstrap over HTTP is disabled in production. "
            "Create the first administrator with scripts/seed_admin.py."
        )
    return await users.ensure_bootstrap_admin(payload.email, payload.password)


@router.post(
    "/change-password",
    response_model=Acknowledgement,
    summary="Change own password (local auth only)",
    responses={401: {"description": "Current password is incorrect."}},
)
async def change_password(
    payload: PasswordChangeRequest,
    principal: CurrentUser,
    provider: AuthProviderDep,
    _guard: Annotated[Settings, Depends(require_local_auth)],
) -> Acknowledgement:
    """Change the caller's password after verifying the current one.

    With Firebase this is handled by the client SDK, which supports the full
    reset and verification flow.
    """
    from app.services.auth.local_provider import LocalAuthProvider

    # Length and difference are enforced by PasswordChangeRequest.
    if not isinstance(provider, LocalAuthProvider):  # pragma: no cover - defensive
        raise AuthenticationError("Password change is not available for this auth backend.")

    await provider.change_password(
        principal.user_id, payload.current_password, payload.new_password
    )
    log.info("auth.password_changed", user_id=principal.user_id)
    return Acknowledgement(message="Password updated.")


@router.post(
    "/logout",
    response_model=Acknowledgement,
    summary="Sign out",
)
async def logout(principal: CurrentUser, provider: AuthProviderDep) -> Acknowledgement:
    """Revoke the caller's sessions where the provider supports it.

    Firebase revokes refresh tokens server-side. Local development tokens are
    stateless JWTs and cannot be revoked individually, so the client discards
    the token and it expires on schedule — a real limitation of that path, and
    one of the reasons it is refused in production.
    """
    await provider.revoke_sessions(principal.user_id)
    log.info("auth.logout", user_id=principal.user_id)
    return Acknowledgement(message="Signed out.")
