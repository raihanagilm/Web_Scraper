# Global Rules — Web_Scraper (auto-load tiap sesi oleh Cline)

## 1. Trio dokumen — PRE-FLIGHT WAJIB

Setiap task, **baca dalam urutan ini sebelum menulis/mengubah kode**:

1. `prd.md` — apa & mengapa (kebutuhan, SOP, segmen, milestone)
2. `file.md` — struktur folder & **jalan kode** (code map, call graph, peta modul)
3. `database.md` — skema DB (tabel, kolom, enum, unique, relasi)

Ketiganya saling melengkapi & **wajib saling membaca**. Rujukan lengkap: `AGENTS.md`.

## 2. Pre-flight checklist

- [ ] `prd.md` terbaca → paham segmen + SOP (rate-limit 1–3 dtk, MVC, anti-duplikat)
- [ ] `file.md` terbaca → tahu file/lokasi yg benar & jalan kode yang sudah ada
- [ ] `database.md` terbaca → perubahan tidak merusak skema/enum/unique
- [ ] Baca file terkait di area perubahan (jangan menebak)

## 3. Selama bekerja

- Ikuti pola MVC: `frontend/` → `controllers/` → `services/` → `models/`.
- Data masuk DB hanya via `cleaner.clean_lead()` + `storage_service.upsert_lead()`.
- Scraper baru: inherit `BaseScraper`, daftar di `SCRAPER_REGISTRY` + `ENRICHMENT_SOURCES`.
- Konvensi lain: `file.md` §5 dan `prd.md` §4.

## 4. Update dokumen bareng kode

- Tambah/pindah file → update `file.md` (§1 & §4).
- Ubah model/skema → update `database.md` (+ `storage_service.LEAD_FIELDS`).
- Ubah alur/SOP → update `prd.md`.

Setelah selesai: `venv\Scripts\python.exe tools\check_docs_sync.py` wajib lolos.

## 5. Anti-slop

- Jangan mulai dari nol — baca dokumen & kode dulu ("tahu jalannya kode sebelumnya").
- Jangan duplikasi logic `cleaner`/`storage`/`dedup`/`enrichment`.
- Jangan commit `.env` / kredensial.