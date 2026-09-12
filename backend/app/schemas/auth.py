"""Authentication and user-management schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, field_validator
from trajyx_shared.domain import Role

from app.schemas.common import ApiModel, EmailAddress, ResponseModel

#: Minimum password length for locally managed accounts. Firebase enforces its
#: own policy; this applies to the development auth path and to the strength
#: check performed before a password ever reaches Firebase.
MIN_PASSWORD_LENGTH = 10


def check_password_strength(password: str) -> str:
    """Reject passwords that are trivially weak.

    Deliberately minimal: length plus character variety. A long passphrase
    should pass, so no composition rule beyond "more than one character class"
    is imposed. Defined once and applied through :data:`StrongPassword`, so
    every path that sets a password gets the same rule — an earlier version
    had this check on the administrator endpoint only, which left public
    driver registration accepting ``alllowercase``.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

    classes = sum(
        [
            any(character.islower() for character in password),
            any(character.isupper() for character in password),
            any(character.isdigit() for character in password),
            any(not character.isalnum() for character in password),
        ]
    )
    if classes < 2:
        raise ValueError(
            "Password must combine at least two of: lowercase, uppercase, digits, symbols."
        )
    return password


#: A password acceptable for a new or changed credential.
StrongPassword = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=256),
    AfterValidator(check_password_strength),
]


class LoginRequest(ApiModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(ResponseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Lifetime of the access token in seconds.")
    refresh_token: str | None = Field(
        default=None,
        description=(
            "Present only on the local development auth path. With Firebase, "
            "token refresh is handled by the Firebase client SDK."
        ),
    )
    user: UserResponse


class FirebaseExchangeRequest(ApiModel):
    """Exchanges a Firebase ID token for a TRAJYX session.

    The web and mobile clients sign in through the Firebase SDK and post the
    resulting ID token here. The backend verifies it, ensures a user document
    exists, and returns the profile plus role. The role is never read from the
    client — only from the verified token's claims or the user document.
    """

    id_token: str = Field(min_length=16, description="Firebase ID token from the client SDK.")


class UserResponse(ResponseModel):
    id: str
    email: str
    display_name: str | None = None
    role: Role
    status: str = Field(description="active | suspended")
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def is_staff(self) -> bool:
        """Dashboard user, as opposed to a driver on the mobile app."""
        return self.role in {Role.ADMIN, Role.TRAFFIC_OPERATOR, Role.ANALYST}


class UserCreateRequest(ApiModel):
    """Administrator-driven account creation.

    There is no self-registration for staff roles. A public sign-up that could
    grant ``TRAFFIC_OPERATOR`` would let anyone read CCTV-derived data.
    """

    email: EmailAddress
    password: StrongPassword
    display_name: str | None = Field(default=None, max_length=120)
    role: Role = Role.DRIVER


class UserUpdateRequest(ApiModel):
    """Self-service profile edit.

    Role and status are absent on purpose: changing them is an administrative
    action with its own endpoint, and accepting them here would be a
    privilege-escalation path.
    """

    display_name: str | None = Field(default=None, max_length=120)


class UserRoleUpdateRequest(ApiModel):
    """Administrator-only role change."""

    role: Role


class UserStatusUpdateRequest(ApiModel):
    """Administrator-only account suspension or reinstatement."""

    status: str = Field(pattern="^(active|suspended)$")


class PasswordChangeRequest(ApiModel):
    """Password change payload.

    A body, never query parameters: a query string is recorded in access logs,
    proxy logs and browser history, so a password placed there leaks by design.
    """

    current_password: str = Field(min_length=1, max_length=256)
    new_password: StrongPassword

    @field_validator("new_password")
    @classmethod
    def _must_differ(cls, new_password: str, info) -> str:
        if new_password == info.data.get("current_password"):
            raise ValueError("The new password must differ from the current one.")
        return new_password


class DriverRegistrationRequest(ApiModel):
    """Public driver sign-up.

    The one self-service path. It is hardcoded to ``DRIVER`` — the request
    carries no role field at all, so there is nothing to tamper with.
    """

    email: EmailAddress
    password: StrongPassword
    display_name: str | None = Field(default=None, max_length=120)


# Resolves the forward reference in TokenResponse.
TokenResponse.model_rebuild()
