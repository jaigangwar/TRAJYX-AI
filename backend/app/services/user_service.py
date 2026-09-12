"""User provisioning and administration.

Holds the rules that must not be duplicated in a route handler:

* A role change updates the identity provider *and* the user document, and
  revokes existing sessions so the change takes effect immediately.
* An administrator cannot remove or demote the last remaining administrator,
  which would lock everyone out of the deployment permanently.
* Self-service edits cannot touch role or status.
"""

from __future__ import annotations

import structlog
from trajyx_shared.domain import Role

from app.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.repositories.base import DocumentStore, Filter, Query, utc_now
from app.schemas.auth import UserResponse
from app.services.auth.base import AuthProvider

log = structlog.get_logger(__name__)

USERS = "users"
STAFF_ROLES = frozenset({Role.ADMIN, Role.TRAFFIC_OPERATOR, Role.ANALYST})


class UserService:
    def __init__(self, store: DocumentStore, auth_provider: AuthProvider) -> None:
        self._store = store
        self._auth = auth_provider

    # ------------------------------------------------------------------ reads

    async def get(self, user_id: str) -> UserResponse:
        document = await self._store.get(USERS, user_id)
        if document is None:
            raise NotFoundError(f"User {user_id} not found.", details={"user_id": user_id})
        return _to_response(document)

    async def find_by_email(self, email: str) -> UserResponse | None:
        page = await self._store.query(
            USERS, Query().where(Filter.eq("email", email.strip().lower())).take(1)
        )
        return _to_response(page.documents[0]) if page.documents else None

    async def list_users(
        self, role: Role | None = None, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[UserResponse], str | None]:
        query = Query().order_by("created_at", descending=True).take(limit).after(cursor)
        if role is not None:
            query = query.where(Filter.eq("role", role.value))

        page = await self._store.query(USERS, query)
        return [_to_response(document) for document in page.documents], page.next_cursor

    async def count_admins(self) -> int:
        return await self._store.count(USERS, Query().where(Filter.eq("role", Role.ADMIN.value)))

    # ----------------------------------------------------------------- create

    async def create_user(
        self, email: str, password: str, display_name: str | None, role: Role
    ) -> UserResponse:
        """Provision an account in the identity provider and the store."""
        normalised = email.strip().lower()

        if await self.find_by_email(normalised) is not None:
            raise ConflictError("An account with this email address already exists.")

        user_id = await self._auth.create_credential(normalised, password, display_name)

        try:
            document = await self._store.create(
                USERS,
                {
                    "email": normalised,
                    "display_name": display_name,
                    "role": role.value,
                    "status": "active",
                    "created_at": utc_now(),
                    "last_login_at": None,
                    "auth_provider": self._auth.name,
                },
                document_id=user_id,
            )
            await self._auth.set_role(user_id, role)
        except Exception:
            # Do not leave a credential that can authenticate but has no
            # profile: verify_token would reject it and the address would be
            # permanently unregisterable.
            log.error("user_service.rollback_credential", user_id=user_id)
            await self._auth.delete_credential(user_id)
            raise

        log.info("user_service.created", user_id=user_id, role=role.value)
        return _to_response(document)

    # ----------------------------------------------------------------- update

    async def update_profile(self, user_id: str, display_name: str | None) -> UserResponse:
        """Self-service edit. Cannot reach role or status by construction."""
        document = await self._store.update(
            USERS, user_id, {"display_name": display_name, "updated_at": utc_now()}
        )
        return _to_response(document)

    async def set_role(self, user_id: str, role: Role, acting_admin_id: str) -> UserResponse:
        current = await self.get(user_id)
        if current.role is role:
            return current

        # Removing the last administrator would make the deployment
        # unadministrable, with no recovery path short of direct database
        # access.
        if current.role is Role.ADMIN and role is not Role.ADMIN and await self.count_admins() <= 1:
            raise ValidationError(
                "This is the only administrator. Promote another user before changing this role."
            )

        await self._auth.set_role(user_id, role)
        document = await self._store.update(
            USERS, user_id, {"role": role.value, "updated_at": utc_now()}
        )

        # A demotion must take effect now, not when the old token expires.
        if current.role in STAFF_ROLES and role not in STAFF_ROLES:
            await self._auth.revoke_sessions(user_id)

        log.info(
            "user_service.role_changed",
            user_id=user_id,
            previous=current.role.value,
            role=role.value,
            by=acting_admin_id,
        )
        return _to_response(document)

    async def set_status(self, user_id: str, status: str, acting_admin_id: str) -> UserResponse:
        if status not in {"active", "suspended"}:
            raise ValidationError("Status must be 'active' or 'suspended'.")

        current = await self.get(user_id)
        if user_id == acting_admin_id and status == "suspended":
            raise ValidationError("You cannot suspend your own account.")

        if current.role is Role.ADMIN and status == "suspended" and await self.count_admins() <= 1:
            raise ValidationError(
                "This is the only administrator. Promote another user before suspending this account."
            )

        document = await self._store.update(
            USERS, user_id, {"status": status, "updated_at": utc_now()}
        )

        if status == "suspended":
            await self._auth.revoke_sessions(user_id)

        log.info("user_service.status_changed", user_id=user_id, status=status, by=acting_admin_id)
        return _to_response(document)

    async def delete_user(self, user_id: str, acting_admin_id: str) -> None:
        current = await self.get(user_id)

        if user_id == acting_admin_id:
            raise ValidationError("You cannot delete your own account.")
        if current.role is Role.ADMIN and await self.count_admins() <= 1:
            raise ValidationError("This is the only administrator and cannot be deleted.")

        await self._auth.delete_credential(user_id)
        await self._store.delete(USERS, user_id)
        log.info("user_service.deleted", user_id=user_id, by=acting_admin_id)

    # ---------------------------------------------------- first-run bootstrap

    async def ensure_bootstrap_admin(self, email: str, password: str) -> UserResponse:
        """Create the first administrator, only while none exists.

        Deliberately refuses once any administrator is present, so this cannot
        be used to mint a second one.
        """
        if await self.count_admins() > 0:
            raise AuthorizationError(
                "An administrator already exists. Ask them to create further accounts."
            )
        return await self.create_user(email, password, "Administrator", Role.ADMIN)


def _to_response(document: dict[str, object]) -> UserResponse:
    raw_role = str(document.get("role", Role.DRIVER.value))
    try:
        role = Role(raw_role)
    except ValueError:
        log.error("user_service.unknown_role", role=raw_role, user_id=document.get("id"))
        role = Role.DRIVER

    return UserResponse(
        id=str(document["id"]),
        email=str(document.get("email", "")),
        display_name=document.get("display_name"),  # type: ignore[arg-type]
        role=role,
        status=str(document.get("status", "active")),
        created_at=document.get("created_at"),  # type: ignore[arg-type]
        last_login_at=document.get("last_login_at"),  # type: ignore[arg-type]
    )
