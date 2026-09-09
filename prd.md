# PRD — Automated Web Scraper & B2B Lead Generation Tool

| | |
|---|---|
| **Nama Perusahaan** | PT Edtekno Inovasi Indonesia |
| **Judul Proyek** | Automated Web Scraper & B2B Lead Generation Tool |
| **Nama Magang** | Raihan Agil |
| **Posisi** | Data Analyst Intern |
| **Versi Dokumen** | 1.1 |
| **Status** | Disetujui — Siap Implementasi |

---

## 0. Dokumen Pendamping (Wajib Dibaca Bersama)

PRD ini **wajib dibaca bersama** dua dokumen pelengkap yang saling merujuk satu sama lain:

| Dokumen | Isi |
|---|---|
| [file.md](file.md) | Struktur folder terkini & **jalan kode** (code map / call graph) — melengkapi §7 |
| [database.md](database.md) | Skema database detail (tabel/kolom/enum/constraint) — melengkapi §9 |

**Alur baca (agent AI wajib):** `prd.md` → `file.md` → `database.md` sebelum menyentuh kode.
Setiap perubahan kode yang menyentuh struktur/alur/skema harus diikuti pembaruan dokumen
tersebut. Validasi otomatis: `venv\Scripts\python.exe tools\check_docs_sync.py`.

## 1. Ringkasan Eksekutif

Tool internal berbasis web untuk **mengotomatiskan pengumpulan lead bisnis (B2B)** dari berbagai sumber publik di Indonesia, membersihkannya, menghilangkan duplikat, dan mengekspornya ke Excel profesional. Pengguna cukup membuka browser, login, memilih sumber + kategori + kota, lalu memantau progres scraping secara realtime.

**Masalah yang dipecahkan:** Proses pengumpulan data sekolah/perusahaan/UMKM saat ini masih manual (buka Google Maps satu-salin, catat di Excel). Tool ini menggantikannya dengan pipeline otomatis yang rapi, bisa diulang, dan terdokumentasi.

**Arsitektur sumber data (Seed → Enrichment):** Sumber utama adalah **Google Maps (GMaps)** — sistem mengambil *daftar leads dasar* (nama instansi, alamat, kota, telp, email, website, link GMaps) dari GMaps. Karena banyak data penting **tidak tercantum di GMaps** (NPSN, nama kepala sekolah, posisi rekrutmen, deskripsi IT, penanggung jawab vendor), lead kemudian **diperkaya (enrichment)** oleh sumber pendukung: **Dapodik Kemendikbud** (melengkapi Sekolah), **Jobstreet / Glints** (melengkapi Perusahaan/Corporate serta UMKM, Retail, Resto/Kafe), dan **LPSE Daerah** (melengkapi Vendor B2G / Kontraktor).

**Target akhir:** 500–1.000+ kontak bisnis terverifikasi (unique leads) yang siap untuk keperluan IT Training, Bootcamp, Outsource Dev, Corporate Training, Aplikasi POS, System Inventaris, IT Consulting, dan Custom System.

---

## 2. Tujuan & Non-Goals

### Tujuan (v1)
- Mengganti alur manual menjadi **web app** yang bisa dipakai tim non-teknis.
- Scraping **Google Maps sebagai sumber utama (seed)** untuk daftar leads, lalu **enrichment** via 3 sumber pendukung (Dapodik, Jobstreet/Glints, LPSE Daerah) sesuai segmen pasar.
- **Anti-duplikat 2 lapis** (otomatis via DB + review manual).
- Fitur **perbandingan & penggabungan** lead dari sumber berbeda (pilih mana yang dipertahankan/digabung/dihapus).
- **Progress realtime** via WebSocket + kemampuan **Stop/Batalkan** job.
- **Search, filter, pagination** pada tabel hasil.
- **Export Excel** profesional (styling, dropdown status, kolom sesuai sumber).
- **Login wajib** (akun internal Edtekno) — data tidak boleh diakses publik.

### Non-Goals (v1)
- Tidak ada sistem peran/otorisasi granular (hanya 1 level: logged-in user).
- Tidak ada penjadwalan otomatis (cron) — scraping manual trigger per sesi.
- Tidak ada pengumpulan data yang dilindungi login/captcha (hanya halaman publik).
- Tidak ada dashboard analitik lanjutan (hanya statistik ringkas).

---

## 3. Target Pengguna
- **Staf Sales/Marketing Edtekno** — mencari prospek sekolah, perusahaan, UMKM, vendor.
- **Tim Data/Analyst** — membersihkan, deduplikasi, dan mengekspor data lead.
- **Pengguna teknis tingkat dasar** — cukup bisa operasikan browser & form.

