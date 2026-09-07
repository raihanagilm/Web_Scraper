"""Scrape routes: mulai job, daftar job, detail, cancel, browser login, enrichment.

Flow PRD v1.1:
1. Seed: GMaps → daftar leads dasar
2. Enrichment: Dapodik/Jobstreet/Glints/LPSE → melengkapi field kosong
"""
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.deps import require_auth
from backend.models import get_db
from backend.services import storage_service as store
from backend.services.enrichment_service import ENRICHMENT_FIELDS
from backend.services.job_manager import job_manager, ScraperRegistry
from backend.services.scrapers.gmaps import GmapsScraper, get_enrichment_sources

router = APIRouter()


class ScrapeRequest(BaseModel):
    source: str = "gmaps"
    category: str = "sekolah"
    city: str = "salatiga"
    max_results: int = 100


class EnrichmentRequest(BaseModel):
    """Request untuk memulai enrichment pada lead seed yang field-nya masih kosong.

    `category` bebas (dinamis) — tidak lagi dibatasi 4 kategori hardcoded.
    `max_results` opsional: jika tidak diberikan, enrichment memproses semua
    kandidat (mengikuti berapa data seed yang sudah diambil).
    """
    category: str = "sekolah"
    city: str = "salatiga"
    enrichment_source: str = ""  # dapodik, jobstreet, glints, lpse (kosong = auto berdasarkan kategori)
    max_results: int = 0         # 0 = semua kandidat (tanpa batas)


@router.get("/sources")
def list_sources(_: dict = Depends(require_auth)) -> dict:
    """Daftar sumber scraper + meta enrichment dinamis untuk form Enrichment.

    `enrichment_sources` = tiap sumber enrichment, apakah scraper-nya aktif
    (terdaftar di registry), dan field yang bisa diisinya.
    """
    available = set(ScraperRegistry.list_sources())
    return {
        "sources": sorted(available),
        "enrichment_sources": [
            {"source": src, "available": src in available, "fields": fields}
            for src, fields in ENRICHMENT_FIELDS.items()
        ],
        "categories": {
            "sekolah": {"label": "Sekolah", "enrichment": ["dapodik"]},
            "corporate": {"label": "Perusahaan / Corporate (Jateng)", "enrichment": ["jobstreet", "glints"]},
            "perusahaan": {"label": "Perusahaan / Corporate (Jateng)", "enrichment": ["jobstreet", "glints"]},
            "umkm": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["jobstreet", "glints"]},
            "retail": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["jobstreet", "glints"]},
            "resto": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["jobstreet", "glints"]},
            "restoran": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["jobstreet", "glints"]},
            "kafe": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["jobstreet", "glints"]},
            "cafe": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["jobstreet", "glints"]},
            "vendor": {"label": "Vendor B2G / Kontraktor", "enrichment": ["lpse"]},
            "kontraktor": {"label": "Vendor B2G / Kontraktor", "enrichment": ["lpse"]},
            "b2g": {"label": "Vendor B2G / Kontraktor", "enrichment": ["lpse"]},
        },
    }


@router.post("/scrape")
def start_scrape(req: ScrapeRequest, _: dict = Depends(require_auth)) -> dict:
    """Memulai job scraping seed (GMaps) atau enrichment."""
    if req.max_results < 1:
        raise HTTPException(status_code=422, detail="max_results minimal 1")
    try:
        return job_manager.start(req.source, req.category, req.city, req.max_results)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/enrich")
