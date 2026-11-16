"""Migrasi: Menambahkan kolom user_id pada tabel scrape_jobs."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy import text
from app.Models.base import engine


def migrate():
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(scrape_jobs)")).fetchall()]
            if "user_id" not in cols:
                conn.execute(text("ALTER TABLE scrape_jobs ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))
                conn.commit()
                print("Kolom user_id berhasil ditambahkan di SQLite.")
            else:
                print("Kolom user_id sudah ada di SQLite.")
        else:
            check_sql = text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'scrape_jobs' AND COLUMN_NAME = 'user_id'"
            )
            exists = conn.execute(check_sql).scalar() > 0
            if not exists:
                conn.execute(text(
                    "ALTER TABLE scrape_jobs "
                    "ADD COLUMN user_id INT NULL AFTER id, "
                    "ADD CONSTRAINT fk_scrape_jobs_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL, "
                    "ADD INDEX idx_scrape_jobs_user_id (user_id)"
                ))
                conn.commit()
                print("Kolom user_id berhasil ditambahkan di MySQL.")
            else:
                print("Kolom user_id sudah ada di MySQL.")


if __name__ == "__main__":
    migrate()
