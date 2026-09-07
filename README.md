# Web Scraper & B2B Lead Generation Tool — Edtekno

Tool internal untuk mengumpulkan, membersihkan, dan mengekspor **lead bisnis (B2B)** dari berbagai sumber publik. Backend **FastAPI (MVC)**, frontend HTML/CSS/JS, database **MySQL (TiDB Cloud)**.

## Fitur
- 🔐 Login wajib (session cookie)
- 🕷 Scraping Google Maps multi-kategori (+ Dapodik, LPSE, Jobstreet/Glints di modul)
- 📈 Progress realtime via WebSocket + tombol Stop
- 🛡️ Anti-duplikat 2 lapis (unique DB + review manual)
- ⚖️ Bandingkan & gabungkan duplikat antar sumber
- 📊 Export Excel profesional
- 🔎 Search, filter, pagination

## Struktur
```
backend/
  models/          # SQLAlchemy models (MVC: Model)
  controllers/     # FastAPI routers (MVC: Controller)
  services/        # scraper/cleaner/exporter/dedupe/job/auth (MVC: Business logic)
frontend/          # HTML/CSS/JS (MVC: View)
```

## Setup
```bash
# 1. Virtual env
python -m venv venv
venv\Scripts\activate

# 2. Dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Env config
copy .env.example .env     # Windows
cp .env.example .env       # macOS/Linux
# isi DB_HOST/DB_USER/DB_PASSWORD dengan kredensial TiDB Cloud

# 4. Browser scraper (Google Maps)
playwright install chromium

# 5. Jalankan
python run.py
# buka http://127.0.0.1:8000 → login (admin / agiltampan)
```

## Test
```bash
venv\Scripts\python -m pytest tests/ -q
```

## Dokumentasi API
Buka `http://127.0.0.1:8000/docs` (Swagger auto).

> ⚠️ Kredensial DB / password seed tersimpan di `.env` (sudah di-`.gitignore`). Jangan pernah commit `.env`.