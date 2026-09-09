# file.md — Struktur Folder & Jalan Kode (Code Map)

> **Dokumen ini adalah 1 dari 3 dokumen yang WAJIB saling membaca & saling melengkapi.**
>
> | Dokumen | Isi | Pertanyaan yang dijawab |
> |---|---|---|
> | [prd.md](prd.md) | Kebutuhan bisnis, SOP, arsitektur, model data konseptual | **APA & MENGAPA** |
> | **file.md (ini)** | Struktur folder, tanggung jawab tiap file, call graph / alur kode | **DIMANA & BAGAIMANA kodenya jalan** |
> | [database.md](database.md) | Skema detail tabel/kolom/enum, relasi, anti-duplikat | **DATA disimpan di mana** |
>
> **Aturan:** Saat mengubah kode, periksa apakah `file.md` ikut usang. Saat menambah/memindah file,
> perbarui bagian "Pohon Folder" & "Peta Modul" di dokumen ini. Jalankan
> `venv\Scripts\python.exe tools\check_docs_sync.py` untuk verifikasi.

---

## 1. Pohon Folder (terkini)

```
.
├── AGENTS.md                       # Aturan global & workflow wajib untuk agent AI (baca ini)
├── README.md                       # Panduan onboarding manusia
├── prd.md                          # PRD v1.1 — APA & MENGAPA
├── file.md                         # Dokumen ini — struktur folder & jalan kode
├── database.md                     # Skema database & alur data (komplemen file.md)
├── pyproject.toml                  # Konfigurasi entrypoint deployment (Vercel)
├── requirements.txt                # Dependencies Python
├── run.py                          # Entry point dev server: python run.py
├── scraper_gmaps_sekolah.py        # Skrip legacy prototype GMaps (bukan dipakai app)
├── .env.example                    # Template konfigurasi (salurannya ada di .env — JANGAN commit .env)
├── .gitignore
├── .vscode/
│   └── settings.json               # VS Code: interpreter venv + cline.hooks (workflow)
├── tools/
│   ├── add_seed_job_fk_to_scrape_jobs.py # Skrip migrasi DDL seed_job_id FK ON DELETE CASCADE pada scrape_jobs
│   ├── check_docs_sync.py          # Validator sinkronisasi trio dokumen (hook)
│   ├── drop_job_and_vendor_columns.py # Skrip migrasi DDL hapus kolom posisi_rekrutmen, deskripsi_it, penanggung_jawab
│   ├── drop_jobstreet_glints_lpse_sources.py # Skrip migrasi DDL sesuaikan source enum ke gmaps/dapodik
│   ├── migrate_multi_social_and_codes.py # Skrip migrasi DDL multi-medsos & business code ID
│   └── migrate_tiktok_and_clean_socials.py # Skrip migrasi DDL tiktok & pembersihan relokasi sosial media
├── .clinerules/
│   └── rules.md                    # Global rules versi Cline (auto-load tiap sesi)
├── .githooks/
│   └── pre-commit                  # Git hook: jalankan validator sebelum commit
├── backend/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app, lifespan (init_db + seed), mount frontend
│   ├── config.py                   # Settings dari env (pydantic-settings), database_url
│   ├── deps.py                     # require_auth dependency (proteksi seluruh API)
│   ├── seed.py                     # seed_default_user() — buat user admin pertama
│   ├── migrate_phase1.py           # Migrasi DB fase 1: normalisasi kategori/kota → lookup
│   ├── audio/                      # Sound-effect UI frontend (assets statis)
│   ├── controllers/                # LAPIS ROUTER (MVC: Controller)
│   │   ├── __init__.py
│   │   ├── auth_routes.py          # POST /api/auth/login, logout, GET /me
│   │   ├── scrape_routes.py        # /sources (meta enrichment dinamis), POST /scrape, POST /enrich, GET+DELETE /jobs, GET /jobs/{id}/incomplete, cancel, browser-login
│   │   └── lead_routes.py          # /stats, /leads CRUD, /export, /export-csv, /duplicates, /import
│   ├── models/                     # LAPIS MODEL (MVC: Model) — lihat database.md
│   │   ├── __init__.py             # Re-export Base, SessionLocal, get_db, init_db + semua model
│   │   ├── base.py                 # Base, engine (pooling+SSL TiDB), SessionLocal, get_db, init_db
│   │   ├── user.py                 # users
│   │   ├── category.py             # categories (lookup kategori)
│   │   ├── city.py                 # cities (lookup kota)
│   │   ├── lead.py                 # leads (tabel utama) + unique constraint
│   │   ├── scrape_job.py           # scrape_jobs (audit job)
│   │   └── merge_history.py        # merge_history (audit dedup)
│   ├── services/                   # LAPIS BUSINESS LOGIC (MVC: Service)
│   │   ├── __init__.py
│   │   ├── auth_service.py         # bcrypt hash/verify
│   │   ├── browser_profile.py      # Kloning profil login Chrome bawaan (%LOCALAPPDATA%) ke worker Playwright
│   │   ├── cleaner.py              # normalize_phone → 628, nama, website, email, junk domain
│   │   ├── code_generator.py       # Generator business code ID terstruktur: LD-*, KAT-*, K-*
│   │   ├── storage_service.py      # upsert_lead, save_raw_items, query_leads, job helpers
│   │   ├── job_manager.py          # JobManager: thread background, progress, cancel, registry, watchdog reconcile
│   │   ├── enrichment_service.py   # match & merge enrichment (fuzzy), find_incomplete_leads
│   │   ├── dedup_service.py        # fingerprint duplikat + resolve (keep/merge/delete_all)
│   │   ├── exporter.py             # export_leads (.xlsx), export_leads_csv
│   │   ├── importer.py             # import_csv_text (kontingensi sumber diblokir)
│   │   └── scrapers/               # MESIN SCRAPER
│   │       ├── __init__.py
│   │       ├── base.py             # BaseScraper: rate_limit 1–3s, cancel, emit_progress
│   │       ├── gmaps.py            # GmapsScraper (SEED semua segmen) + CATEGORY_KEYWORDS
│   │       ├── dapodik.py          # DapodikScraper (enrichment Sekolah: NPSN, kepsek)
│   │       └── google.py           # GoogleScraper (enrichment Kontak Umum: telp/WA, email, website, sosmed via DuckDuckGo/Web)
│   ├── data/
│   │   ├── exports/                # Hasil export .xlsx / file CSV (dynamic, jangan di-hook)
│   │   └── uploads/                # Upload impor CSV (optional)
├── frontend/                       # LAPIS VIEW (MVC: View) — single-page
│   ├── index.html                  # Login + app shell (dashboard/scrape/enrichment/results/dedup)
│   ├── app.js                      # Logika frontend: fetch API, render, WebSocket progress
│   ├── style.css                   # Tema hijau Edtekno (PRD §11)
│   ├── css/                        # (cadangan)
│   └── js/                         # (cadangan)
└── tests/
    ├── test_auth.py                        # Smoke test auth
    ├── test_browser_profile_and_progress.py # Unit test browser profile & progress preservation
    ├── test_codes_and_socials.py           # Unit test kode ID terstruktur & multi-sosmed
    ├── test_enrichment_core.py             # Unit test core enrichment & job management
    └── test_google_enrichment.py           # Unit test scraper Google & enrichment kontak umum
```
---

