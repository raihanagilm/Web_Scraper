"""Seed default user jika tabel users masih kosong."""
from backend.models import SessionLocal, User
from backend.services.auth_service import hash_password
from backend.config import settings


def seed_default_user() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            user = User(
                username=settings.seed_username,
                password_hash=hash_password(settings.seed_password),
                full_name=settings.seed_full_name,
            )
            db.add(user)
            db.commit()
            print(f"[seed] default user created: {settings.seed_username}")
        else:
            print("[seed] users table already populated, skipping")
    finally:
        db.close()
