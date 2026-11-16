"""Migrasi Fase 1 — Normalisasi `kategori` & `kota` pada tabel `leads`.

Alur:
1. Buat tabel lookup `categories`/`cities` (idempotent).
2. Backfill dari kolom legacy `leads.kota`/`leads.kategori` (bila kolom masih ada).
3. Isi FK `category_id`/`city_id` di `leads`.
4. Bersihkan duplikat & rebuild unique index → (source, nama_instansi, city_id).
5. Opsional: hapus kolom legacy dengan `--drop-legacy`.

Aman dijalankan ulang (idempotent). DDL MySQL/TiDB.

Usage:
    python -m backend.migrate_phase1
    python -m backend.migrate_phase1 --drop-legacy
"""
import argparse

from sqlalchemy import text

from backend.models import Base, engine

NEW_UNIQUE_INDEX = "uq_lead_source_name_city"


def _col_exists(conn, table: str, col: str) -> bool:
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": col},
    ).scalar() > 0


def _index_exists(conn, table: str, index: str) -> bool:
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
        ),
        {"t": table, "i": index},
    ).scalar() > 0


def _fk_exists(conn, table: str, ref_table: str) -> bool:
    return (
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = :t "
                "AND REFERENCED_TABLE_NAME = :rt"
            ),
            {"t": table, "rt": ref_table},
        ).scalar()
        > 0
    )


def _ensure_fk_columns(conn) -> None:
    """Tambah kolom city_id/category_id + FK bila belum ada (tabel leads lama)."""
    for coln, ref in (("category_id", "categories"), ("city_id", "cities")):
        if not _col_exists(conn, "leads", coln):
            print(f"[migrate] add column leads.{coln} ...")
            conn.execute(text(f"ALTER TABLE leads ADD COLUMN {coln} INT NULL"))
        if not _fk_exists(conn, "leads", ref):
            print(f"[migrate] add FK fk_leads_{coln} -> {ref}(id) ...")
            conn.execute(
                text(
                    f"ALTER TABLE leads ADD CONSTRAINT fk_leads_{coln} "
                    f"FOREIGN KEY ({coln}) REFERENCES {ref}(id) ON DELETE SET NULL"
                )
            )


