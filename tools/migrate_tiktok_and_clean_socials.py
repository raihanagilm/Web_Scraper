"""Skrip migrasi database untuk menambahkan kolom `tiktok` dan merelokasi URL media sosial ke kolom yang tepat."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text
from backend.models.base import engine, SessionLocal
from backend.models.lead import Lead
from backend.services.cleaner import clean_social_url


def run_migration():
    print("Memulai migrasi database: kolom tiktok & perapihan medsos...")

    # 1. Tambah kolom tiktok ke tabel leads jika belum ada
    ddl_statement = "ALTER TABLE leads ADD COLUMN IF NOT EXISTS tiktok TEXT AFTER twitter_x;"
    with engine.connect() as conn:
        try:
            conn.execute(text(ddl_statement))
            conn.commit()
            print("  [OK] Kolom tiktok berhasil ditambahkan ke tabel leads.")
        except Exception as e:
            print(f"  [INFO] DDL tiktok -> {e}")

    # 2. Relokasi data sosmed yang salah tempat (misal link Instagram ada di sosmed tapi kolom instagram kosong)
    db = SessionLocal()
    try:
        leads = db.query(Lead).all()
        relocated_count = 0
        operator_cleared = 0

        for l in leads:
            changed = False
            raw_sosmed = (l.sosmed or "").strip()

            # Bersihkan nama_kepsek jika terisi nama operator 'Febri Ayuk Rikmawati'
            if l.nama_kepsek and "febri ayuk" in l.nama_kepsek.lower():
                l.nama_kepsek = ""
                operator_cleared += 1
                changed = True

            if raw_sosmed:
                s_lower = raw_sosmed.lower()
                if "instagram.com" in s_lower:
                    if not l.instagram:
                        l.instagram = clean_social_url(raw_sosmed, "instagram")
                    l.sosmed = ""
                    changed = True
                    relocated_count += 1
                elif "facebook.com" in s_lower or "fb.com" in s_lower:
                    if not l.facebook:
                        l.facebook = clean_social_url(raw_sosmed, "facebook")
                    l.sosmed = ""
                    changed = True
                    relocated_count += 1
                elif "linkedin.com" in s_lower:
                    if not l.linkedin:
                        l.linkedin = clean_social_url(raw_sosmed, "linkedin")
                    l.sosmed = ""
                    changed = True
                    relocated_count += 1
                elif "twitter.com" in s_lower or "x.com" in s_lower:
                    if not l.twitter_x:
                        l.twitter_x = clean_social_url(raw_sosmed, "twitter_x")
                    l.sosmed = ""
                    changed = True
                    relocated_count += 1
                elif "tiktok.com" in s_lower:
                    if not l.tiktok:
                        l.tiktok = clean_social_url(raw_sosmed, "tiktok")
                    l.sosmed = ""
                    changed = True
                    relocated_count += 1

            if changed:
                db.add(l)

        db.commit()
        print(f"  [OK] Berhasil merapikan {relocated_count} URL medsos ke kolom spesifik (Instagram/FB/LinkedIn/X/TikTok).")
        if operator_cleared:
            print(f"  [OK] Berhasil membersihkan {operator_cleared} nama operator yang salah masuk ke kolom Kepala Sekolah.")

    except Exception as e:
        db.rollback()
        print(f"  [ERROR] Gagal backfill/relokasi: {e}")
        raise e
    finally:
        db.close()

    print("Migrasi selesai dengan sukses!")


if __name__ == "__main__":
    run_migration()
