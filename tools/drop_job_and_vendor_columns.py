"""
Skrip migrasi database: Menghapus kolom posisi_rekrutmen, deskripsi_it, dan penanggung_jawab dari tabel leads.
Aman dijalankan berulang (idempoten).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from backend.models.base import engine


def drop_columns():
    cols_to_drop = ["posisi_rekrutmen", "deskripsi_it", "penanggung_jawab"]
    print(f"Memeriksa kolom yang akan dihapus: {cols_to_drop}")

    with engine.connect() as conn:
        # Cek kolom yang ada di tabel leads
        res = conn.execute(text("SHOW COLUMNS FROM leads"))
        existing_cols = {row[0] for row in res.fetchall()}
        print(f"Kolom yang terdaftar di tabel leads saat ini: {len(existing_cols)} kolom")

        for col in cols_to_drop:
            if col in existing_cols:
                print(f"Menghapus kolom '{col}' dari tabel leads...")
                conn.execute(text(f"ALTER TABLE leads DROP COLUMN `{col}`"))
                print(f"Kolom '{col}' berhasil dihapus.")
            else:
                print(f"Kolom '{col}' sudah tidak ada (dilewati).")

        conn.commit()
    print("Migrasi drop columns selesai dengan sukses.")


if __name__ == "__main__":
    drop_columns()
