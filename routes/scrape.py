"""Scrape routes — deklarasi endpoint scrape, jobs, enrichment, monitoring."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.Middleware.auth_middleware import require_auth
from app.Models import get_db
from app.Controllers.ScrapeController import (
    ScrapeController,
    ScrapeRequest,
    EnrichmentRequest,
)

router = APIRouter()


@router.get("/sources")
def list_sources(_: dict = Depends(require_auth)) -> dict:
    return ScrapeController.list_sources()


@router.post("/scrape")
def start_scrape(req: ScrapeRequest, request: Request, _: dict = Depends(require_auth)) -> dict:
    return ScrapeController.start_scrape(req, request)


@router.post("/enrich")
def start_enrichment(req: EnrichmentRequest, request: Request, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return ScrapeController.start_enrichment(req, db, request)


@router.get("/enrich/options")
def enrich_options(_: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return ScrapeController.enrich_options(db)


@router.get("/jobs")
def list_jobs(limit: int = 20, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return ScrapeController.list_jobs(db, limit=limit)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return ScrapeController.get_job(job_id, db)


@router.get("/jobs/{job_id}/incomplete")
def get_job_incomplete_leads(
    job_id: str,
    limit: int = 100,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    return ScrapeController.get_job_incomplete_leads(job_id, db, limit=limit)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, _: dict = Depends(require_auth)) -> dict:
    return ScrapeController.cancel_job(job_id)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return ScrapeController.delete_job(job_id, db)


@router.get("/browser-status")
def browser_status(request: Request, _: dict = Depends(require_auth)) -> dict:
    return ScrapeController.browser_status(request)


@router.post("/browser-login")
def browser_login(request: Request, _: dict = Depends(require_auth)) -> dict:
    return ScrapeController.browser_login(request)