## 2. Jalan Kode — Request Lifecycle (API)

Semua endpoint WAJIB login (`backend/deps.py::require_auth`) kecuali `POST /api/auth/login`.
Frontend memanggil API via `fetch` di `frontend/app.js`.

### 2.1 Login
```
frontend/app.js --POST--> /api/auth/login
  → backend/controllers/auth_routes.py::login
  → backend/services/auth_service.py::verify_password (bcrypt, tabel users)
  → request.session["user_id"] (signed cookie, HttpOnly) — backend/main.py::SessionMiddleware
```

### 2.2 Mulai Scrape (seed/enrichment)
```
POST /api/scrape  (atau /api/enrich)
  → backend/controllers/scrape_routes.py::start_scrape / start_enrichment
  → backend/services/job_manager.py::job_manager.start
      ├─ store.create_job → scrape_jobs (status=pending)
      ├─ ScraperRegistry.get_class(source) → pilih kelas scraper
      │    (dapodik: kirim daftar target nama sekolah dari find_incomplete_leads)
      ├─ scraper.set_progress_callback(...)
      └─ threading.Thread(_run) — background
  _run → scraper.run() → raw_items
       ├─ Seed (gmaps): store.save_raw_items (upsert tiap item) → leads
       └─ Enrichment (dapodik/google):
            enrichment_service.match_and_merge(...) — cocokkan hasil ke lead seed
            yang sudah di DB (filter kategori+kota & field kosong), isi HANYA field
            kosong, TIDAK membuat lead baru; progress = jumlah lead yang diisi.
       → store.update_job status=completed/progress/total_found

DELETE /api/jobs/{id} → hapus 1 baris riwayat job (400 jika job masih berjalan — Stop dulu).
```

