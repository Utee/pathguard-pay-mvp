import argparse
import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password
from app.db import SessionLocal, initialize_database
from app.models import UserAccount


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("--name", default="PathGuard Pay Staff")
    parser.add_argument("--role", choices=("customer", "reviewer", "admin"), default="admin")
    args = parser.parse_args()

    email = args.email.strip().lower()
    password = getpass("Password (minimum 12 characters): ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")

    initialize_database()
    db = SessionLocal()
    try:
        existing = db.query(UserAccount).filter(UserAccount.email == email).first()
        if existing:
            raise SystemExit("An account with this email already exists.")
        user = UserAccount(
            email=email,
            display_name=args.name.strip() or "PathGuard Pay Staff",
            password_hash=hash_password(password),
            role=args.role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Created {args.role} account for {email}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
