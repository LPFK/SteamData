"""
CLI helper to create or promote an admin user.

Usage:
    python scripts/create_admin.py <username>

- If the username does not exist, prompt for a password and create with role='admin'.
- If the username exists with role='user' or 'viewer', prompt to promote it.
- If the username exists with role='admin', print a message and exit.
"""

import sys
import getpass

sys.path.insert(0, ".")

from app.models import init_db, get_session, User
from app import auth


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/create_admin.py <username>")
        sys.exit(1)

    username = sys.argv[1].strip()
    init_db()

    with get_session() as session:
        user = session.query(User).filter_by(username=username).first()

        if user is None:
            print(f"User '{username}' does not exist. Creating as admin.")
            email = input("Email: ").strip()
            password = getpass.getpass("Password: ")
            confirm  = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Passwords do not match.")
                sys.exit(1)
            new_user = User(
                username        = username,
                email_encrypted = auth.encrypt_field(email),
                password_hash   = auth.hash_password(password),
                role            = "admin",
            )
            session.add(new_user)
            session.commit()
            print(f"Admin user '{username}' created.")

        elif user.role == "admin":
            print(f"User '{username}' is already an admin.")

        else:
            answer = input(
                f"User '{username}' has role='{user.role}'. Promote to admin? [y/N]: "
            ).strip().lower()
            if answer == "y":
                user.role = "admin"
                session.commit()
                print(f"User '{username}' promoted to admin.")
            else:
                print("Aborted.")


if __name__ == "__main__":
    main()
