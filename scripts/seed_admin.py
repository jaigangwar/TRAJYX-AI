"""Create the first TRAJYX administrator.

    python scripts/seed_admin.py --email admin@example.com
    python scripts/seed_admin.py --email admin@example.com --password '...'

This is the supported way to bootstrap a deployment, including production. It
requires filesystem access to the host rather than only network access, which
is why the equivalent HTTP endpoint is disabled in production.

Refuses to run if an administrator already exists, so it cannot be used to
quietly add a second one.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def generate_password(length: int = 20) -> str:
    """A password strong enough that the operator can safely keep the default."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def run(email: str, password: str, role_name: str) -> int:
    from app.core.config import get_settings
    from app.core.errors import TrajyxError
    from app.repositories.factory import create_document_store
    from app.services.auth.factory import create_auth_provider
    from app.services.user_service import UserService
    from trajyx_shared.domain import Role

    settings = get_settings()
    store = create_document_store(settings)
    provider = create_auth_provider(settings, store)
    users = UserService(store, provider)

    print(f"Data backend : {settings.resolved_data_backend.value}")
    print(f"Auth backend : {settings.resolved_auth_backend.value}")
    print(f"Environment  : {settings.environment.value}\n")

    existing = await users.count_admins()
    if existing > 0:
        print(
            f"An administrator already exists ({existing} found). Refusing to create another.\n"
            "Use the dashboard, or POST /api/v1/users as that administrator.",
            file=sys.stderr,
        )
        return 1

    try:
        user = await users.create_user(
            email=email,
            password=password,
            display_name="Administrator",
            role=Role(role_name),
        )
    except TrajyxError as error:
        print(f"Failed: {error.message}", file=sys.stderr)
        return 1
    finally:
        await store.close()

    print("Administrator created.\n")
    print(f"  id    : {user.id}")
    print(f"  email : {user.email}")
    print(f"  role  : {user.role.value}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first TRAJYX administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--password",
        default=None,
        help="Omit to be prompted, or use --generate-password.",
    )
    parser.add_argument(
        "--generate-password",
        action="store_true",
        help="Generate a strong password and print it once.",
    )
    parser.add_argument("--role", default="ADMIN", choices=["ADMIN"])
    args = parser.parse_args()

    if args.generate_password:
        password = generate_password()
        print("Generated password (shown once - store it in a password manager):")
        print(f"\n  {password}\n")
    elif args.password:
        password = args.password
    else:
        # Prompted rather than passed as an argument: a command line ends up in
        # shell history and in the process list.
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 2

    if len(password) < 10:
        print("Password must be at least 10 characters.", file=sys.stderr)
        return 2

    return asyncio.run(run(args.email, password, args.role))


if __name__ == "__main__":
    raise SystemExit(main())
