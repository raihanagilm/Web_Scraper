"""Job Manager: menjalankan scraper di thread background + progress + cancel.

Flow scraping (PRD v1.1):
1. Seed: GMaps → daftar leads dasar
2. Enrichment: Dapodik/Jobstreet/Glints/LPSE → melengkapi field kosong
"""
import threading
import time
import traceback
from datetime import datetime

from backend.config import settings
from backend.models import ScrapeJob, SessionLocal
from backend.services import enrichment_service as enrich
from backend.services import storage_service as store

# Registry scraper: source key -> class
from backend.services.scrapers.dapodik import DapodikScraper
from backend.services.scrapers.gmaps import GmapsScraper
from backend.services.scrapers.jobstreet import JobstreetScraper
from backend.services.scrapers.glints import GlintsScraper
from backend.services.scrapers.lpse import LpseScraper

SCRAPER_REGISTRY = {
    "gmaps": GmapsScraper,
    "dapodik": DapodikScraper,   # M2 — enrichment Sekolah (NPSN & kepsek)
    "lpse": LpseScraper,
    "jobstreet": JobstreetScraper,
    "glints": GlintsScraper,
}

# Mapping sumber enrichment (PRD v1.1 §5.3)
ENRICHMENT_SOURCES = {
    "dapodik": ["sekolah"],
    "jobstreet": ["corporate", "perusahaan", "umkm", "retail", "resto", "restoran", "kafe", "cafe"],
    "glints": ["corporate", "perusahaan", "umkm", "retail", "resto", "restoran", "kafe", "cafe"],
    "lpse": ["vendor", "kontraktor", "b2g"],
}


class ScraperRegistry:
    @staticmethod
    def get_class(source: str):
        cls = SCRAPER_REGISTRY.get(source)
        if cls is None:
            raise ValueError(f"Unknown source: {source}")
        return cls

    @staticmethod
    def list_sources() -> list[str]:
        return list(SCRAPER_REGISTRY.keys())