**UI — Enrichment dipisah ke menu sendiri (moda monitor), aksi ada di Riwayat Job:**
- Halaman **Enrichment** (sidebar): menampilkan "Field per Sumber" + **Riwayat Enrichment** (job non-gmaps), stop/hapus baris, serta dropdown **📋 Data Belum Lengkap** (dengan jabaran nama instansi/lokasi & tombol ✏️ Isi Manual).
- **Tombol ⚡ Enrich** per baris job seed (`gmaps`) yang terminal → langsung mengarahkan (direct) ke form menu Enrichment dengan kategori & kota otomatis terisi.
- **Tombol ↻ Ulangi** per baris terminal → re-run scrape/enrichment (aman: upsert; enrichment isi field kosong).
- Kolom **Ditemukan** menampilkan format informatif misal `98/100 dari 120` (terambil / target dari total listing GMaps).

### 2.3 Progress realtime & watchdog status
- **Opsi form Enrichment dinamis**: `GET /api/enrich/options` → Kategori & Kota DISTINCT dari tabel `leads` (data seed gmaps) via `storage_service.list_categories_with_cities`. Frontend menampilkan **dropdown Kategori** + combobox Kota (searchable) yang terisi dinamis; saat Kategori dipilih, daftar Kota otomatis tersaring ke kota yang punya data kategori tsb (mencegah enrichment kombinasi kosong).
Scraper memanggil `emit_progress(progress, total, message)` → callback `_on_progress`
→ `store.update_job` + `store.append_job_log` (disimpan ke kolom `log`, dipotong 4000 chars).
Frontend memantau via polling `/api/jobs` (**WebSocket /ws belum dipasang** — progres dibaca polling).

- **Persentase progress** dihitung di frontend: `(total_found / max_results) × 100`, cap 0–100 —
  pembagi mengikuti input "Maks. hasil" user, bukan 100 hardcoded. Lihat `app.js::jobProgressPct`.
- **Watchdog status**: `GET /api/jobs` & `/api/jobs/{id}` memanggil `job_manager.reconcile(db)`
  yang mengoreksi job stuck `running` → `error` (+ log alasan) ketika: server restart (job tak
  ada di memori), thread scraper mati, browser Chrome ditutup manual (`scraper.is_alive()`),
  atau tanpa progres > `settings.job_stale_seconds` (default 600 dtk, dianggap hang).
  Tombol Stop hanya dirender untuk status `running/pending`; setelah dikoreksi otomatis hilang.

### 2.4 Query/Filter/Update Leads
```
GET /api/leads?search=&source=&kota=&category=&status=&page=&size=&sort_by=&sort_dir=
  → backend/controllers/lead_routes.py::list_leads
  → backend/services/storage_service.py::query_leads
      ├─ JOIN categories & cities (outer) agar bisa sort/filter nama lookup
      ├─ search: nama_instansi/alamat/email/kategori/kota (ilike)
      └─ sort_by di-whitelist via SORTABLE_COLUMNS (anti SQL-injection)

PATCH /api/leads/{id}  → storage_service.update_lead_full (kategori/kota di-resolve ke FK)
DELETE /api/leads/{id} → storage_service.delete_leads
```

