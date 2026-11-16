"""ScrapeController — Menangani logika scrape, enrichment, monitoring browser, dan jobs."""
import threading
from typing import Optional
from fastapi import HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.Models import ScrapeJob
from app.Services import storage_service as store
from app.Services.enrichment_service import ENRICHMENT_FIELDS, find_incomplete_leads
from app.Services.job_manager import job_manager, ScraperRegistry
from app.Services.scrapers.gmaps import GmapsScraper, get_enrichment_sources

_login_thread: Optional[threading.Thread] = None


class ScrapeRequest(BaseModel):
    source: str = "gmaps"
    category: str = "sekolah"
    city: str = "salatiga"
    max_results: int = 50
    job_id: Optional[str] = None


class EnrichmentRequest(BaseModel):
    category: str = "sekolah"
    city: str = "salatiga"
    enrichment_source: str = ""
    max_results: int = 0
    job_id: Optional[str] = None
    seed_job_id: Optional[str] = None


class ScrapeController:
    @staticmethod
    def list_sources() -> dict:
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
                "corporate": {"label": "Perusahaan / Corporate (Jateng)", "enrichment": ["google"]},
                "perusahaan": {"label": "Perusahaan / Corporate (Jateng)", "enrichment": ["google"]},
                "umkm": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
                "retail": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
                "resto": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
                "restoran": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
                "kafe": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
                "cafe": {"label": "UMKM, Retail, Resto/Kafe", "enrichment": ["google"]},
                "vendor": {"label": "Vendor B2G / Kontraktor", "enrichment": ["google"]},
                "kontraktor": {"label": "Vendor B2G / Kontraktor", "enrichment": ["google"]},
                "b2g": {"label": "Vendor B2G / Kontraktor", "enrichment": ["google"]},
            },
        }

    @staticmethod
    def start_scrape(req: ScrapeRequest, request: Request | None = None) -> dict:
        if req.max_results < 1:
            raise HTTPException(status_code=422, detail="max_results minimal 1")
        if req.max_results > 100:
            raise HTTPException(status_code=422, detail="max_results maksimal 100 agar proses stabil dan aman dari rate limit")
        try:
            user_id = request.session.get("user_id") if request else None
            return job_manager.start(req.source, req.category, req.city, req.max_results, job_id=req.job_id, user_id=user_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    def start_enrichment(req: EnrichmentRequest, db: Session, request: Request | None = None) -> dict:
        source = req.enrichment_source.strip().lower()
        if not source:
            sources = get_enrichment_sources(req.category)
            if not sources:
                raise HTTPException(
                    status_code=400,
                    detail=f"Kategori '{req.category}' tidak punya sumber enrichment default — pilih sumber secara manual.",
                )
            source = sources[0]

        if source not in ScraperRegistry.list_sources():
            raise HTTPException(
                status_code=400,
                detail=f"Sumber enrichment '{source}' tidak tersedia. Pilih: {ScraperRegistry.list_sources()}",
            )

        seed_job_id = req.seed_job_id
        if not seed_job_id:
            seed = db.query(ScrapeJob).filter(
                ScrapeJob.source == "gmaps",
                ScrapeJob.category == req.category,
                ScrapeJob.city == req.city,
            ).order_by(ScrapeJob.started_at.desc()).first()
            if seed:
                seed_job_id = seed.id

        try:
            user_id = request.session.get("user_id") if request else None
            return job_manager.start(
                source=source,
                category=req.category,
                city=req.city,
                max_results=req.max_results,
                job_id=req.job_id,
                seed_job_id=seed_job_id,
                user_id=user_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    def enrich_options(db: Session) -> dict:
        by_cat = store.list_categories_with_cities(db, source="gmaps")
        return {
            "categories": sorted(by_cat.keys()),
            "cities_by_category": by_cat,
            "all_cities": sorted({c for v in by_cat.values() for c in v}),
        }

    @staticmethod
    def list_jobs(db: Session, limit: int = 20) -> dict:
        try:
            job_manager.reconcile(db)
        except Exception:
            pass
        return {"items": store.list_jobs(db, limit=limit)}

    @staticmethod
    def get_job(job_id: str, db: Session) -> dict:
        try:
            job_manager.reconcile(db)
        except Exception:
            pass
        job = store.get_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "id": job.id,
            "seed_job_id": getattr(job, "seed_job_id", None),
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

    @staticmethod
    def get_job_incomplete_leads(job_id: str, db: Session, limit: int = 100) -> dict:
        job = store.get_job(db, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job tidak ditemukan")

        if job.source == "gmaps":
            cat_lower = (job.category or "").lower()
            is_school = any(w in cat_lower for w in ("sekolah", "sd", "smp", "sma", "smk", "madrasah", "pesantren"))
            if is_school:
                fields = ["npsn", "nama_kepsek", "email", "telp", "website", "sosmed"]
                d_leads = find_incomplete_leads(db, source="dapodik", category=job.category, city=job.city, limit=limit)
                g_leads = find_incomplete_leads(db, source="google", category=job.category, city=job.city, limit=limit)
                leads = list({l.id: l for l in (d_leads + g_leads)}.values())[:limit]
            else:
                fields = ENRICHMENT_FIELDS.get("google", [])
                leads = find_incomplete_leads(db, source="google", category=job.category, city=job.city, limit=limit)
        else:
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
            "seed_job_id": getattr(job, "seed_job_id", None),
            "source": job.source,
            "category": job.category,
            "city": job.city,
            "fields": fields,
            "total": len(items),
            "items": items,
        }

    @staticmethod
    def cancel_job(job_id: str) -> dict:
        ok = job_manager.cancel(job_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Job tidak berjalan / tidak ditemukan")
        return {"ok": True, "id": job_id}

    @staticmethod
    def delete_job(job_id: str, db: Session) -> dict:
        if job_manager.is_managed(job_id):
            raise HTTPException(status_code=400, detail="Job masih berjalan — Stop dulu sebelum menghapus riwayat.")
        deleted = store.delete_job(db, job_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"ok": True, "deleted": job_id}

    @staticmethod
    def _novnc_status() -> dict:
        return {
            "available": settings.novnc_available,
            "enabled": settings.novnc_enabled,
            "port": settings.novnc_port,
            "url": settings.novnc_url,
            "password_required": bool(settings.novnc_password),
        }

    @staticmethod
    def browser_status(request: Request | None = None) -> dict:
        user_id = request.session.get("user_id") if request else None
        try:
            status = GmapsScraper(user_id=user_id).browser_status()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal cek status browser: {e}")
        status["novnc"] = ScrapeController._novnc_status()
        return status

    @staticmethod
    def browser_login(request: Request | None = None) -> dict:
        if settings.browser_headless:
            return {
                "ok": False,
                "headless": True,
                "msg": (
                    "Mode headless: tidak ada layar untuk login manual. "
                    "Aktifkan monitor browser (NOVNC_ENABLED=1 di container) atau "
                    "login sekali di mesin lokal lalu salin profil "
                    "~/playwright_chrome_profile_gmaps ke volume container. "
                    "Scraping GMaps tetap berjalan tanpa login."
                ),
            }

        user_id = request.session.get("user_id") if request else None
        global _login_thread
        if _login_thread is not None and _login_thread.is_alive():
            return {
                "ok": True,
                "already_open": True,
                "msg": "Jendela login sudah terbuka. Login di Chrome, lalu tutup jendelanya.",
            }

        def _open():
            try:
                GmapsScraper(user_id=user_id).browser_login()
            except Exception:
                pass

        _login_thread = threading.Thread(target=_open, daemon=True)
        _login_thread.start()
        return {"ok": True, "msg": "Chrome terbuka — login ke akun Google, lalu tutup jendelanya."}