---

## 4. SOP & Aturan Teknis (Wajib Dipatuhi)

| Aturan | Keterangan | Implementasi |
|---|---|---|
| Bahasa Pemrograman | Python 3.10+ | Seluruh backend pakai Python 3.10+ |
| Struktur Modular | Scraper, Cleaner, Exporter dipisah | `services/scrapers/`, `cleaner.py`, `exporter.py` |
| Rate Limiting | Delay 1–3 detik per request | `base.py` scraper: `time.sleep(random.uniform(1,3))` |
| Version Control | Push ke GitHub berkala, commit terstruktur | Milestone diakhiri commit `feat/fix/refactor: ...` |
| Format Telepon | Standarisasi ke `628xxxxxxxx` | `cleaner.py`: `normalize_phone()` |
| Kerahasiaan Data | Data hanya internal Edtekno, dilarang disebar | `.env` di-gitignore, login wajib, data di DB internal |
| Keamanan Kredensial | Password di-hash, tidak pernah plain-text | bcrypt + session cookie HttpOnly |


---

## 5. Target Sumber Data

### 5.1 Pemetaan Segmen → Sumber → Field

Prinsip umum: **Google Maps adalah sumber utama (seed) untuk semua segmen** — menghasilkan daftar leads dasar. Sumber pendukung dipakai sebagai **enrichment** untuk mengisi field yang tidak tersedia di GMaps.

| Segment Pasar | Sumber Utama (Seed) | Sumber Pendukung (Enrichment) | Prioritas | Layanan Edtekno Target | Field dari Seed (GMaps) | Field dari Enrichment |
|---|---|---|---|---|---|---|
| Sekolah | **Google Maps** | **Dapodik Kemendikbud** | High | IT Training, Bootcamp, Workshop | Nama Sekolah, Alamat, Kota, Telp, Email, Website, Sosmed, Link GMaps | **NPSN**, **Nama Kepsek** |
| Perusahaan/Corporate (Jateng) | **Google Maps** | **Jobstreet / Glints** | High | Outsource Dev, Corporate Training | Nama PT, Alamat, Kota, Telp, Email, Website, Sosmed, Link GMaps | **Posisi Rekrutmen**, **Deskripsi IT** |
| UMKM, Retail, Resto/Kafe | **Google Maps** | **Jobstreet / Glints** | Medium | Aplikasi POS, System Inventaris | Nama Bisnis, Kategori, Alamat, Kota, No. WA/Telp, Email, Website, Sosmed, Link GMaps | **Posisi Rekrutmen**, **Deskripsi IT** |
| Vendor B2G / Kontraktor | **Google Maps** | **LPSE Daerah** | Medium | IT Consulting, Custom System | Nama PT/CV, Alamat, Kota, Telp/Email, Website, Sosmed, Link GMaps | **Penanggung Jawab**, **Bidang Usaha (detail)** |

> **Catatan enrichment:** Enrichment bersifat *lazy* — hanya dijalankan untuk lead yang field pendukungnya masih kosong, dan hanya mengisi field kosong (tidak menimpa data yang sudah ada). Matching dilakukan via fuzzy match nama + kota, NPSN (Sekolah), domain website/email (Perusahaan/UMKM), atau nama PT/kota (Vendor).

### 5.2 Catatan Teknis per Sumber

**Google Maps — Sumber Utama (Seed, semua segmen)**
- Mesin: Playwright (persistent Chrome profile, headful).
- Query: `{kategori} di {kota}` — mendukung kategori: Sekolah, Kafe/Resto, UMKM/Toko, Retail, Jasa, dan custom keyword.
- Filter nama: whitelist/blacklist regex (untuk kategori sekolah); kategori umum tidak di-hard-filter.
- Rate-limit: delay antar klik/scroll 1–3 detik.
- Output: *daftar leads dasar* yang menjadi input utama pipeline; field pendukung yang tidak ada di GMaps akan diisi oleh sumber enrichment di bawah.

**Dapodik / Kemendikdasmen (Data Pokok Pendidikan) — Enrichment (Sekolah)**
- Peran: melengkapi lead Sekolah hasil seed GMaps dengan **NPSN** dan **Nama Kepala Sekolah** (field yang tidak tersedia di GMaps).
- Sumber data: ekosistem data Kemendikbud (`referensi.data.kemdikbud.go.id`, `dapo.kemdikbud.go.id`, `sekolah.data.kemdikbud.go.id`) — **bukan** portal berita `www.kemendikdasmen.go.id`.
- Endpoint internal (JSON) diverifikasi saat implementasi (situs butuh JS/browser).
- Field unggulan: NPSN, Nama Kepala Sekolah, alamat resmi, kontak.
- Strategi: scraping daftar per kota → buka halaman detail per sekolah → tarik field.