class JobManager:
    def __init__(self):
        self._running: dict[str, object] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._last_progress: dict[str, float] = {}

    def start(self, source: str, category: str, city: str, max_results: int = 0) -> dict:
        idx_max = max_results or None

        # Untuk enrichment: kumpulkan kandidat seed (lead gmaps kategori+kota
        # dengan field kosong). Bila user tidak kasih maks → proses SEMUA
        # kandidat (eff_max = jumlah kandidat), "mengikuti data yang diambil".
        if source in enrich.ENRICHMENT_FIELDS:
            tdb = SessionLocal()
            try:
                cand = enrich.find_incomplete_leads(
                    tdb, source=source, category=category, city=city, limit=idx_max,
                )
                n_cand = len(cand)
            finally:
                tdb.close()
            eff_max = max(n_cand, 1) if not (max_results and max_results > 0) else max_results
            # dependenc: target list untuk dapodik
            targets = [c.nama_instansi for c in cand][:eff_max]
        else:
            eff_max = max_results if max_results and max_results > 0 else 100
            targets = []

        db = SessionLocal()
        try:
            job = store.create_job(db, source, category, city, eff_max)
            job_id = job.id
        finally:
            db.close()

        cls = ScraperRegistry.get_class(source)
        if source == "dapodik":
            # Dapodik mencari per NAMA SEKOLAH → kirim daftar target kandidat
            scraper = cls(
                category=category, city=city, max_results=eff_max,
                targets=targets,
            )
        else:
            scraper = cls(category=category, city=city, max_results=eff_max)
        self._running[job_id] = scraper
        scraper.set_progress_callback(
            lambda progress, total, message: self._on_progress(job_id, progress, total, message)
        )
        t = threading.Thread(target=self._run, args=(job_id, scraper), daemon=True)
        self._threads[job_id] = t
        self._last_progress[job_id] = time.time()
        t.start()
        return {"id": job_id, "status": "running"}

    def is_managed(self, job_id: str) -> bool:
        """True jika job masih aktif di memori server (bisa di-cancel)."""
        return job_id in self._running

    def _on_progress(self, job_id: str, progress: int, total: int, message: str) -> None:
        db = SessionLocal()
        try:
            store.update_job(db, job_id, progress=progress, total_found=total)
            if message:
                store.append_job_log(db, job_id, message)
            self._last_progress[job_id] = time.time()
        except Exception:
            pass
        finally:
            db.close()

    def _run(self, job_id: str, scraper) -> None:
        db = SessionLocal()
        try:
            store.update_job(db, job_id, status="running")
        finally:
            db.close()

        try:
            raw_items = scraper.run()
            db = SessionLocal()
            try:
                if scraper.source in enrich.ENRICHMENT_FIELDS:
                    self._run_enrichment(db, job_id, scraper, raw_items)
                else:
                    self._run_seed(db, job_id, scraper, raw_items)
            finally:
                db.close()
        except Exception as e:
            db = SessionLocal()
            try:
                store.append_job_log(db, job_id, f"ERROR: {e}\n{traceback.format_exc()[-800:]}")
                store.update_job(db, job_id, status="error", finished_at=datetime.utcnow())
            finally:
                db.close()
        finally:
            self._running.pop(job_id, None)
            self._threads.pop(job_id, None)
            self._last_progress.pop(job_id, None)

    def _run_seed(self, db, job_id: str, scraper, raw_items) -> None:
        """Seed (GMaps): simpan hasil scrape sebagai lead (via cleaner + upsert).

        Simpan angka real `items_created`/`items_updated` (berapa lead yang
        benar-benar terambil/terpindah ke DB) — berbeda dari `total_found`
        yang hanya berapa hasil yang diterrakan di situs.
        """
        stat = store.save_raw_items(db, raw_items, source=scraper.source)
        created, updated = stat.get("created", 0), stat.get("updated", 0)
        store.update_job(db, job_id, items_created=created, items_updated=updated)
        store.append_job_log(db, job_id, f"Tersimpan: {created} baru, {updated} update.")
        if scraper.is_cancelled():
            # Status sudah "cancelled" (diset JobManager.cancel) —
            # jangan timpa menjadi "completed".
            store.append_job_log(
                db, job_id,
                f"Job dihentikan — {created} baru, {updated} update tercatat sebelum berhenti.",
            )
        else:
            store.update_job(db, job_id, status="completed", progress=len(raw_items), total_found=len(raw_items), finished_at=datetime.utcnow())

    def _run_enrichment(self, db, job_id: str, scraper, raw_items) -> None:
        """Enrichment (jobstreet/glints/lpse/dapodik): cocokkan hasil ke lead seed
        & isi hanya field kosong — TIDAK membuat lead baru.

        Target lead diambil dari DB berdasar `category` & `city` input user
        (liat enrichment_service.find_incomplete_leads). Jumlah target dibatasi
        `scraper.max_results` (maks. hasil). Progress = jumlah lead yang diisi.
        """
        try:
            result = enrich.match_and_merge(
                db,
                source=scraper.source,
                raw_items=raw_items,
                progress_cb=lambda prog, total, msg: self._on_progress(job_id, prog, total, msg),
                cancel_check=scraper.is_cancelled,
                category=scraper.category,
                city=scraper.city,
                limit=scraper.max_results,
            )
        except Exception:
            raise
        store.append_job_log(
            db, job_id,
            f"Enrichment {scraper.source} ({scraper.category} @ {scraper.city}): "
            f"{result['matched']} lead diisi, {result['filled']} field terisi, "
            f"{result['candidates']} kandidat, {len(result['unmatched'])} tidak match (review manual).",
        )
        # items_created = matched (lead yang field-nya terisi) — berapa yg "terambil"
        store.update_job(db, job_id, items_created=result["matched"], items_updated=0)
        if scraper.is_cancelled():
            store.append_job_log(
                db, job_id,
                f"Job dihentikan — {result['matched']} lead sudah terisi sebelum berhenti.",
            )
        else:
            store.update_job(
                db, job_id,
                status="completed",
                progress=result["matched"],
                total_found=result["matched"],
                finished_at=datetime.utcnow(),
            )

    def cancel(self, job_id: str) -> bool:
        scraper = self._running.get(job_id)
        if scraper is None:
            return False
        scraper.cancel()
        db = SessionLocal()
        try:
            store.update_job(db, job_id, status="cancelled", finished_at=datetime.utcnow())
        finally:
            db.close()
        self._running.pop(job_id, None)
        self._threads.pop(job_id, None)
        self._last_progress.pop(job_id, None)
        return True

    # ---- Reconcile / watchdog status ----
    # Dipanggil tiap kali frontend polling GET /api/jobs. Menyamakan status
    # job "pending/running" di DB dengan realita proses, sehingga status tidak
    # stuck di "running" ketika: server restart, thread scraper mati,
    # browser Chrome ditutup manual, atau proses hang tanpa progres.

    def reconcile(self, db) -> int:
        """Perbaiki job stuck. Return jumlah job yang diperbaiki."""
        stale_seconds = settings.job_stale_seconds
        now = time.time()
        fixed = 0
        stuck = db.query(ScrapeJob).filter(ScrapeJob.status.in_(("pending", "running"))).all()
        for job in stuck:
            scraper = self._running.get(job.id)
            thread = self._threads.get(job.id)
            reason = None
            if scraper is None or thread is None or not thread.is_alive():
                # Grace period: job baru saja di-start (thread belum sempat hidup) → jangan dikoreksi
                if now - self._last_progress.get(job.id, 0) < 10:
                    continue
                reason = "Proses terhenti: job tidak aktif di server (restart/crash). Status dikoreksi otomatis."
            elif not scraper.is_alive():
                reason = "Proses terhenti: browser/proses scraper ditutup sebelum selesai. Status dikoreksi otomatis."
            elif now - self._last_progress.get(job.id, now) > stale_seconds:
                try:
                    scraper.cancel()
                except Exception:
                    pass
                reason = f"Proses terhenti: tidak ada progres >{stale_seconds} detik (diduga hang). Status dikoreksi otomatis."
            if reason:
                self._finish_dead(db, job, reason)
                self._running.pop(job.id, None)
                self._threads.pop(job.id, None)
                self._last_progress.pop(job.id, None)
                fixed += 1
        return fixed

    def _finish_dead(self, db, job: ScrapeJob, reason: str) -> None:
        try:
            store.append_job_log(db, job.id, reason)
        except Exception:
            pass
        store.update_job(db, job.id, status="error", finished_at=datetime.utcnow())


job_manager = JobManager()