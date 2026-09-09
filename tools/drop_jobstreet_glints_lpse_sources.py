"""Skrip migrasi database: Menghapus nilai ENUM 'jobstreet', 'glints', 'lpse' dari kolom leads.source.

Menyesuaikan tipe kolom menjadi:
    source ENUM('gmaps', 'dapodik') NOT NULL
"""
import os
import sys

# Tambahkan root workspace ke sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from backend.models.base import engine


def migrate_source_enum():
    with engine.connect() as conn:
        print("1. Memeriksa baris yang memakai sumber lama di tabel leads...")
        check_leads = conn.execute(
            text("SELECT count(*) FROM leads WHERE source IN ('jobstreet', 'glints', 'lpse')")
        ).scalar()
        print(f"   Ditemukan {check_leads} baris pada leads.")

        if check_leads > 0:
            print("   Menghapus data dengan sumber jobstreet, glints, lpse...")
            conn.execute(
                text("DELETE FROM leads WHERE source IN ('jobstreet', 'glints', 'lpse')")
            )

        print("2. Memeriksa scrape_jobs dengan sumber lama...")
        check_jobs = conn.execute(
            text("SELECT count(*) FROM scrape_jobs WHERE source IN ('jobstreet', 'glints', 'lpse')")
        ).scalar()
        print(f"   Ditemukan {check_jobs} baris pada scrape_jobs.")
        if check_jobs > 0:
            print("   Menghapus jobs dengan sumber jobstreet, glints, lpse...")
            conn.execute(
                text("DELETE FROM scrape_jobs WHERE source IN ('jobstreet', 'glints', 'lpse')")
            )

        print("3. Memperbarui kolom leads.source ENUM menjadi ('gmaps', 'dapodik')...")
        conn.execute(
            text("ALTER TABLE leads MODIFY COLUMN source ENUM('gmaps', 'dapodik') NOT NULL")
        )
        conn.commit()
        print("   Berhasil memperbarui kolom source.")

        print("4. Verifikasi definisi kolom saat ini:")
        col_info = conn.execute(text("SHOW COLUMNS FROM leads LIKE 'source'")).fetchall()
        print("  ", col_info)

    print("Migrasi selesai dengan sukses!")


if __name__ == "__main__":
    migrate_source_enum()
