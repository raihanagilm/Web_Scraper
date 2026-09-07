"""Lead routes: statistik, query, update status, export, dedup review, import."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.deps import require_auth
from backend.models import get_db
from backend.services import storage_service as store
from backend.services.dedup_service import find_duplicate_groups, resolve_group
from backend.services.exporter import export_leads
from backend.services.importer import import_csv_text

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/stats")
def get_stats(_: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return store.stats(db)


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
    if page < 1 or size < 1:
        raise HTTPException(status_code=422, detail="page/size minimal 1")
    return store.query_leads(
        db, search=search, source=source, kota=kota, category=category, status=status,
        page=page, size=size, sort_by=sort_by, sort_dir=sort_dir,
    )


@router.get("/filters")
def get_filters(_: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    """Opsi untuk dropdown filter Results: sumber (tanpa duplikat), kota & kategori dari DB."""
    from backend.services.job_manager import ScraperRegistry

    sources = sorted(set(ScraperRegistry.list_sources()) | set(store.list_distinct_sources(db)))
    return {
        "sources": sources,
        "cities": store.list_cities(db),
        "categories": store.list_categories(db),
    }


class LeadUpdate(BaseModel):
    """Semua field opsional — hanya field yang dikirim yang diubah (edit data)."""

    nama_instansi: str | None = None
    kategori: str | None = None
    telp: str | None = None
    email: str | None = None
    alamat: str | None = None
    kota: str | None = None
    link_gmaps: str | None = None
    website: str | None = None
    sosmed: str | None = None
    link_source: str | None = None
    status: str | None = None
    npsn: str | None = None
    nama_kepsek: str | None = None
    posisi_rekrutmen: str | None = None
    deskripsi_it: str | None = None
    penanggung_jawab: str | None = None


@router.patch("/leads/{lead_id}")
def update_lead(
    lead_id: int,
    req: LeadUpdate,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    lead = store.update_lead_full(db, lead_id, req.model_dump())
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"ok": True, **store._lead_to_dict(lead)}


@router.delete("/leads/{lead_id}")
def delete_lead(
    lead_id: int,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    if not store.get_lead(db, lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    deleted = store.delete_leads(db, [lead_id])
    return {"ok": True, "deleted": deleted}


class LeadBulkDelete(BaseModel):
    ids: list[int]


@router.post("/leads/delete-bulk")
def delete_leads_bulk(
    req: LeadBulkDelete,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    if not req.ids:
        raise HTTPException(status_code=422, detail="ids tidak boleh kosong")
    deleted = store.delete_leads(db, req.ids)
    return {"ok": True, "deleted": deleted}


@router.get("/export")
def export_xlsx(
    source: str = "",
    kota: str = "",
    category: str = "",
    status: str = "",
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    res = store.query_leads(db, source=source, kota=kota, category=category, status=status, page=1, size=100000)
    if not res["items"]:
        raise HTTPException(status_code=400, detail="Tidak ada data untuk diekspor")
    filepath = export_leads(res["items"])
    return FileResponse(
        filepath,
        filename=Path(filepath).name,
        media_type=XLSX_MIME,
    )


@router.get("/export-csv")
def export_csv(
    source: str = "",
    kota: str = "",
    category: str = "",
    status: str = "",
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    from datetime import datetime

    from fastapi.responses import Response

    from backend.services.exporter import export_leads_csv

    res = store.query_leads(db, source=source, kota=kota, category=category, status=status, page=1, size=100000)
    if not res["items"]:
        raise HTTPException(status_code=400, detail="Tidak ada data untuk diekspor")
    content = export_leads_csv(res["items"])
    ts = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
    safe = (kota or source or "leads").replace("/", "_").replace("\\", "_")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="Leads_{safe}_{ts}.csv"'},
    )


@router.get("/duplicates")
def duplicates(_: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    groups = find_duplicate_groups(db)
    out = []
    for g in groups:
        members = [store._lead_to_dict(store.get_lead(db, mid)) for mid in g["members"]]
        out.append({**g, "member_data": members})
    return {"groups": out}


class ResolveRequest(BaseModel):
    group_key: str
    member_ids: list[int]
    action: str  # keep | merge | delete_all
    winner_id: int | None = None
    field_choices: dict = {}


@router.post("/duplicates/resolve")
def resolve_dup(
    req: ResolveRequest,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return resolve_group(
            db, req.group_key, req.member_ids, req.action, req.winner_id, req.field_choices
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import")
async def import_csv(
    file: UploadFile,
    source: str = "",
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        return import_csv_text(db, text, source=source)
    except Exception as e:  # parser/file tidak valid
        raise HTTPException(status_code=400, detail=f"Import gagal: {e}")
