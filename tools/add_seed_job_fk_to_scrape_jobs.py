"""
Skrip migrasi database: Menambahkan kolom seed_job_id dan foreign key ON DELETE CASCADE ke tabel scrape_jobs.
Aman dijalankan berulang (idempoten).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from backend.models.base import engine


def migrate_seed_job_fk():
    print("Memeriksa skema tabel scrape_jobs...")

    with engine.connect() as conn:
        res = conn.execute(text("SHOW COLUMNS FROM scrape_jobs"))
        existing_cols = {row[0] for row in res.fetchall()}

        if "seed_job_id" not in existing_cols:
            print("Menambahkan kolom 'seed_job_id' ke tabel scrape_jobs...")
            conn.execute(text("ALTER TABLE scrape_jobs ADD COLUMN `seed_job_id` VARCHAR(36) NULL"))
            print("Kolom 'seed_job_id' berhasil ditambahkan.")
        else:
            print("Kolom 'seed_job_id' sudah ada.")

        # Cek apakah foreign key sudah terpasang
        fk_res = conn.execute(text("""
            SELECT CONSTRAINT_NAME 
            FROM information_schema.KEY_COLUMN_USAGE 
            WHERE TABLE_NAME = 'scrape_jobs' 
              AND COLUMN_NAME = 'seed_job_id' 
              AND REFERENCED_TABLE_NAME = 'scrape_jobs'
        """))
        existing_fks = [row[0] for row in fk_res.fetchall()]

        if not existing_fks:
            print("Menambahkan index dan foreign key constraint 'fk_scrape_jobs_seed_job'...")
            # Tambahkan index terlebih dahulu bila belum ada
            try:
                conn.execute(text("ALTER TABLE scrape_jobs ADD INDEX `idx_scrape_jobs_seed_job_id` (`seed_job_id`)"))
            except Exception as e:
                print(f"Catatan indeks: {e}")

            try:
                conn.execute(text("""
                    ALTER TABLE scrape_jobs 
                    ADD CONSTRAINT `fk_scrape_jobs_seed_job` 
                    FOREIGN KEY (`seed_job_id`) REFERENCES `scrape_jobs`(`id`) 
                    ON DELETE CASCADE
                """))
                print("Foreign key 'fk_scrape_jobs_seed_job' dengan ON DELETE CASCADE berhasil dipasang.")
            except Exception as e:
                print(f"Peringatan pemasangan FK: {e}")
        else:
            print(f"Foreign key sudah terpasang: {existing_fks}")

        # Backfill otomatis: untuk job enrichment yang belum punya seed_job_id,
        # pasangkan dengan job gmaps terbaru yang memiliki kategori & kota yang sama
        print("Melakukan auto-linking seed_job_id untuk job enrichment yang sudah ada...")
        try:
            conn.execute(text("""
                UPDATE scrape_jobs e
                JOIN (
                    SELECT s.id as gmaps_job_id, s.category, s.city
                    FROM scrape_jobs s
                    WHERE s.source = 'gmaps'
                    ORDER BY s.started_at DESC
                ) seed ON seed.category = e.category AND seed.city = e.city
                SET e.seed_job_id = seed.gmaps_job_id
                WHERE e.source != 'gmaps' AND (e.seed_job_id IS NULL OR e.seed_job_id = '')
            """))
        except Exception as e:
            print(f"Catatan auto-linking: {e}")

        conn.commit()
    print("Migrasi seed_job_fk selesai dengan sukses.")


if __name__ == "__main__":
    migrate_seed_job_fk()