def _ensure_job_stats_columns(conn) -> None:
    """Tambah kolom items_created/items_updated di scrape_jobs (idempotent).

    Tabel scrape_jobs bisa sudah ada tanpa kolom tsb (daftar sebelum fitur
    "berapa yang terambil"). `create_all` tidak mengubah tabel existing,
    sehingga di-ALTER manual bila kolom belum ada.
    """
    if not _col_exists(conn, "scrape_jobs", "id"):
        return  # tabel belum ada — create_all akan buatnya dengan kolom tsb
    for col, ddl in (
        ("items_created", "INTEGER NOT NULL DEFAULT 0"),
        ("items_updated", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if not _col_exists(conn, "scrape_jobs", col):
            print(f"[migrate] add column scrape_jobs.{col} ...")
            conn.execute(text(f"ALTER TABLE scrape_jobs ADD COLUMN {col} {ddl}"))


def _backfill_lookup(conn, source_col: str, lookup: str) -> None:
    """Salin DISTINCT nilai kolom legacy ke tabel lookup + isi FK-nya."""
    fk_col = {"categories": "category_id", "cities": "city_id"}[lookup]
    print(f"[migrate] backfill {lookup} dari leads.{source_col} ...")

    conn.execute(
        text(
            (
                f"INSERT INTO {lookup} (name) "
                "SELECT DISTINCT TRIM(l.{col}) FROM leads l "
                "WHERE l.{col} IS NOT NULL AND TRIM(l.{col}) <> '' "
                "AND TRIM(l.{col}) <> '-' "
                "AND LOWER(TRIM(l.{col})) NOT IN (SELECT LOWER(name) FROM {lk}) "
                "ON DUPLICATE KEY UPDATE name = {lk}.name"
            ).format(col=source_col, lk=lookup)
        )
    )
    res = conn.execute(
        text(
            (
                f"UPDATE leads l, {lookup} c "
                "SET l.{fk} = c.id "
                "WHERE l.{fk} IS NULL "
                "AND LOWER(TRIM(l.{col})) = LOWER(c.name) "
                "AND TRIM(l.{col}) <> ''"
            ).format(fk=fk_col, col=source_col)
        )
    )
    print(f"[migrate]   {res.rowcount} baris leads terpetakan ke {lookup}")


def _clean_duplicates(conn) -> None:
    """Hapus duplikat (source, nama_instansi, city_id) sebelum index unik dibuat."""
    res = conn.execute(
        text(
            "DELETE l1 FROM leads l1 JOIN leads l2 "
            "ON l1.source = l2.source AND l1.nama_instansi = l2.nama_instansi "
            "AND l1.city_id = l2.city_id AND l1.city_id IS NOT NULL AND l1.id > l2.id"
        )
    )
    if res.rowcount:
        print(f"[migrate] {res.rowcount} duplikat lead dihapus")


def _rebuild_unique_index(conn) -> None:
    """Drop unique index lama berisi kolom `kota`; buat yang baru berbasis city_id."""
    legacy = conn.execute(
        text(
            "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'leads' "
            "AND NON_UNIQUE = 0 AND COLUMN_NAME = 'kota'"
        )
    ).all()
    for (idx,) in legacy:
        print(f"[migrate] drop legacy unique index `{idx}` (masih berisi kolom kota) ...")
        conn.execute(text(f"ALTER TABLE leads DROP INDEX `{idx}`"))

    if not _index_exists(conn, "leads", NEW_UNIQUE_INDEX):
        print(f"[migrate] add unique index {NEW_UNIQUE_INDEX} (source, nama_instansi, city_id) ...")
        conn.execute(
            text(
                f"ALTER TABLE leads ADD UNIQUE INDEX {NEW_UNIQUE_INDEX} "
                "(source, nama_instansi, city_id)"
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalisasi Fase 1: kategori & kota leads")
    parser.add_argument(
        "--drop-legacy",
        action="store_true",
        help="Hapus kolom legacy kota/kategori setelah backfill",
    )
    args = parser.parse_args()

    # 1. Pastikan tabel lookup ada (create_all idempotent — tidak mengubah tabel existing)
    print("[migrate] create tables categories & cities (bila belum ada)...")
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        # 2. Tambah kolom + FK bila tabel leads sudah ada lebih dulu
        if _col_exists(conn, "leads", "id"):
            _ensure_fk_columns(conn)
        # 2b. Kolom audit item stats di scrape_jobs (idempotent ALTER)
        _ensure_job_stats_columns(conn)

        # 3 & 4. Backfill lookup + FK
        if _col_exists(conn, "leads", "kota"):
            _backfill_lookup(conn, "kota", "cities")
        if _col_exists(conn, "leads", "kategori"):
            _backfill_lookup(conn, "kategori", "categories")

        # 4. Dedupe + unique index baru
        _clean_duplicates(conn)
        _rebuild_unique_index(conn)

        # 5. Opsional hapus kolom legacy
        if args.drop_legacy:
            for col in ("kota", "kategori"):
                if _col_exists(conn, "leads", col):
                    print(f"[migrate] drop legacy column `{col}` ...")
                    conn.execute(text(f"ALTER TABLE leads DROP COLUMN `{col}`"))

        s = conn.execute(
            text(
                "SELECT (SELECT COUNT(*) FROM categories) AS cats, "
                "(SELECT COUNT(*) FROM cities) AS cities, "
                "(SELECT COUNT(*) FROM leads WHERE city_id IS NOT NULL) AS leads_city, "
                "(SELECT COUNT(*) FROM leads WHERE category_id IS NOT NULL) AS leads_cat"
            )
        ).one()
        print(
            "[migrate] selesai. "
            f"categories={s.cats}, cities={s.cities}, "
            f"leads city_id={s.leads_city}, category_id={s.leads_cat}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())