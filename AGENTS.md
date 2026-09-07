# AGENTS.md — Aturan Global & Workflow Wajib untuk Semua Agent AI

**Repositori:** Web_Scraper (Edtekno B2B Lead Generation Tool) — PRD v1.1

Dokumen ini adalah **aturan global tingkat repo** untuk semua agent AI (Cline, Claude Code,
Cursor, Windsurf, GitHub Copilot, dsb.). Patuhi **sebelum dan selama** mengerjakan task apa pun.

---

## 1. Trio Dokumen — WAJIB Dibaca Sebelum Bekerja (Pre-flight)

Setiap kali menerima task, agent WAJIB membaca ketiga dokumen di bawah **sebelum** menulis/
mengubah kode, dalam urutan berikut:

```
1. prd.md        → APA & MENGAPA  (kebutuhan bisnis, SOP, arsitektur, milestone)
2. file.md       → DIMANA & BAGAIMANA  (struktur folder, jalan kode / call graph, peta modul)
3. database.md   → DATA  (skema tabel/kolom/enum, relasi, anti-duplikat)
```

Ketiga dokumen **saling melengkapi dan diwajibkan saling membaca**:

| Dokumen | Peran | Harus merujuk ke |
|---|---|---|
| `prd.md` | Kebutuhan & aturan | `file.md` (§7 Struktur Folder), `database.md` (§9 Model Data) |
| `file.md` | Peta kode & struktur | `prd.md`, `database.md` |
| `database.md` | Skema data | `prd.md`, `file.md` |

- Jika salah satu dokumen **tidak ada** atau **nyata-nyata usang** dibanding kode → hentikan
  pekerjaan, beri tahu user, dan perbaiki dokumen lebih dulu.
- Validator otomatis: `venv\Scripts\python.exe tools\check_docs_sync.py`

## 2. Workflow Pre-flight Checklist (sebelum ubah kode)

1. [ ] Baca `prd.md` — pahami API/tujuan, segmen, dan SOP wajib (rate-limit, MVC, anti-duplikat).
2. [ ] Baca `file.md` — konfirmasi tempat yang benar untuk modifikasi + *jalan kode* yang sudah ada.
3. [ ] Baca `database.md` — pastikan perubahan tidak merusak skema/enum/unique constraint.
4. [ ] Cek kode yang ada di area perubahan (baca file terkait) — jangan menebak konvensi.
5. [ ] Kalau perubahan melibatkan model/skema → baca juga `backend/models/*.py` + `migrate_phase1.py`.

## 3. Selama Bekerja

- Ikuti **struktur MVC** yang ada: View (`frontend/`) → Controller (`backend/controllers/`) →
  Service (`backend/services/`) → Model (`backend/models/`). Jangan buat pola paralel baru.
- **Jangan bypass Cleaner / Storage** — data masuk DB hanya lewat `clean_lead()` + `upsert_lead()`.
- Ikuti konvensi di `file.md` §5 dan SOP di `prd.md` §4 (rate-limit 1–3 detik, login wajib, dll).
- Perbarui dokumen **bersamaan** dengan perubahan kode (bukan nanti-nanti).

## 4. Kapan WAJIB Memperbarui Dokumen (Document-Sync)

| Jika Anda mengubah... | Dokumen yang wajib diperbarui |
|---|---|
| Menambah/memindah/menghapus file | `file.md` → §1 Pohon Folder & §4 Peta Modul |
| Alur/request lifecycle berubah | `file.md` → §2 & §3 |
| Model / kolom / enum / unique constraint | `database.md` → tabel terkait & §8 Enum (+ `storage_service.LEAD_FIELDS`) |
| Kebutuhan, segmen, SOP di `prd.md` | PRD (dan cantumkan referensi ke `file.md`/`database.md`) |

Setelah selesai, jalankan & **pastikan lolos**:
```
venv\Scripts\python.exe tools\check_docs_sync.py
```

## 5. Hooks yang Terpasang (otomatis)

- **Cline hook** `ON_TASK_START` → menjalankan `tools/check_docs_sync.py` (lihat `.vscode/settings.json`).
- **Git pre-commit** → menjalankan validator sebelum commit (lihat `.githooks/pre-commit`).
- Hook non-zero exit = ada drift dokumen → jangan lanjut sampai diperbaiki.

## 6. Jalan Kode Cepat (ringkas — detail di `file.md`)

- Startup: `python run.py` → `backend/main.py` (lifespan: `init_db()` + `seed_default_user()`).
- Auth: `/api/auth/login` → `auth_routes` → `auth_service` → session cookie.
- Scrape: `POST /api/scrape` → `scrape_routes` → `job_manager.start` → thread → scraper (`services/scrapers/`)
  → `storage_service.save_raw_items` → `cleaner` → `upsert_lead` → `leads`.
- Enrichment: `POST /api/enrich` → `enrichment_service.match_and_merge` (isi field kosong saja).
- Dedup: `GET /api/duplicates` → `dedup_service.find_duplicate_groups` → resolve → `merge_history`.
- Export: `GET /api/export` → `exporter.export_leads` → `.xlsx`.

## 7. Regulasi Anti-Slop

- Jangan menulis kode jika dokumen & kode yang ada tidak dibaca dulu — **"tahu jalannya kode
  sebelumnya" itu wajib**, jangan mulai dari nol.
- Jangan menebak nama function/atribut — baca `file.md` peta modul lalu buka file-nya.
- Jangan duplikasi logic yang sudah ada di `cleaner`/`storage`/`dedup`/`enrichment`.
- Jangan commit `.env` atau kredensial (lihat `.gitignore` & PRD §12).