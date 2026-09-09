# database.md — Skema Database & Alur Data

> **Dokumen ini adalah 1 dari 3 dokumen yang WAJIB saling membaca & saling melengkapi.**
>
> | Dokumen | Isi |
> |---|---|
> | [prd.md](prd.md) | Kebutuhan bisnis & model data konseptual (PRD §9) |
> | [file.md](file.md) | Struktur folder & jalan kode (tabel model → file `backend/models/*.py`) |
> | **database.md (ini)** | Skema detail: tabel, kolom, tipe, enum, unique constraint, relasi |
>
> **Aturan:** Jika Anda mengubah model di `backend/models/*.py`, wajib memperbarui dokumen ini
> (tabel yang bersesuaian) DAN `LEAD_FIELDS`/`SORTABLE_COLUMNS` di `storage_service.py`.
> Verifikasi: `venv\Scripts\python.exe tools\check_docs_sync.py`.

---

## 1. Ringkasan & Relasi Antar Tabel

DB: **MySQL (TiDB Cloud)** — `mysql+pymysql://` (lihat `backend/config.py`), engine di `backend/models/base.py`.

```
users ─────────────┐  (auth login)
                   │
categories ────────┼──┐  FK kategori (lookup, auto-create)
                   │  │
leads ─────────────┼──┼── FK city_id → cities.id (lookup, auto-create)
                   │  │
cities ────────────┘  └── category_id → categories.id
                   │
scrape_jobs ───────┘  (audit job, tidak ada FK ke leads)
                   │
merge_history ────────┘ (audit dedup; member_ids/field_choices JSON)
```

- **Master data:** `categories`, `cities` — dinormalisasi dari kolom string legacy `kategori`/`kota`,
  di-*auto-create* saat `upsert_lead` (case-insensitive, anti-duplikat nama).
- **Antar-lead** tidak ada FK langsung; hubungan digabung lewat *fingerprint* di
  `dedup_service.py` / `enrichment_service.py` (logika, bukan FK DB).

---

## 2. Tabel: users

Auth login. Di-seed otomatis oleh `backend/seed.py::seed_default_user` (username/password dari `.env`).

| Kolom | Tipe | Constraint / Default | Keterangan |
|---|---|---|---|
| **id** | INT | PK, autoincrement | |
| **username** | VARCHAR(50) | UNIQUE, NOT NULL | login id |
| **password_hash** | VARCHAR(255) | NOT NULL | bcrypt (`auth_service.hash_password`) |
| **full_name** | VARCHAR(100) | default "" | |
| **created_at** | DATETIME | default utcnow | |
| **updated_at** | DATETIME | default utcnow, onupdate | |
---

## 3. Tabel: categories

Master data kategori lead (lookup FK dari `leads.category_id`).

| Kolom | Tipe | Constraint / Default | Keterangan |
|---|---|---|---|
| **id** | INT | PK, autoincrement | |
| **kode** | VARCHAR(50) | INDEX, NULLABLE | Kode unik bisnis, contoh: `KAT-SEKOLAH-001` |
| **name** | VARCHAR(100) | UNIQUE, NOT NULL, INDEX | contoh: sekolah, umkm, kafe, it |
| **created_at** | DATETIME | default utcnow | |

---

## 4. Tabel: cities

Master data kota/kabupaten (lookup FK dari `leads.city_id`).

| Kolom | Tipe | Constraint / Default | Keterangan |
|---|---|---|---|
| **id** | INT | PK, autoincrement | |
| **kode** | VARCHAR(50) | INDEX, NULLABLE | Kode unik bisnis, contoh: `K-SALATIGA-001` |
| **name** | VARCHAR(100) | UNIQUE, NOT NULL, INDEX | contoh: salatiga, semarang |
| **province** | VARCHAR(100) | default "" | |
| **created_at** | DATETIME | default utcnow | |
---

## 5. Tabel: leads

**Tabel utama.** Satu baris = satu lead (instansi/bisnis). Data ditambah lewat
`storage_service.upsert_lead` (selalu lewat `clean_lead` di `cleaner.py`).

| Kolom | Tipe | Constraint / Default | Keterangan |
|---|---|---|---|
| **id** | INT | PK, autoincrement | ID internal database |
| **kode** | VARCHAR(50) | INDEX, NULLABLE | Kode bisnis terstruktur, format `LD-{KATEGORI}-{001}` |
| **source** | ENUM | NOT NULL — `gmaps`/`dapodik`/`lpse`/`jobstreet`/`glints` | dari mana data asal |
| **priority** | ENUM | NOT NULL, default `medium` — `high`/`medium` | per segmen pasar |
| **nama_instansi** | VARCHAR(255) | NOT NULL, default "" | nama sekolah/PT/bisnis |
| **category_id** | INT | FK → categories.id, ON DELETE SET NULL, NULLABLE | di-resolve dari string `kategori` |
| **telp** | VARCHAR(20) | default "" | normalisasi `628...` |
| **email** | TEXT | default "" | multi-email dipisahkan koma |
| **alamat** | TEXT | default "" | |
| **city_id** | INT | FK → cities.id, ON DELETE SET NULL, NULLABLE | di-resolve dari string `kota` |
| **link_gmaps** | TEXT | default "" | |
| **website** | TEXT | default "" | domain CDN dibuang di cleaner |
| **instagram** | TEXT | default "" | URL / akun Instagram resmi |
| **facebook** | TEXT | default "" | URL Fanpage / profil Facebook |
| **linkedin** | TEXT | default "" | URL Profil / company LinkedIn |
| **twitter_x** | TEXT | default "" | URL Akun Twitter / X |
| **tiktok** | TEXT | default "" | URL / akun TikTok resmi |
| **sosmed** | TEXT | default "" | Akun medsos lainnya / fallback umum |
| **link_source** | TEXT | default "" | |
| **status** | ENUM | default `New` — `New`/`Contacted`/`Follow Up`/`Deal`/`Rejected` | pipeline sales |
| **npsn** | VARCHAR(20) | default "" | enrichment Dapodik |
| **nama_kepsek** | VARCHAR(200) | default "" | enrichment Dapodik |
| **created_at** | DATETIME | default utcnow | |
| **updated_at** | DATETIME | default utcnow, onupdate | |

