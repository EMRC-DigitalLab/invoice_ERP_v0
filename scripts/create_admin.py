#!/usr/bin/env python3
"""
Seed the first admin user.  Run once inside the running container:

    docker exec -it invoice_erp_production python scripts/create_admin.py

Requires all env vars (DB_HOST, DB_USER, etc.) to already be set —
they are when running inside the Docker container.
"""

import secrets
import sys
import uuid
from datetime import datetime, timezone

import app.models  # noqa: F401 — registers all tables with Base.metadata
from app.core.database import Base, SessionLocal, engine
from app.core.security import get_password_hash
from app.models.user import User


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    name = input("Admin full name: ").strip()
    email = input("Admin email:     ").strip().lower()
    role = input("Role       [cfo]: ").strip() or "cfo"
    title = input("Title  [Administrator]: ").strip() or "Administrator"
    department = input("Department  [Management]: ").strip() or "Management"

    if db.query(User).filter(User.email == email).first():
        print(f"\nError: a user with email '{email}' already exists.")
        db.close()
        sys.exit(1)

    password = secrets.token_urlsafe(16)
    db.add(
        User(
            id=uuid.uuid4().hex,
            name=name,
            email=email,
            password_hash=get_password_hash(password),
            role=role,
            title=title,
            department=department,
            department_id=None,
            region_id=None,
            is_admin=True,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.close()

    print("\nAdmin created successfully.")
    print(f"  Email:    {email}")
    print(f"  Password: {password}")
    print("\nShare this password securely — it cannot be retrieved again.")


if __name__ == "__main__":
    main()
