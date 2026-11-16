"""LeadController — Menangani logika bisnis endpoint leads, stats, export, dedup, import."""
from pathlib import Path
from datetime import datetime
from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.Services import storage_service as store
from app.Services.dedup_service import find_duplicate_groups, resolve_group
from app.Services.exporter import export_leads, export_leads_csv
from app.Services.importer import import_csv_text
from app.Services.job_manager import ScraperRegistry

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class LeadUpdate(BaseModel):
    nama_instansi: str | None = None
    kategori: str | None = None
    telp: str | None = None
    email: str | None = None
    alamat: str | None = None
    kota: str | None = None
    link_gmaps: str | None = None
    website: str | None = None
    sosmed: str | None = None
    instagram: str | None = None
    facebook: str | None = None
    linkedin: str | None = None
    twitter_x: str | None = None
    tiktok: str | None = None
    link_source: str | None = None
    status: str | None = None
    npsn: str | None = None
    nama_kepsek: str | None = None


class LeadBulkDelete(BaseModel):
    ids: list[int]


class ResolveRequest(BaseModel):
    group_key: str
    member_ids: list[int]
    action: str  # keep | merge | delete_all
    winner_id: int | None = None
    field_choices: dict = {}


class LeadController:
    @staticmethod
    def get_stats(db: Session) -> dict:
        return store.stats(db)

    @staticmethod
    def list_leads(
        db: Session,
        search: str = "",
        source: str = "",
        kota: str = "",
        category: str = "",
        status: str = "",
        page: int = 1,
        size: int = 25,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
    ) -> dict:
        if page < 1 or size < 1:
            raise HTTPException(status_code=422, detail="page/size minimal 1")
        return store.query_leads(
            db, search=search, source=source, kota=kota, category=category, status=status,
            page=page, size=size, sort_by=sort_by, sort_dir=sort_dir,
        )

    @staticmethod
    def get_filters(db: Session) -> dict:
        sources = sorted(set(ScraperRegistry.list_sources()) | set(store.list_distinct_sources(db)))
        return {
            "sources": sources,
            "cities": store.list_cities(db),
            "categories": store.list_categories(db),
        }

    @staticmethod
    def update_lead(lead_id: int, req: LeadUpdate, db: Session) -> dict:
        lead = store.update_lead_full(db, lead_id, req.model_dump())
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        return {"ok": True, **store._lead_to_dict(lead)}

    @staticmethod
    def delete_lead(lead_id: int, db: Session) -> dict:
        if not store.get_lead(db, lead_id):
            raise HTTPException(status_code=404, detail="Lead not found")
        deleted = store.delete_leads(db, [lead_id])
        return {"ok": True, "deleted": deleted}

    @staticmethod
    def delete_leads_bulk(req: LeadBulkDelete, db: Session) -> dict:
        if not req.ids:
            raise HTTPException(status_code=422, detail="ids tidak boleh kosong")
        deleted = store.delete_leads(db, req.ids)
        return {"ok": True, "deleted": deleted}

    @staticmethod
    def export_xlsx(
        db: Session,
        source: str = "",
        kota: str = "",
        category: str = "",
        status: str = "",
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

    @staticmethod
    def export_csv(
        db: Session,
        source: str = "",
        kota: str = "",
        category: str = "",
        status: str = "",
    ):
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

    @staticmethod
    def duplicates(db: Session) -> dict:
        groups = find_duplicate_groups(db)
        out = []
        for g in groups:
            members = [store._lead_to_dict(store.get_lead(db, mid)) for mid in g["members"]]
            out.append({**g, "member_data": members})
        return {"groups": out}

    @staticmethod
    def resolve_dup(req: ResolveRequest, db: Session) -> dict:
        try:
            return resolve_group(
                db, req.group_key, req.member_ids, req.action, req.winner_id, req.field_choices
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @staticmethod
    async def import_csv(file: UploadFile, source: str, db: Session) -> dict:
        text = (await file.read()).decode("utf-8-sig", errors="replace")
        try:
            return import_csv_text(db, text, source=source)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Import gagal: {e}")