### 2.5 Dedup / Merge
```
GET  /api/duplicates
  → backend/services/dedup_service.py::find_duplicate_groups
      _lead_fingerprints → key (nama+kota, npsn, phone, email, domain)
      _score_pair → skor kemiripan; hanya grup dengan >= 2 member & score >= 1
POST /api/duplicates/resolve
  → dedup_service.resolve_group (action: keep | merge | delete_all)
  → selalu catat MergeHistory (group_key, action, winner_id, member_ids, snapshots)
```

### 2.6 Export / Import
```
GET  /api/export      → exporter.export_leads → .xlsx (styling + dropdown status)
GET  /api/export-csv  → exporter.export_leads_csv (delimiter ';', BOM utf-8, anti formula-injection)
POST /api/import      → importer.import_csv_text → save_raw_items (auto clean + dedup)
```
---

## 3. Jalan Kode — Pipeline Scraping (Seed → Enrichment)

Alur konseptual PRD v1.1 (lihat [prd.md](prd.md) §6.2); implementasi aktual di backend:

```
1. SEED — GMaps (gmaps.py::GmapsScraper.run)
     query {kategori} di {kota} → kumpulkan leads dasar
   └─ hasil TIDAK langsung simpan sendiri — dikembalikan list[dict] raw

2. PERSIST — job_manager._run
   └─ store.save_raw_items(db, raw_items, source)
        ├─ clean_lead()  → cleaner.py (telp→628, email valid, junk website dibuang)
        ├─ upsert_lead() → unique (source, nama_instansi, city_id)
        │    ├─ ditemukan → isi HANYA field kosong/placeholder (tidak menimpa)
        │    └─ tidak ada → insert baru
        └─ kategori/kota string → auto-create lookup categories/cities → FK

3. ENRICHMENT (opsional, lazy) — POST /api/enrich
   ├─ kategori BEBAS (dinamis, input + datalist dari DB) — bukan lagi 4 pilihan hardcoded
   ├─ sumber enrichment dipilih MANUAL via dropdown yang dirender dari /api/sources
   │  (sumber aktif = terdaftar di SCRAPER_REGISTRY; dapodik tampil disabled sampai M2 selesai),
   │  atau Auto → get_enrichment_sources(category); 400 bila Auto tanpa mapping
   └─ scraper pendukung run → enrichment_service.match_and_merge
        ├─ find_incomplete_leads → lead seed dengan field pendukung kosong
        ├─ _match_score → fuzzy nama+kota (threshold 0.75 kota sama / 0.9 tanpa kota),
        │                NPSN (+3), domain website (+3), email (+3)
        └─ cocok → isi field kosong saja; tidak cocok → log "review manual" (TIDAK di-save)

4. DEDUP MANUAL — GUI Review Duplikat → dedup_service (lihat §2.5)
```

> **Catatan Dapodik:** `dapodik.py` bersifat khusus — situs Kemdikbud tidak punya
> pencarian per kategori, jadi scraper menerima **daftar nama sekolah** (target)
> dari `job_manager.start(source='dapodik')` (lead seed gmaps yang NPSN/kepsek-nya
> masih kosong, difilter kategori+kota), lalu mencari NPSN + Kepala Sekolah
> per nama. Terdaftar aktif di `SCRAPER_REGISTRY`.

## 4. Peta Modul — Tanggung Jawab per File (Call Graph Inti)

