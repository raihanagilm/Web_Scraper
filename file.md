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
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app, lifespan (init_db + seed), mount public
│   ├── config.py                   # Settings dari env (pydantic-settings), database_url
│   ├── Controllers/                # LAPIS CONTROLLER (Universal Laravel Pattern)
│   │   ├── __init__.py
│   │   ├── AuthController.py       # Logika auth (login, logout, me)
│   │   ├── ScrapeController.py     # Logika scrape, jobs, enrichment, monitoring
│   │   └── LeadController.py       # Logika leads CRUD, stats, export, dedup, import
│   ├── Middleware/                 # LAPIS MIDDLEWARE
│   │   ├── __init__.py
│   │   └── auth_middleware.py      # require_auth dependency (proteksi seluruh API)
│   ├── Models/                     # LAPIS MODEL (SQLAlchemy Models) — lihat database.md
│   │   ├── __init__.py             # Re-export Base, SessionLocal, get_db, init_db + semua model
│   │   ├── base.py                 # Base, engine (pooling+SSL TiDB), SessionLocal, get_db, init_db
│   │   ├── user.py                 # users
│   │   ├── category.py             # categories (lookup kategori)
│   │   ├── city.py                 # cities (lookup kota)
│   │   ├── lead.py                 # leads (tabel utama) + unique constraint
│   │   ├── scrape_job.py           # scrape_jobs (audit job)
│   │   └── merge_history.py        # merge_history (audit dedup)
│   └── Services/                   # LAPIS BUSINESS LOGIC (Services)
│       ├── __init__.py
│       ├── auth_service.py         # bcrypt hash/verify
│       ├── browser_profile.py      # Kloning profil login Chrome ke worker Playwright
│       ├── cleaner.py              # normalize_phone → 628, nama, website, email, junk domain
│       ├── code_generator.py       # Generator business code ID terstruktur: LD-*, KAT-*, K-*
│       ├── storage_service.py      # upsert_lead, save_raw_items, query_leads, job helpers
│       ├── job_manager.py          # JobManager: thread background, progress, cancel, registry, watchdog reconcile
│       ├── enrichment_service.py   # match & merge enrichment (fuzzy), find_incomplete_leads
│       ├── dedup_service.py        # fingerprint duplikat + resolve (keep/merge/delete_all)
│       ├── exporter.py             # export_leads (.xlsx), export_leads_csv
│       ├── importer.py             # import_csv_text (kontingensi sumber diblokir)
│       └── scrapers/               # MESIN SCRAPER
│           ├── __init__.py
│           ├── base.py             # BaseScraper: rate_limit 1–3s, cancel, emit_progress
│           ├── gmaps.py            # GmapsScraper (SEED semua segmen) + CATEGORY_KEYWORDS
│           ├── dapodik.py          # DapodikScraper (enrichment Sekolah: NPSN, kepsek)
│           └── google.py           # GoogleScraper (enrichment Kontak Umum: telp/WA, email, website, sosmed)
├── routes/                         # LAPIS ROUTER
│   ├── __init__.py
│   ├── api.py                      # Aggregator router (/api)
│   ├── auth.py                     # POST /api/auth/login, logout, GET /me
│   ├── scrape.py                   # /sources, POST /scrape, POST /enrich, jobs, browser-status, browser-login
│   └── lead.py                     # /stats, /leads CRUD, /export, /export-csv, /duplicates, /import
├── database/
│   ├── migrations/                 # Migrasi DDL & normalisasi database
│   │   ├── __init__.py
│   │   └── migrate_phase1.py       # Migrasi DB fase 1: normalisasi kategori/kota → lookup
│   └── seeders/                    # Database Seeders
│       ├── __init__.py
│       └── user_seeder.py          # seed_default_user() — buat user admin pertama
├── public/                         # LAPIS VIEW (Static Assets & UI) — single-page
│   ├── index.html                  # Login + app shell (dashboard/scrape/enrichment/results/dedup)
│   ├── app.js                      # Logika frontend: fetch API, render, WebSocket progress
│   ├── style.css                   # Tema hijau Edtekno (PRD §11)
│   ├── favicon.svg                 # Ikon resmi favicon browser
│   └── audio/                      # Sound-effect UI frontend (assets statis)
└── tests/
    ├── test_auth.py                        # Smoke test auth
    ├── test_browser_profile_and_progress.py # Unit test browser profile & progress preservation
    ├── test_codes_and_socials.py           # Unit test kode ID terstruktur & multi-sosmed
    ├── test_enrichment_core.py             # Unit test core enrichment & job management
    └── test_google_enrichment.py           # Unit test scraper Google & enrichment kontak umum
