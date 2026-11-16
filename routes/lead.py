"""Lead routes — deklarasi endpoint leads, stats, export, dedup, import."""
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.Middleware.auth_middleware import require_auth
from app.Models import get_db
from app.Controllers.LeadController import LeadController, LeadUpdate, LeadBulkDelete, ResolveRequest

router = APIRouter()


@router.get("/stats")
def get_stats(_: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return LeadController.get_stats(db)


@router.get("/leads")
def list_leads(
    search: str = "",
    source: str = "",
    kota: str = "",
    category: str = "",
    status: str = "",
    page: int = 1,
    size: int = 25,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    return LeadController.list_leads(
        db, search=search, source=source, kota=kota, category=category, status=status,
        page=page, size=size, sort_by=sort_by, sort_dir=sort_dir,
    )


@router.get("/filters")
def get_filters(_: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return LeadController.get_filters(db)


@router.patch("/leads/{lead_id}")
def update_lead(
    lead_id: int,
    req: LeadUpdate,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    return LeadController.update_lead(lead_id, req, db)


@router.delete("/leads/{lead_id}")
def delete_lead(
    lead_id: int,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    return LeadController.delete_lead(lead_id, db)


@router.post("/leads/delete-bulk")
def delete_leads_bulk(
    req: LeadBulkDelete,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    return LeadController.delete_leads_bulk(req, db)


@router.get("/export")
def export_xlsx(
    source: str = "",
    kota: str = "",
    category: str = "",
    status: str = "",
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return LeadController.export_xlsx(db, source=source, kota=kota, category=category, status=status)


@router.get("/export-csv")
def export_csv(
    source: str = "",
    kota: str = "",
    category: str = "",
    status: str = "",
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    return LeadController.export_csv(db, source=source, kota=kota, category=category, status=status)


@router.get("/duplicates")
def duplicates(_: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return LeadController.duplicates(db)


@router.post("/duplicates/resolve")
def resolve_dup(
    req: ResolveRequest,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    return LeadController.resolve_dup(req, db)


@router.post("/import")
async def import_csv(
    file: UploadFile,
    source: str = "",
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    return await LeadController.import_csv(file, source, db)