| File | Peran dalam jalan kode |
|---|---|
| `backend/main.py` | Merakit FastAPI: lifespan → `init_db()` + `seed_default_user()`; SessionMiddleware; mount `/audio` lalu `/` (frontend) di akhir |
| `backend/config.py` | Baca env `.env`; `database_url` = `mysql+pymysql://...`; default delay scraper 1–3 detik |
| `backend/models/base.py` | Engine SQLAlchemy + pooling `pool_recycle=1800`, `pool_pre_ping` (mitigasi TiDB idle disconnect), SSL `connect_args` |
| `backend/services/job_manager.py` | **Orkestrator scraping**: `SCRAPER_REGISTRY`, `ENRICHMENT_SOURCES`, thread background, cancel, `reconcile()` watchdog (koreksi job stuck `running` → `error` saat proses/browser mati/hang). `_run` bercabang: seed → `save_raw_items`; enrichment → `match_and_merge` |
| `backend/services/storage_service.py` | Gerbang utama tulis/baca `leads`; `LEAD_FIELDS`, `FK_FIELDS`, `SORTABLE_COLUMNS`; helper job (`create_job`, `update_job`, `delete_job`, `list_jobs`); opsi dropdown (`list_categories`, `list_cities`, `list_categories_with_cities` = DISTINCT Kategori→Kota dari data seed) |
| `backend/services/auth_service.py` | bcrypt hash/verify |
| `backend/services/browser_profile.py` | Kloning profil login Chrome bawaan (%LOCALAPPDATA%) ke worker Playwright tanpa bentrok process lock |
| `backend/services/cleaner.py` | Normalisasi wajib sebelum DB: telp→`628...`, nama, website domain, validasi email, buang CDN (`ggpht.com`, dll) |
| `backend/services/code_generator.py` | Generator format kode bisnis unik: `LD-{KATEGORI}-{001}`, `KAT-{KATEGORI}-{001}`, `K-{KOTA}-{001}` |
| `backend/services/enrichment_service.py` | **Core logic enrichment**: `find_incomplete_leads` (target seed gmaps difilter kategori+kota & field kosong, `limit`=maks hasil), `match_and_merge` (isi hanya field kosong, tidak replace, tidak buat lead baru), `ENRICHMENT_FIELDS`, `CATEGORY_ENRICHMENT_SOURCES`, threshold fuzzy |
| `backend/services/dedup_service.py` | Fingerprint & grouping duplikat; `resolve_group` → `merge_history` |
| `backend/services/scrapers/base.py` | `BaseScraper`: `rate_limit()` = `random.uniform(min, max)` (SOP 1–3 detik), `cancel()`, `emit_progress()` |
| `backend/services/scrapers/gmaps.py` | Seed semua segmen; `CATEGORY_KEYWORDS`, `INVALID_SCHOOL` regex, `browser_status`/`browser_login`, `is_alive()` (deteksi jendela Chrome ditutup) |
| `backend/services/scrapers/dapodik.py` | **Enrichment Sekolah**: cari NPSN+kepsek per nama sekolah (target dari JobManager) di referensi.data.kemdikbud.go.id; output → `match_and_merge` |
| `backend/services/scrapers/google.py` | **Enrichment Kontak Umum (Google/Web)**: cari no. WA/telp, email, website, sosmed (Instagram) per target via DuckDuckGo HTML parser; output → `match_and_merge` |
| `backend/services/exporter.py` | `BASE_COLUMNS` + `EXTRA_COLUMNS` per sumber → XLSX/CSV |
| `backend/services/importer.py` | Parser CSV label Indonesia → field; kontingensi ketika sumber diblokir |
| `frontend/app.js` | Menghubungkan UI (`index.html`) ke seluruh API + polling job + tombol Stop; Riwayat Kategori (localStorage, unique, klik-isi); Hapus riwayat job (`DELETE /api/jobs/{id}` + cascade enrichment otomatis); rumus progress `(found/max)×100` via `jobProgressPct` (freeze saat Stop/cancelled); format `formatJobResult` (`Math.max(progress, taken)`); **Pemisahan riwayat job**: Scrape khusus gmaps, Enrichment khusus non-gmaps; tombol ⚡ Enrich direct ke form Enrichment; drawer/accordion **📋 Data Belum Lengkap** di Riwayat Enrichment + toolbar **⚡ Lengkapi Otomatis dengan Sumber Lain** + edit manual via `openEditModal` |
| `tests/test_auth.py` | Smoke test alur login |