```
---

## 2. Jalan Kode — Request Lifecycle (API)

Semua endpoint WAJIB login (`app/Middleware/auth_middleware.py::require_auth`) kecuali `POST /api/auth/login`.
Frontend memanggil API via `fetch` di `public/app.js`.

### 2.1 Login
```
public/app.js --POST--> /api/auth/login
  → routes/auth.py::login → app/Controllers/AuthController.py::login
  → app/Services/auth_service.py::verify_password (bcrypt, tabel users)
  → request.session["user_id"] (signed cookie, HttpOnly) — app/main.py::SessionMiddleware
```

### 2.2 Mulai Scrape (seed/enrichment)
```
POST /api/scrape  (atau /api/enrich)
  → routes/scrape.py::start_scrape / start_enrichment → app/Controllers/ScrapeController.py
  → app/Services/job_manager.py::job_manager.start
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
  → routes/lead.py::list_leads → app/Controllers/LeadController.py::list_leads
  → app/Services/storage_service.py::query_leads
      ├─ JOIN categories & cities (outer) agar bisa sort/filter nama lookup
      ├─ search: nama_instansi/alamat/email/kategori/kota (ilike)
      └─ sort_by di-whitelist via SORTABLE_COLUMNS (anti SQL-injection)

PATCH /api/leads/{id}  → storage_service.update_lead_full (kategori/kota di-resolve ke FK)
DELETE /api/leads/{id} → storage_service.delete_leads
```

### 2.5 Dedup / Merge
```
GET  /api/duplicates
  → app/Services/dedup_service.py::find_duplicate_groups
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

### 2.7 Monitor Browser via noVNC (Docker / VPS)
Di container tidak ada layar, jadi jendela Chromium Playwright tidak bisa muncul di
device user. Solusinya **noVNC + layar virtual** — tanpa perubahan alur aplikasi:

```
docker/entrypoint.sh (ENTRYPOINT container)
  1. Xvfb :99              → layar virtual 1920x1080x24 (-ac, tanpa TCP)
  2. openbox               → window manager (title bar, maximize, Alt+Tab antar job)
  3. x11vnc :5900          → server VNC (opsional password via NOVNC_PASSWORD, maks 8 char RFB)
  4. websockify :8002      → noVNC (UI VNC HTML5) → http://<host>:8002/vnc.html?autoconnect=1&resize=scale
  5. exec uvicorn          → CMD aplikasi (BROWSER_HEADLESS=false dipaksa saat display siap)
```

- Chromium **headful** di `:99`; `JobManager` tidak membatasi konkurensi → 3 job
  bersamaan = 3 jendela Chromium di layar yang sama (Alt+Tab / drag via title bar).
- Bila display stack gagal start (`NOVNC_ENABLED=0`, paket tidak ada, Xvfb mati) →
  entrypoint memaksa `BROWSER_HEADLESS=true` (fallback aman, scraping tetap jalan).
- **Login Google** via tombol "Buka Browser Login" kembali berfungsi di container:
  buka tab Monitor (noVNC), login, tutup jendela — profil tersimpan di volume
  `playwright_profile` (`~/playwright_chrome_profile_gmaps`).
