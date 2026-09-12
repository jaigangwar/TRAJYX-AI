"""User administration. Administrator-only throughout."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from trajyx_shared.domain import Role

from app.api.deps import CurrentUser, UserServiceDep, require_admin, require_staff
from app.schemas.auth import (
    UserCreateRequest,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from app.schemas.common import Acknowledgement, Page

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=Page[UserResponse],
    summary="List users",
    dependencies=[Depends(require_admin)],
)
async def list_users(
    users: UserServiceDep,
    role: Annotated[Role | None, Query(description="Filter by role.")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(description="Cursor from a previous page.")] = None,
) -> Page[UserResponse]:
    items, next_cursor = await users.list_users(role=role, limit=limit, cursor=cursor)
    return Page(items=items, next_cursor=next_cursor)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    dependencies=[Depends(require_admin)],
    responses={409: {"description": "Email address already registered."}},
)
async def create_user(
    payload: UserCreateRequest,
    users: UserServiceDep,
) -> UserResponse:
    """Provision an account with any role.

    This is the only way a staff role is granted. Public registration
    (`/auth/register`) is hardcoded to `DRIVER`.
    """
    return await users.create_user(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role=payload.role,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Read a user",
    dependencies=[Depends(require_staff)],
    responses={404: {"description": "User not found."}},
)
async def read_user(user_id: str, users: UserServiceDep) -> UserResponse:
    """Read one user. Staff-readable so an operator can attribute an event."""
    return await users.get(user_id)


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Change a user's role",
    responses={
        422: {"description": "Would remove the last administrator."},
        404: {"description": "User not found."},
    },
)
async def set_user_role(
    user_id: str,
    payload: UserRoleUpdateRequest,
    users: UserServiceDep,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> UserResponse:
    """Change a role.

    Refused if it would leave the deployment with no administrator. A
    downgrade out of a staff role revokes existing sessions immediately rather
    than waiting for the token to expire.
    """
    return await users.set_role(user_id, payload.role, acting_admin_id=admin.user_id)


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    summary="Suspend or reinstate a user",
    responses={422: {"description": "Cannot suspend yourself or the last administrator."}},
)
async def set_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    users: UserServiceDep,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> UserResponse:
    """Suspend or reinstate an account. Suspension revokes active sessions."""
    return await users.set_status(user_id, payload.status, acting_admin_id=admin.user_id)


@router.delete(
    "/{user_id}",
    response_model=Acknowledgement,
    summary="Delete a user",
    responses={422: {"description": "Cannot delete yourself or the last administrator."}},
)
async def delete_user(
    user_id: str,
    users: UserServiceDep,
    admin: Annotated[CurrentUser, Depends(require_admin)],
) -> Acknowledgement:
    """Remove an account and its credential.

    Records the user produced — hazard reports, trips, alerts — are retained,
    because deleting them would corrupt the safety history that other analysis
    depends on. They keep the user id as an opaque reference.
    """
    await users.delete_user(user_id, acting_admin_id=admin.user_id)
    return Acknowledgement(message="User deleted.")
