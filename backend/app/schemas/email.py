"""Email address validation.

Pydantic's ``EmailStr`` refuses RFC 6761 special-use domains. That default is
wrong for this product: TRAJYX is deployed on-premise for traffic authorities,
and an operator account at ``control@traffic.local`` is a realistic case that
must not be rejected at account creation.

So the special-use list is narrowed to the names that genuinely cannot receive
mail, and ``local``/``test`` are permitted. ``invalid`` and ``onion`` stay
blocked: the first is reserved precisely to be unusable, and the second is a
Tor hidden service, neither of which is a plausible operator mailbox.

Syntax validation stays on. Deliverability checking stays off: a DNS lookup
inside request handling would make account creation fail intermittently with
network conditions, which is worse than accepting a typo an administrator can
correct.
"""

from __future__ import annotations

from typing import Annotated

import email_validator
from pydantic import BeforeValidator

#: Special-use names TRAJYX accepts, because on-premise deployments use them.
PERMITTED_INTERNAL_DOMAINS = frozenset({"local", "test"})

#: Names that remain rejected: reserved-as-unusable, or not a mail destination.
BLOCKED_SPECIAL_USE_DOMAINS = tuple(
    name for name in email_validator.SPECIAL_USE_DOMAIN_NAMES if name not in PERMITTED_INTERNAL_DOMAINS
)

# Narrow the library's list to the blocked set. This is the mechanism
# email_validator documents for permitting specific internal domains, and it
# is done once at import rather than per call. The explicit check in
# validate_email_address still rejects everything left in the list, so the
# rule is enforced in one place and readable without knowing library
# internals.
email_validator.SPECIAL_USE_DOMAIN_NAMES = list(BLOCKED_SPECIAL_USE_DOMAINS)


def validate_email_address(value: object) -> str:
    """Validate and normalise an email address.

    Returns the lowercased normalised form, so ``Admin@Example.COM`` and
    ``admin@example.com`` cannot become two accounts.

    Raises:
        ValueError: with the library's explanation, which the API surfaces as a
            422 naming the field.
    """
    if not isinstance(value, str):
        raise ValueError("Email address must be a string.")

    candidate = value.strip()
    if not candidate:
        raise ValueError("Email address must not be empty.")

    domain = candidate.rpartition("@")[2].lower()
    if domain in BLOCKED_SPECIAL_USE_DOMAINS or any(
        domain.endswith(f".{name}") for name in BLOCKED_SPECIAL_USE_DOMAINS
    ):
        raise ValueError(f"The domain {domain!r} cannot receive email.")

    try:
        validated = email_validator.validate_email(candidate, check_deliverability=False)
    except email_validator.EmailNotValidError as error:
        raise ValueError(str(error)) from error

    return validated.normalized.lower()


#: Email address type used across the API.
EmailAddress = Annotated[str, BeforeValidator(validate_email_address)]
