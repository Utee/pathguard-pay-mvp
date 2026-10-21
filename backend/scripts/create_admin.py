
import argparse
import getpass
import sys

from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.db import SessionLocal, initialize_database
from app.models import UserAccount


def create_admin(email: str, display_name: str) -> None:
    email = email.strip().lower()
    display_name = display_name.strip()

    if not email or not display_name:
        raise ValueError("Email and display name are required.")

    password = getpass.getpass("Admin password (minimum 12 characters): ")
    confirm_password = getpass.getpass("Confirm admin password: ")

    if password != confirm_password:
        raise ValueError("Passwords do not match.")

    password_hash = hash_password(password)

    initialize_database()

    with SessionLocal() as db:
        existing = (
            db.query(UserAccount)
            .filter(UserAccount.email == email)
            .first()
        )

        if existing:
            raise ValueError(
                f"An account with {email} already exists. "
                "No changes were made."
            )

        admin = UserAccount(
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            role="admin",
            is_active=True,
        )

        try:
            db.add(admin)
            db.commit()
            db.refresh(admin)
        except IntegrityError:
            db.rollback()
            raise ValueError(
                "The account could not be created. "
                "An account with that email may already exist."
            ) from None

        print("\nAdmin account created successfully.")
        print(f"Email: {admin.email}")
        print(f"Role: {admin.role}")
        print(f"User ID: {admin.id}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a PathGuard Pay administrator account."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    try:
        create_admin(args.email, args.name)
    except (ValueError, IntegrityError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
