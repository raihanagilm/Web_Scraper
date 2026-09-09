"""Skrip migrasi database untuk menambahkan kolom kode dan multi-sosmed.

Menjalankan ALTER TABLE pada TiDB/MySQL:
1. `leads`: tambah `kode`, `instagram`, `facebook`, `linkedin`, `twitter_x`, modify `email` TEXT.
2. `categories`: tambah `kode`.
3. `cities`: tambah `kode`.
4. Melakukan backfill kode unik untuk data yang sudah ada di database.
"""
import sys
from pathlib import Path

# Pastikan root direktori ada di sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text
from backend.models.base import engine, SessionLocal
from backend.models.category import Category
from backend.models.city import City
from backend.models.lead import Lead
from backend.services.code_generator import (
    generate_category_code,
    generate_city_code,
    generate_lead_code,
)


def run_migration():
    print("Memulai migrasi database: kolom kode & multi-sosmed...")

    # Jalankan DDL ALTER TABLE secara aman
    ddl_statements = [
        # Categories
        "ALTER TABLE categories ADD COLUMN IF NOT EXISTS kode VARCHAR(50) UNIQUE AFTER id;",
        # Cities
        "ALTER TABLE cities ADD COLUMN IF NOT EXISTS kode VARCHAR(50) UNIQUE AFTER id;",
        # Leads
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS kode VARCHAR(50) UNIQUE AFTER id;",
        "ALTER TABLE leads MODIFY COLUMN email TEXT;",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS instagram TEXT AFTER sosmed;",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS facebook TEXT AFTER instagram;",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS linkedin TEXT AFTER facebook;",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS twitter_x TEXT AFTER linkedin;",
    ]

    with engine.connect() as conn:
        for stmt in ddl_statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
                print(f"  [OK] {stmt.strip()}")
            except Exception as e:
                # TiDB / MySQL ALTER TABLE error handling
                print(f"  [INFO] {stmt.strip()} -> {e}")

    # Backfill kode untuk data yang sudah ada
    db = SessionLocal()
    try:
        # 1. Categories
        cats = db.query(Category).order_by(Category.id.asc()).all()
        cat_count = 0
        for c in cats:
            if not c.kode:
                c.kode = generate_category_code(db, c.name)
                db.flush()
                cat_count += 1
        print(f"  [OK] Backfilled {cat_count} categories kode.")

        # 2. Cities
        cities = db.query(City).order_by(City.id.asc()).all()
        city_count = 0
        for ct in cities:
            if not ct.kode:
                ct.kode = generate_city_code(db, ct.name)
                db.flush()
                city_count += 1
        print(f"  [OK] Backfilled {city_count} cities kode.")

        # 3. Leads
        leads = db.query(Lead).order_by(Lead.id.asc()).all()
        lead_count = 0
        for ld in leads:
            if not ld.kode:
                cat_name = ld.category.name if ld.category else "GEN"
                ld.kode = generate_lead_code(db, cat_name)
                db.flush()
                lead_count += 1
        print(f"  [OK] Backfilled {lead_count} leads kode.")

        db.commit()
        print("Migrasi & backfill berhasil 100%!")
    except Exception as e:
        db.rollback()
        print(f"Error saat backfill: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
