#!/usr/bin/env python3
"""Create an admin user for FlowLens.

Usage:
    python scripts/create_admin.py admin@example.com "Admin User" SecurePassword123

This script creates a local admin user in the database.
Requires database to be running and configured via environment variables.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def create_admin(email: str, name: str, password: str) -> None:
    """Create an admin user in the database."""
    from sqlalchemy import select

    from flowlens.common.config import get_settings
    from flowlens.common.database import get_session_factory, init_database
    from flowlens.common.exceptions import ValidationError
    from flowlens.models.auth import User, UserRole
    from flowlens.services.auth_service import hash_password, validate_password_policy

    settings = get_settings()

    # Initialize database
    await init_database(settings)
    session_factory = get_session_factory()

    async with session_factory() as db:
        # Check if email already exists
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Error: User with email '{email}' already exists.")
            sys.exit(1)

        # Validate password policy
        try:
            validate_password_policy(password)
        except ValidationError as e:
            print(f"Error: {e.message}")
            sys.exit(1)

        # Create admin user
        user = User(
            email=email.lower(),
            name=name,
            role=UserRole.ADMIN.value,
            is_active=True,
            is_local=True,
            hashed_password=hash_password(password),
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        print(f"Admin user created successfully!")
        print(f"  ID: {user.id}")
        print(f"  Email: {user.email}")
        print(f"  Name: {user.name}")
        print(f"  Role: {user.role}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create an admin user for FlowLens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/create_admin.py admin@example.com "Admin User" MySecureP@ssw0rd
    python scripts/create_admin.py --email admin@example.com --name "Admin" --password secret123
        """,
    )
    parser.add_argument(
        "email",
        nargs="?",
        help="Email address for the admin user",
    )
    parser.add_argument(
        "name",
        nargs="?",
        help="Full name for the admin user",
    )
    parser.add_argument(
        "password",
        nargs="?",
        help="Password for the admin user",
    )
    parser.add_argument(
        "--email",
        dest="email_flag",
        help="Email address for the admin user",
    )
    parser.add_argument(
        "--name",
        dest="name_flag",
        help="Full name for the admin user",
    )
    parser.add_argument(
        "--password",
        dest="password_flag",
        help="Password for the admin user",
    )

    args = parser.parse_args()

    # Use positional or flag arguments
    email = args.email or args.email_flag
    name = args.name or args.name_flag
    password = args.password or args.password_flag

    # Validate required arguments
    if not email:
        parser.error("Email is required")
    if not name:
        parser.error("Name is required")
    if not password:
        parser.error("Password is required")

    # Run the async function
    asyncio.run(create_admin(email, name, password))


if __name__ == "__main__":
    main()