---

## 5. Konvensi Yang Harus Diikuti (kode baru)

1. **Pola MVC ketat** — View (`frontend/`) → Controller (`backend/controllers/`) → Service (`backend/services/`) → Model (`backend/models/`).
2. **Scraper baru** → buat di `backend/services/scrapers/<nama>.py`, inherit `BaseScraper`, lalu daftarkan di `SCRAPER_REGISTRY` dan `ENRICHMENT_SOURCES` di `job_manager.py`.
3. **Jangan bypass Cleaner** — semua data masuk DB lewat `clean_lead()` + `upsert_lead()`.
4. **Kategori/kota = FK lookup** — selalu resolve ke `categories`/`cities` (jangan kolom string baru).
5. **Rate-limit 1–3 detik** — wajib `self.rate_limit()` antar request scraper.
6. **Semua endpoint = login wajib** — tambahkan `Depends(require_auth)`.
7. **Field baru di `leads`** → update juga `LEAD_FIELDS`, `SORTABLE_COLUMNS`, `database.md`, dan label export di `exporter.py`.

---

## 6. Menjaga Dokumen Tetap Sinkron

Jalankan validator: `venv\Scripts\python.exe tools\check_docs_sync.py`
- Script ini membandingkan **pohon folder aktual** dengan daftar file di dokumen ini,
  **model SQLAlchemy** dengan tabel/kolom di [database.md](database.md), dan
  **cross-reference** ketiga dokumen ([prd.md](prd.md) ↔ file.md ↔ database.md).
- Hasil keluar non-zero → ada drift → perbaiki dokumen **sebelum** commit.

Alur dokumen: **prd.md (apa/mengapa) → file.md (di mana / jalannya) → database.md (data)**.
---

## 7. Daftar File untuk Validator (Machine Index)

Blok di bawah dibaca oleh `tools/check_docs_sync.py` untuk membandingkan **dokumen ↔ file aktual**.
Saat menambah/memindah/menghapus file, **perbarui blok ini** (dan pohon folder di §1).

<!-- FILE-INDEX-START -->
AGENTS.md
README.md
prd.md
file.md
database.md
pyproject.toml
requirements.txt
run.py
scraper_gmaps_sekolah.py
.env.example
.gitignore
.vscode/settings.json
tools/add_seed_job_fk_to_scrape_jobs.py
tools/check_docs_sync.py
tools/clean_invalid_generic_links.py
tools/drop_job_and_vendor_columns.py
tools/drop_jobstreet_glints_lpse_sources.py
tools/migrate_multi_social_and_codes.py
tools/migrate_tiktok_and_clean_socials.py
.clinerules/rules.md
.githooks/pre-commit
backend/config.py
backend/deps.py
backend/main.py
backend/migrate_phase1.py
backend/seed.py
backend/controllers/__init__.py
backend/controllers/auth_routes.py
backend/controllers/lead_routes.py
backend/controllers/scrape_routes.py
backend/models/__init__.py
backend/models/base.py
backend/models/category.py
backend/models/city.py
backend/models/lead.py
backend/models/merge_history.py
backend/models/scrape_job.py
backend/models/user.py
backend/services/__init__.py
backend/services/auth_service.py
backend/services/browser_profile.py
backend/services/cleaner.py
backend/services/code_generator.py
backend/services/dedup_service.py
backend/services/enrichment_service.py
backend/services/exporter.py
backend/services/importer.py
backend/services/job_manager.py
backend/services/storage_service.py
backend/services/scrapers/__init__.py
backend/services/scrapers/base.py
backend/services/scrapers/dapodik.py
backend/services/scrapers/gmaps.py
backend/services/scrapers/google.py
frontend/app.js
frontend/index.html
frontend/style.css
tests/test_auth.py
tests/test_browser_profile_and_progress.py
tests/test_codes_and_socials.py
tests/test_enrichment_core.py
tests/test_google_enrichment.py
<!-- FILE-INDEX-END -->