**LPSE Daerah — Enrichment (Vendor B2G / Kontraktor)**
- Peran: melengkapi lead Vendor hasil seed GMaps dengan **Penanggung Jawab** dan detail **Bidang Usaha** dari profil penyedia pada pengumuman tender.
- Setiap daerah punya instance tersendiri (contoh: `lpse.salatiga.go.id`, `lpse.semarang.go.id`).
- Strategi: akses daftar pengumuman tender → buka profil penyedia/vendor → tarik data badan usaha.
- Konfigurasi per-daerah (URL base + selector) disimpan di config.
- Pilot v1: 1–2 daerah (Salatiga, Semarang).

**Jobstreet / Glints — Enrichment (Perusahaan/Corporate & UMKM, Retail, Resto/Kafe)**
- Peran: melengkapi lead hasil seed GMaps dengan **Posisi Rekrutmen** (lowongan IT aktif) dan **Deskripsi IT** (ringkasan kebutuhan teknologi perusahaan) — sinyal kualifikasi prospek.
- **Risiko tinggi:** anti-bot ketat (Datadome/Cloudflare), login-wall, ToS melarang scraping.
- Pendekatan: halaman publik saja, rate-limit 1–3 detik, hormati `robots.txt`, **tidak** menerobos captcha/login.
- **Kontingensi:** jika diblokir → gunakan **impor CSV manual** (pipeline Cleaner→Dedupe→DB tetap dipakai).

### 5.3 Alur Enrichment Data (Seed → Enrichment → Merge)

1. **Seed (GMaps):** scraper Google Maps menghasilkan *daftar leads dasar* per kategori/kota → Cleaner → upsert ke DB (unique constraint `(source, nama_instansi, kota)`).
2. **Identifikasi lead belum lengkap:** storage service memilih lead yang field pendukungnya masih kosong — mis. `npsn`/`nama_kepsek` kosong (Sekolah), `posisi_rekrutmen`/`deskripsi_it` kosong (Perusahaan/UMKM), `penanggung_jawab` kosong (Vendor).
3. **Enrichment scraper:** scraper pendukung dijalankan hanya untuk lead tersebut (lazy), dengan rate-limit 1–3 detik:
   - **Dapodik** → isi NPSN, nama kepsek, email resmi, & link referensi Kemendikdasmen (Sekolah).
   - **Jobstreet/Glints** → isi posisi rekrutmen & deskripsi IT (Perusahaan/Corporate, UMKM, Retail, Resto/Kafe).
   - **LPSE Daerah** → isi penanggung jawab & detail bidang usaha (Vendor B2G/Kontraktor).
4. **Matching:** fuzzy match `nama_instansi` + `kota`; alternatif NPSN (Sekolah) atau domain website/email (Perusahaan/UMKM). Hasil match di bawah threshold ditandai untuk review manual, bukan otomatis digabung.
5. **Merge:** hanya field kosong yang diisi (`update_lead_full` field-level); data yang sudah ada tidak ditimpa. Semua perubahan tercatat dan anti-duplikat (Lapis 1 & 2) tetap berjalan.

---

## 6. Arsitektur Sistem (MVC)

### 6.1 Pola MVC

> VIEW (frontend: login, dashboard, scrape, enrichment-monitor, results, merge-review) → CONTROLLER (routers) → MODEL+SERVICE (SQLAlchemy models, scrapers, cleaner, exporter, storage, job manager, auth, dedup, importer)

### 6.2 Alur Data (Pipeline)

> View pilih sumber+kategori+kota+max → POST /api/scrape → Job Manager spawn thread → **Step 1 — Seed: Scraper GMaps** (rate-limit 1-3s, progres dipantau via **polling** `/api/jobs` tiap 3 detik) → Cleaner (normalisasi telp→628, nama, validasi email, dedup key) → Storage Service (upsert MySQL, unique constraint anti-duplikat; jumlah real tersimpan dicatat ke `items_created`/`items_updated`) → **Step 2 — Enrichment (dipicu manual):** tombol **⚡ Enrich** pada baris job seed di Riwayat Job (kategori+kota otomatis ikut job, tanpa "maks" — memproses SEMUA kandidat yang field-nya kosong) → scraper pendukung (Dapodik per-nama-sekolah / Jobstreet-Glints / LPSE Daerah) → match & merge field-level (hanya isi field kosong, tidak menimpa) → [opsional] Exporter (Excel profesional).

