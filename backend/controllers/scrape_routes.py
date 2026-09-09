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
from backend.services.enrichment_service import ENRICHMENT_FIELDS, find_incomplete_leads
from backend.services.job_manager import job_manager, ScraperRegistry
from backend.services.scrapers.gmaps import GmapsScraper, get_enrichment_sources

router = APIRouter()


class ScrapeRequest(BaseModel):
    source: str = "gmaps"
    category: str = "sekolah"
    city: str = "salatiga"
    max_results: int = 50
    job_id: Optional[str] = None


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
    job_id: Optional[str] = None


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
            "sekolah": {"label": "Sekolah", "enrichment": ["dapodik", "google"]},
            "rumah sakit": {"label": "Rumah Sakit / Kesehatan", "enrichment": ["google"]},
            "kesehatan": {"label": "Kesehatan / Faskes", "enrichment": ["google"]},
            "hotel": {"label": "Hotel / Penginapan", "enrichment": ["google"]},
            "corporate": {"label": "Perusahaan / Corporate (Jateng)", "enrichment": ["jobstreet", "glints", "google"]},
            "perusahaan": {"label": "Perusahaan / Corporate (Jateng)", "enrichment": ["jobstreet", "glints", "google"]},
            "umkm": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google", "jobstreet", "glints"]},
            "retail": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google", "jobstreet", "glints"]},
            "resto": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
            "restoran": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
            "kafe": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
            "cafe": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
            "vendor": {"label": "Vendor B2G / Kontraktor", "enrichment": ["lpse", "google"]},
            "kontraktor": {"label": "Vendor B2G / Kontraktor", "enrichment": ["lpse", "google"]},
            "b2g": {"label": "Vendor B2G / Kontraktor", "enrichment": ["lpse", "google"]},
        },
    }


@router.post("/scrape")
def start_scrape(req: ScrapeRequest, _: dict = Depends(require_auth)) -> dict:
    """Memulai job scraping seed (GMaps) atau enrichment."""
    if req.max_results < 1:
        raise HTTPException(status_code=422, detail="max_results minimal 1")
    if req.max_results > 100:
        raise HTTPException(status_code=422, detail="max_results maksimal 100 agar proses stabil dan aman dari rate limit")
    try:
        return job_manager.start(req.source, req.category, req.city, req.max_results, job_id=req.job_id)
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
            source=source,
            category=req.category,
            city=req.city,
            max_results=req.max_results,
            job_id=req.job_id,
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


@router.get("/jobs/{job_id}/incomplete")
def get_job_incomplete_leads(
    job_id: str,
    limit: int = 100,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Mengambil daftar lead seed yang belum lengkap field enrichment-nya untuk job ini."""
    job = store.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")

    fields = ENRICHMENT_FIELDS.get(job.source, [])
    if not fields:
        return {
            "job_id": job.id,
            "source": job.source,
            "category": job.category,
            "city": job.city,
            "fields": [],
            "items": [],
            "total": 0,
        }

    leads = find_incomplete_leads(
        db,
        source=job.source,
        category=job.category,
        city=job.city,
        limit=limit,
    )

    items = []
    for l in leads:
        d = store._lead_to_dict(l)
        missing = [f for f in fields if not getattr(l, f, None) or str(getattr(l, f, "")).strip() in ("", "-")]
        d["missing_fields"] = missing
        items.append(d)

    return {
        "job_id": job.id,
        "source": job.source,
        "category": job.category,
        "city": job.city,
        "fields": fields,
        "total": len(items),
        "items": items,
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