def start_enrichment(req: EnrichmentRequest, _: dict = Depends(require_auth)) -> dict:
    """Memulai job enrichment untuk melengkapi field kosong pada lead seed.

    Enrichment mencocokkan hasil scrape pendukung ke lead seed (GMaps) yang
    field pendukungnya masih kosong, lalu mengisi field kosong tersebut.

    `max_results` opsional: 0/tidak dikirim = proses SEMUA kandidat
    (mengikuti berapa data seed yang sudah diambil).
    """
    # Tentukan sumber enrichment berdasarkan kategori jika tidak dispesifikasikan
    source = req.enrichment_source.strip().lower()
    if not source:
        sources = get_enrichment_sources(req.category)
        if not sources:
            raise HTTPException(
                status_code=400,
                detail=f"Kategori '{req.category}' tidak punya sumber enrichment default — pilih sumber secara manual.",
            )
        # Gunakan sumber pertama yang tersedia
        source = sources[0]

    if source not in ScraperRegistry.list_sources():
        raise HTTPException(
            status_code=400,
            detail=f"Sumber enrichment '{source}' tidak tersedia. Pilih: {ScraperRegistry.list_sources()}"
        )

    try:
        return job_manager.start(
            source,
            req.category,
            req.city,
            # None/0 → tanpa batas (enrich semua kandidat / ikut data seed)
            max_results=req.max_results if req.max_results and req.max_results > 0 else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/enrich/options")
def enrich_options(_: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    """Opsi dinamis form Enrichment — diambil dari data seed yang sudah di Results.

    Mengembalikan nilai unik (DISTINCT) Kategori & Kota dari tabel leads
    (source seed gmaps), dikelompokkan per kategori. Frontend memakai ini untuk
    combobox: saat Kategori dipilih, daftar Kota otomatis tersaring ke kota yang
    benar-benar punya data kategori tsb (mencegah enrichment kombinasi kosong).
    """
    by_cat = store.list_categories_with_cities(db, source="gmaps")
    return {
        "categories": sorted(by_cat.keys()),
        "cities_by_category": by_cat,
        "all_cities": sorted({c for v in by_cat.values() for c in v}),
    }


@router.get("/jobs")
def list_jobs(limit: int = 20, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    # Watchdog: koreksi job stuck ("running" padahal proses mati) sebelum listing.
    # Dipanggil tiap polling frontend → status otomatis membaik tanpa restart.
    try:
        job_manager.reconcile(db)
    except Exception:
        pass
    return {"items": store.list_jobs(db, limit=limit)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    try:
        job_manager.reconcile(db)
    except Exception:
        pass
    job = store.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "source": job.source,
        "category": job.category,
        "city": job.city,
        "max_results": job.max_results,
        "status": job.status,
        "progress": job.progress,
        "total_found": job.total_found,
        "items_created": getattr(job, "items_created", 0),
        "items_updated": getattr(job, "items_updated", 0),
        "log": job.log or "",
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, _: dict = Depends(require_auth)) -> dict:
    ok = job_manager.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job tidak berjalan / tidak ditemukan")
    return {"ok": True, "id": job_id}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    """Hapus satu baris riwayat job (audit log). Lead yang tersimpan tidak ikut terhapus."""
    if job_manager.is_managed(job_id):
        raise HTTPException(status_code=400, detail="Job masih berjalan — Stop dulu sebelum menghapus riwayat.")
    deleted = store.delete_job(db, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "deleted": job_id}


# ---- Browser login (akun Google utk Maps) ----
_login_thread: Optional[threading.Thread] = None


@router.get("/browser-status")
def browser_status(_: dict = Depends(require_auth)) -> dict:
    try:
        return GmapsScraper().browser_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal cek status browser: {e}")


@router.post("/browser-login")
def browser_login(_: dict = Depends(require_auth)) -> dict:
    """Buka Chrome headful (thread background) agar user login manual sekali."""
    global _login_thread
    if _login_thread is not None and _login_thread.is_alive():
        return {
            "ok": True,
            "already_open": True,
            "msg": "Jendela login sudah terbuka. Login di Chrome, lalu tutup jendelanya.",
        }

    def _open():
        try:
            GmapsScraper().browser_login()
        except Exception:
            pass

    _login_thread = threading.Thread(target=_open, daemon=True)
    _login_thread.start()
    return {"ok": True, "msg": "Chrome terbuka — login ke akun Google, lalu tutup jendelanya."}