- UI membaca info monitor dari `GET /api/browser-status → {"novnc": {...}}`
  (`routes.scrape` / `ScrapeController._novnc_status`) dan menampilkan tombol **Lihat Browser (Monitor)**
  (`public/app.js::novncTargetUrl`, pakai `NOVNC_PUBLIC_URL` bila diisi — mis. via HTTPS/Cloudflare).
- Keamanan: x11vnc diproteksi `NOVNC_PASSWORD` (maks 8 karakter, batas protokol RFB);
  kosong = tanpa password → WAJIB dibatasi firewall/tunnel. `VNC_PORT` 5900 tidak
  dipublikasikan; hanya web noVNC `:8002`.
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
| `app/main.py` | Merakit FastAPI: lifespan → `init_db()` + `seed_default_user()`; SessionMiddleware; mount `/audio` lalu `/` (public) di akhir |
| `app/config.py` | Baca env `.env`; `database_url` = `mysql+pymysql://...`; default delay scraper 1–3 detik; **konfigurasi browser Playwright**: `browser_headless` & `browser_channel`; **konfigurasi monitor noVNC**: `novnc_enabled/port/public_url/password` + properti `novnc_available` & `novnc_url` (dipakai `/api/browser-status`) |
| `app/Controllers/AuthController.py` | Controller autentikasi (login, logout, me) |
| `app/Controllers/ScrapeController.py` | Controller scraping (seed GMaps, enrichment, jobs, status browser) |
| `app/Controllers/LeadController.py` | Controller leads (query, CRUD, stats, export, dedup, import) |
| `app/Middleware/auth_middleware.py` | `require_auth` dependency proteksi session |
| `app/Models/base.py` | Engine SQLAlchemy + pooling `pool_recycle=1800`, `pool_pre_ping` (mitigasi TiDB idle disconnect), SSL `connect_args` |
| `app/Services/job_manager.py` | **Orkestrator scraping**: `SCRAPER_REGISTRY`, `ENRICHMENT_SOURCES`, thread background, cancel, `reconcile()` watchdog |
| `app/Services/storage_service.py` | Gerbang utama tulis/baca `leads`; `LEAD_FIELDS`, `FK_FIELDS`, `SORTABLE_COLUMNS`; helper job; opsi dropdown |
| `app/Services/auth_service.py` | bcrypt hash/verify |
| `app/Services/browser_profile.py` | Launch browser context Playwright & clone profile |
| `app/Services/cleaner.py` | Normalisasi wajib sebelum DB: telp→`628...`, nama, website domain, validasi email, buang CDN |
| `app/Services/code_generator.py` | Generator format kode bisnis unik: `LD-{KATEGORI}-{001}`, `KAT-{KATEGORI}-{001}`, `K-{KOTA}-{001}` |
| `app/Services/enrichment_service.py` | **Core logic enrichment**: `find_incomplete_leads`, `match_and_merge`, `ENRICHMENT_FIELDS`, `CATEGORY_ENRICHMENT_SOURCES`, threshold fuzzy |
| `app/Services/dedup_service.py` | Fingerprint & grouping duplikat; `resolve_group` → `merge_history` |
| `app/Services/scrapers/base.py` | `BaseScraper`: `rate_limit()`, `cancel()`, `emit_progress()` |
| `app/Services/scrapers/gmaps.py` | Seed semua segmen GMaps |
| `app/Services/scrapers/dapodik.py` | **Enrichment Sekolah**: cari NPSN+kepsek per nama sekolah di referensi.data.kemdikbud.go.id |
| `app/Services/scrapers/google.py` | **Enrichment Kontak Umum (Google/Web)**: cari no. WA/telp, email, website, sosmed via DuckDuckGo/Web |
| `app/Services/exporter.py` | `BASE_COLUMNS` + `EXTRA_COLUMNS` per sumber → XLSX/CSV |
| `app/Services/importer.py` | Parser CSV label Indonesia → field |
| `routes/api.py` | Aggregator seluruh router endpoint `/api` |
| `routes/auth.py` | Router autentikasi `/api/auth` |
| `routes/scrape.py` | Router scraping `/api` |
| `routes/lead.py` | Router leads management `/api` |
| `public/app.js` | Logika frontend: fetch API, render, polling job, dialog dedup & incomplete |
| `tests/test_auth.py` | Smoke test alur login |