**Unique constraint:** `uq_lead_source_name_city` = `(source, nama_instansi, city_id)`
→ dasar **anti-duplikat Lapis 1** (PRD §10). `upsert_lead` memanfaatkannya: bila key cocok,
field kosong diisi data baru; tidak menimpa data yang sudah terisi.

---

## 6. Tabel: scrape_jobs

Audit setiap job scraping (seed/enrichment). `category`/`city` sengaja denormalisasi sebagai snapshot.

| Kolom | Tipe | Constraint / Default | Keterangan |
|---|---|---|---|
| **id** | VARCHAR(36) | PK | Format ringkas: `SCRP_{kategori[:14]}_{YYYYMMDD_HHMMSS}` (atau UUID legacy) |
| **source** | VARCHAR(50) | NOT NULL | gmaps/dapodik/jobstreet/glints/lpse |
| **category** | VARCHAR(100) | default "" | snapshot kategori saat job jalan |
| **city** | VARCHAR(100) | default "" | snapshot kota |
| **max_results** | INT | default 50 | |
| **status** | ENUM | default `pending` — `pending`/`running`/`completed`/`cancelled`/`error` | |
| **progress** | INT | default 0 | |
| **total_found** | INT | default 0 | |
| **items_created** | INT | NOT NULL, default 0 | **berapa yang benar-benar terambil**: seed = lead baru dibuat; enrichment = lead yang field-nya terisi (matched) |
| **items_updated** | INT | NOT NULL, default 0 | seed: lead existing yang di-update via upsert (enrichment: 0) |
| **log** | TEXT | default "" | dipotong 4000 chars (`append_job_log`) |
| **started_at** | DATETIME | NULLABLE | |
| **finished_at** | DATETIME | NULLABLE | |
---

## 7. Tabel: merge_history

Audit aksi review duplikat (PRD §10 Lapis 2). JSON snapshot sebelum data dihapus/digabung.

| Kolom | Tipe | Constraint / Default | Keterangan |
|---|---|---|---|
| **id** | INT | PK, autoincrement | |
| **group_key** | VARCHAR(255) | NOT NULL | fingerprint key grup duplikat |
| **action** | ENUM | NOT NULL — `keep`/`merge`/`delete_all` | |
| **winner_id** | INT | NULLABLE | lead yang dipertahankan |
| **member_ids** | JSON | NOT NULL, default [] | semua member grup |
| **field_choices** | JSON | NULLABLE | pilihan per-field saat merge |
| **snapshot_deleted** | JSON | NULLABLE | salinan data yang dihapus |
| **created_at** | DATETIME | default utcnow | |

---

## 8. Enum (ringkasan)

| Enum | Nilai |
|---|---|
| `source_enum` | `gmaps`, `dapodik`, `lpse`, `jobstreet`, `glints` |
| `priority_enum` | `high`, `medium` |
| `status_enum` | `New`, `Contacted`, `Follow Up`, `Deal`, `Rejected` |
| `job_status_enum` | `pending`, `running`, `completed`, `cancelled`, `error` |
| `merge_action_enum` | `keep`, `merge`, `delete_all` |

---

## 9. Pemetaan Segmen → Enrichment Field (data yang mengalir ke `leads`)

| Segmen (kategori) | Seed | Enrichment | Field yang diisi |
|---|---|---|---|
| umum / instansi (rumah sakit, hotel, kafe, dll) | gmaps | google | `telp`, `email`, `website`, `sosmed` |
| sekolah | gmaps | dapodik, google | `npsn`, `nama_kepsek`, `email`, `link_source` / kontak umum |
| corporate / perusahaan | gmaps | jobstreet, glints, google | `posisi_rekrutmen`, `deskripsi_it` / kontak umum |
| umkm / retail / resto / kafe | gmaps | google, jobstreet, glints | `telp`, `email`, `website`, `sosmed`, `posisi_rekrutmen`, `deskripsi_it` |
| vendor / kontraktor / b2g | gmaps | lpse, google | `penanggung_jawab` / kontak umum |

Referensi: [prd.md](prd.md) §5.1 & §5.3, `enrichment_service.ENRICHMENT_FIELDS`,
`job_manager.ENRICHMENT_SOURCES`.

---

## 10. Alur Data Ringkas

```
seeder (gmaps) ──raw_items──▶ cleaner.clean_lead
                                 │  telp→628, email valid, website non-CDN
                                 ▼
                          storage.upsert_lead
                            ├─ resolve kategori/kota → FK lookup (auto-create)
                            ├─ match unique (source, nama_instansi, city_id)
                            │    ├─ ada → isi field kosong saja
                            │    └─ baru → INSERT
                            ▼
                          leads (MySQL/TiDB)
                            ▲
enrichment (dapodik/jobstreet/glints/lpse) ──match_and_merge──┘
                            │  isi field kosong; non-match di-log (tidak disimpan)
                            ▼
                   Review Duplikat (dedup_service) → merge_history
                            ▼
                    Export (exporter) → .xlsx/.csv
```