**Status job watchdog:** setiap polling `GET /api/jobs`, job `running` yang prosesnya mati (server restart, browser ditutup, hang >600 dtk) dikoreksi otomatis menjadi `error` + log alasan.

---

## 7. Struktur Folder

> Lihat bab 7 di dokumen lengkap. Inti: backend/{main.py, config.py, seed.py, models/, controllers/, services/{scrapers/,cleaner.py,exporter.py,importer.py,storage_service.py,job_manager.py,auth_service.py,dedup_service.py}, frontend/{login.html,index.html,scrape.html,results.html,merge.html,css/,js/}

**Dokumen detail:** lihat [file.md](file.md) — struktur folder & jalan kode terkini.

---

## 8. Desain API (semua wajib login kecuali /api/auth/login)

- Auth: POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me
- Scrape: POST /api/scrape, GET /api/sources (sumber + meta enrichment dinamis), GET /api/jobs (polling progres), GET /api/jobs/{id}, GET /api/jobs/{id}/incomplete (ambil data lead belum lengkap/gagal enrich), POST /api/jobs/{id}/cancel, DELETE /api/jobs/{id} (hapus riwayat), GET /api/browser-status, POST /api/browser-login
- Enrichment: POST /api/enrich (max_results opsional — 0/tidak dikirim = proses semua kandidat seed), GET /api/enrich/options (kategori & kota DISTINCT dari data seed)
- Leads: GET /api/stats, GET /api/leads (search, source, kota, category, status, page, size, sort), PATCH /api/leads/{id}, DELETE /api/leads/{id}, POST /api/leads/delete-bulk, GET /api/filters
- Export/Import: GET /api/export (.xlsx), GET /api/export-csv, POST /api/import (multipart CSV)
- Dedup/Merge: GET /api/duplicates, POST /api/duplicates/resolve
- Progres: **polling** GET /api/jobs (interval 3 detik) — tidak memakai WebSocket

---

## 9. Model Data (MySQL TiDB)

**users**: id, username UNIQUE, password_hash (bcrypt), full_name, created_at, updated_at

**categories**: id, kode (`KAT-{KATEGORI}-{001}`), name UNIQUE, created_at

**cities**: id, kode (`K-{KOTA}-{001}`), name UNIQUE, province, created_at

**leads**: id, kode (`LD-{KATEGORI}-{001}`), source (gmaps/dapodik/lpse/jobstreet/glints), priority (high/medium), nama_instansi, category_id → categories (lookup — kategori dinormalisasi via FK), telp (628), email (TEXT multi-email), alamat, city_id → cities (lookup), link_gmaps, website, instagram, facebook, linkedin, twitter_x, tiktok, sosmed, link_source, status (New/Contacted/Follow Up/Deal/Rejected), npsn NULL, nama_kepsek NULL, created_at, updated_at. **Unique: (source, nama_instansi, city_id)** — kategori & kota dinormalisasi ke tabel lookup (migrasi fase 1), bukan kolom string.

**scrape_jobs**: id (format ringkas atau UUID), source, category, city, max_results, status (pending/running/completed/cancelled/error), progress, total_found, items_created, items_updated, log, started_at, finished_at

**merge_history**: id, group_key, action (keep/merge/delete_all), winner_id, member_ids (JSON), field_choices (JSON), snapshot_deleted (JSON), created_at

**Dokumen detail:** lihat [database.md](database.md) — skema kolom/enum/constraint terkini.

---

## 10. Strategi Anti-Duplikat & Penggabungan

**Lapis 1 (otomatis):** normalisasi di Cleaner + unique constraint DB (source, nama_instansi, city_id) + upsert (field kosong diisi data baru).

**Lapis 2 (review manual):** fingerprint keys → (nama ternormalisasi, kota), NPSN sama, telp 628 sama, email sama, domain website sama, nama perusahaan mirip+kota sama. Grup kandidat ditampilkan di Review Duplikat.

**Aksi review:** Pertahankan A / Pertahankan B / Gabungkan (per-field pilih sumber) / Hapus keduanya. Semua tercatat di merge_history.

---

## 11. Desain UI/UX

Hijau (#0E2A1E sidebar, #2F6B4F tombol, #F2F6F3 paper), simpel fungsional anti-AI-slop, Space Grotesk+system-ui+mono, inline SVG icons. 6 halaman: Login, Dashboard, Scrape, Enrichment (monitoring — aksi mulai enrichment dari tombol ⚡ Enrich per baris job di halaman Scrape), Results, Review Duplikat.

---

## 12. Kriteria Penerimaan

- Login admin/agiltampan berhasil; tanpa login → 401
- Scrape 100 lead sekolah Salatiga GMaps → tanpa duplikat exact
- Enrichment Dapodik pada lead Sekolah hasil seed → NPSN & nama kepsek terisi
- Enrichment LPSE pada lead Vendor hasil seed → penanggung jawab terisi
- Enrichment Jobstreet/Glints pada lead Perusahaan/UMKM hasil seed → posisi rekrutmen & deskripsi IT terisi
- Job bisa di-cancel via Stop; job yang prosesnya mati (browser ditutup/server restart) dikoreksi otomatis → `error`
- Progress realtime via polling `/api/jobs` (interval 3 detik)
- Kolom Ditemukan menampilkan format informatif misal `98/100 dari 120` (terambil / target dari total listing GMaps)
- Pemisahan riwayat job: menu Scrape khusus GMaps, menu Enrichment khusus Enrichment
- Tombol ⚡ Enrich di menu Scrape langsung mengarahkan (direct) ke form menu Enrichment
- Dropdown "Data Belum Lengkap" di Riwayat Enrichment menjabarkan lokasi dan field yang belum terisi dengan tombol isi manual
- Hapus riwayat job per baris (lead yang tersimpan tidak ikut terhapus)
- Enrichment tanpa batas "maks" — otomatis memproses semua kandidat seed yang field-nya kosong
- Duplikat fuzzy terdeteksi di Review Duplikat
- Merge: field A+B tergabung, lain terhapus, tercatat di history
- Export Excel: kolom base + tambahan per sumber + styling + dropdown
- Delay scraper 1–3 detik (terbukti di log)
- Tidak ada kredensial di repo
- Commit terstruktur per milestone

---

## 13. Milestone & Timeline

- **M0** Scaffolding → `feat: project scaffolding` ✅
- **M1** Scraper GMaps multi-kategori (seed semua segmen) → `feat: gmaps multi-category scraper` ✅
- **M2** Scraper Dapodik (enrichment Sekolah: NPSN, kepsek — pencarian per nama sekolah) → `feat: dapodik school scraper` ✅
- **M3** Scraper LPSE (enrichment Vendor: penanggung jawab, bidang usaha) → `feat: lpse vendor scraper` ✅
- **M4** Scraper Jobstreet/Glints (enrichment Perusahaan/UMKM: posisi rekrutmen, deskripsi IT) → `feat: jobstreet/glints enrichment scraper` ✅
- **M5** Job Manager + API + Dedup + Importer → `feat: job manager, dedupe & merge` ✅
- **M6** Frontend + Polish → `feat: frontend & polish` ✅ (termasuk: hapus riwayat job, watchdog status, ⚡ Enrich per baris, kolom "Terambil", enrichment monitoring page)

Estimasi: 6–8 minggu (1 orang, paruh waktu magang).

---

## 14. Risiko & Mitigasi

- Anti-bot GMaps → persistent profile + delay + retry
- Struktur Kemdikbud berubah → verifikasi di M1, selector di config
- TiDB idle disconnect → pooling + pool_recycle
- Jobstreet/Glints blokir → kontingensi impor CSV
- LPSE beda struktur per daerah → config per-daerah, 1–2 pilot
- Data bocor → .env di-gitignore, login wajib

---

## 15. Asumsi

Chrome terinstall, internet stabil, kredensial TiDB aktif, seed admin/agiltampan via .env, v1 localhost, hanya halaman publik, target 500–1.000+ leads agregat. Komposisi data: seluruh lead berawal dari **seed Google Maps**; data pendukung (NPSN, kepsek, posisi rekrutmen, deskripsi IT, penanggung jawab) diisi bertahap oleh Dapodik / Jobstreet-Glints / LPSE Daerah sesuai segmen — coverage enrichment bergantung ketersediaan data di sumber pendukung.

---

## 16. Referensi

Sumber: **Google Maps (sumber utama/seed)** untuk daftar leads; **Dapodik Kemendikbud** (enrichment Sekolah), **Jobstreet & Glints** (enrichment Perusahaan/Corporate & UMKM/Retail/Resto/Kafe), **LPSE daerah** (enrichment Vendor B2G/Kontraktor). Teknologi: Python 3.10+, FastAPI, Playwright, BeautifulSoup, Pandas, openpyxl, SQLAlchemy, pymysql, bcrypt. DB: MySQL TiDB Cloud. Docs: Swagger /docs.