---

## 5. Konvensi Yang Harus Diikuti (kode baru)

1. **Pola Universal Laravel / Clean Architecture** — View (`public/`) → Router (`routes/`) → Controller (`app/Controllers/`) → Service (`app/Services/`) → Model (`app/Models/`).
2. **Scraper baru** → buat di `app/Services/scrapers/<nama>.py`, inherit `BaseScraper`, lalu daftarkan di `SCRAPER_REGISTRY` dan `ENRICHMENT_SOURCES` di `job_manager.py`.
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
- Direktori/berkas runtime tidak dilacak (selaras `.gitignore` & `.dockerignore`):
  `venv/`, `.git/`, `.pytest_cache/`, `__pycache__/`, `scratch/`, `logs/`, serta berkas `*.pyc` dan `*.log`.

Alur dokumen: **prd.md (apa/mengapa) → file.md (di mana / jalannya) → database.md (data)**.
---

## 7. Daftar File untuk Validator (Machine Index)

Blok di bawah dibaca oleh `tools/check_docs_sync.py` untuk membandingkan **dokumen ↔ file aktual**.
Saat menambah/memindah/menghapus file, **perbarui blok ini** (dan pohon folder di §1).

<!-- FILE-INDEX-START -->
.clinerules/rules.md
.env.example
.gitattributes
.githooks/pre-commit
.gitignore
.vscode/settings.json
AGENTS.md
README.md
app/Controllers/AuthController.py
app/Controllers/LeadController.py
app/Controllers/ScrapeController.py
app/Controllers/__init__.py
app/Middleware/__init__.py
app/Middleware/auth_middleware.py
app/Models/__init__.py
app/Models/base.py
app/Models/category.py
app/Models/city.py
app/Models/lead.py
app/Models/merge_history.py
app/Models/scrape_job.py
app/Models/user.py
app/Services/__init__.py
app/Services/auth_service.py
app/Services/browser_profile.py
app/Services/cleaner.py
app/Services/code_generator.py
app/Services/dedup_service.py
app/Services/enrichment_service.py
app/Services/exporter.py
app/Services/importer.py
app/Services/job_manager.py
app/Services/scrapers/__init__.py
app/Services/scrapers/base.py
app/Services/scrapers/dapodik.py
app/Services/scrapers/gmaps.py
app/Services/scrapers/google.py
app/Services/storage_service.py
app/__init__.py
app/config.py
app/main.py
database.md
database/migrations/__init__.py
database/migrations/migrate_phase1.py
database/seeders/__init__.py
database/seeders/user_seeder.py
file.md
prd.md
public/app.js
public/favicon.svg
public/index.html
public/style.css
pyproject.toml
requirements.txt
routes/__init__.py
routes/api.py
routes/auth.py
routes/lead.py
routes/scrape.py
run.py
scraper_gmaps_sekolah.py
tests/test_auth.py
tests/test_browser_profile_and_progress.py
tests/test_codes_and_socials.py
tests/test_enrichment_core.py
tests/test_google_enrichment.py
tools/add_seed_job_fk_to_scrape_jobs.py
tools/check_docs_sync.py
tools/clean_invalid_generic_links.py
tools/drop_job_and_vendor_columns.py
tools/drop_jobstreet_glints_lpse_sources.py
tools/migrate_multi_social_and_codes.py
tools/migrate_tiktok_and_clean_socials.py
<!-- FILE-INDEX-END -->