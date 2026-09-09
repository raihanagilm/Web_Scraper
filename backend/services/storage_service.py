"""Storage Service: menyimpan & mengambil data lead dari MySQL (TiDB)."""
from datetime import datetime
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Category, City, Lead, ScrapeJob
from backend.services.cleaner import clean_lead
from backend.services.code_generator import (
    generate_category_code,
    generate_city_code,
    generate_lead_code,
)

# Field base + extras yang bisa dipakai upsert
LEAD_FIELDS = [
    "kode", "source", "priority", "nama_instansi", "kategori", "telp", "email",
    "alamat", "kota", "link_gmaps", "website", "sosmed",
    "instagram", "facebook", "linkedin", "twitter_x", "tiktok", "link_source",
    "status", "npsn", "nama_kepsek",
]

# Field yang dinormalisasi ke tabel lookup (bukan kolom string langsung)
FK_FIELDS = {"kategori": "category_id", "kota": "city_id"}

# Kolom yang boleh dipakai sorting (whitelist aman dari SQL injection)
SORTABLE_COLUMNS = {
    "kode": lambda: Lead.kode,
    "nama_instansi": lambda: Lead.nama_instansi,
    "kategori": lambda: Category.name,
    "telp": lambda: Lead.telp,
    "email": lambda: Lead.email,
    "alamat": lambda: Lead.alamat,
    "kota": lambda: City.name,
    "link_gmaps": lambda: Lead.link_gmaps,
    "website": lambda: Lead.website,
    "sosmed": lambda: Lead.sosmed,
    "instagram": lambda: Lead.instagram,
    "facebook": lambda: Lead.facebook,
    "linkedin": lambda: Lead.linkedin,
    "twitter_x": lambda: Lead.twitter_x,
    "tiktok": lambda: Lead.tiktok,
    "link_source": lambda: Lead.link_source,
    "source": lambda: Lead.source,
    "status": lambda: Lead.status,
    "npsn": lambda: Lead.npsn,
    "nama_kepsek": lambda: Lead.nama_kepsek,
    "created_at": lambda: Lead.created_at,
    "updated_at": lambda: Lead.updated_at,
}


def _get_or_create_category(db: Session, name: str) -> Category | None:
    """Cari/create Category berdasarkan nama (case-insensitive, auto-create)."""
    name = (name or "").strip()
    if not name:
        return None
    found = db.query(Category).filter(func.lower(Category.name) == name.lower()).first()
    if found:
        return found
    cat_code = generate_category_code(db, name)
    cat = Category(name=name, kode=cat_code)
    db.add(cat)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        found = db.query(Category).filter(func.lower(Category.name) == name.lower()).first()
        return found
    return cat


def _get_or_create_city(db: Session, name: str) -> City | None:
    """Cari/create City berdasarkan nama (case-insensitive, auto-create)."""
    name = (name or "").strip()
    if not name:
        return None
    found = db.query(City).filter(func.lower(City.name) == name.lower()).first()
    if found:
        return found
    city_code = generate_city_code(db, name)
    city = City(name=name, kode=city_code)
    db.add(city)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        found = db.query(City).filter(func.lower(City.name) == name.lower()).first()
        return found
    return city


def _resolve_refs(db: Session, clean: dict) -> tuple[Category | None, City | None]:
    """Resolve nama kategori & kota dari data bersih ke objek FK (auto-create)."""
    category = _get_or_create_category(db, clean.get("kategori") or "")
    city = _get_or_create_city(db, clean.get("kota") or "")
    return category, city


def _build_lead(db: Session, clean: dict, category: Category | None, city: City | None) -> Lead:
    """Buat instance Lead dari data bersih + referensi FK + generate kode bisnis unik."""
    kwargs = {f: clean.get(f) for f in LEAD_FIELDS}
    kwargs.pop("kategori", None)
    kwargs.pop("kota", None)
    kwargs["category_id"] = category.id if category else None
    kwargs["city_id"] = city.id if city else None
    if not kwargs.get("kode"):
        cat_name = category.name if category else (clean.get("kategori") or "GEN")
        kwargs["kode"] = generate_lead_code(db, cat_name)
    return Lead(**kwargs)


def upsert_lead(db: Session, data: dict) -> tuple[Lead, bool]:
    """Insert lead baru; jika (source, nama_instansi, city_id) sudah ada → update field kosong.

    `kategori`/`kota` dari input (string) otomatis di-resolve ke tabel lookup
    `categories`/`cities` (auto-create bila belum ada).

    Returns (lead, is_created).
    """
    clean = clean_lead(data)
    source = clean.get("source", "gmaps")
    nama = clean.get("nama_instansi", "")
    category, city = _resolve_refs(db, clean)

    lead = (
        db.query(Lead)
        .filter(
            Lead.source == source,
            Lead.nama_instansi == nama,
            Lead.city_id == (city.id if city else None),
        )
        .first()
    )
    if lead:
        changed = False
        # Generate kode jika belum ada
        if not lead.kode:
            cat_name = category.name if category else "GEN"
            lead.kode = generate_lead_code(db, cat_name)
            changed = True
        # FK kategori/kota
        if category is not None and lead.category_id in (None, 0):
            lead.category_id = category.id
            changed = True
        if city is not None and lead.city_id in (None, 0):
            lead.city_id = city.id
            changed = True
        # field biasa: isi yang kosong / placeholder
        for f in LEAD_FIELDS:
            if f in FK_FIELDS or f == "kode":
                continue
            new_val = clean.get(f)
            old_val = getattr(lead, f)
            if new_val and (old_val in (None, "", "-")):
                setattr(lead, f, new_val)
                changed = True
        lead.updated_at = datetime.utcnow()
        db.add(lead)
        db.commit()
        db.refresh(lead)
        return lead, False
    # create baru
    lead = _build_lead(db, clean, category, city)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead, True


def save_raw_items(db: Session, items: list[dict], source: str, progress_cb=None) -> dict:
    """Simpan banyak hasil scraper dengan callback progress bertahap. Return statistik."""
    created = 0
    updated = 0
    total = len(items)
    for i, item in enumerate(items):
        item.setdefault("source", source)
        _lead, created_flag = upsert_lead(db, item)
        if created_flag:
            created += 1
        else:
            updated += 1
        if progress_cb:
            nama = (item.get("nama_instansi") or f"Data #{i+1}").strip()
            progress_cb(i + 1, total, f"Menyimpan ke database: {i + 1}/{total} — {nama}")
    return {"created": created, "updated": updated}


def get_lead(db: Session, lead_id: int) -> Lead | None:
    return db.query(Lead).filter(Lead.id == lead_id).first()


def delete_leads(db: Session, ids: list[int]) -> int:
    """Hapus lead berdasarkan daftar id. Return jumlah baris terhapus."""
    if not ids:
        return 0
    deleted = db.query(Lead).filter(Lead.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return deleted


# ---- Opsi filter (dropdown) ----

def list_cities(db: Session) -> list[str]:
    """Daftar nama kota unik dari tabel cities (urut abjad)."""
    return [name for (name,) in db.query(City.name).order_by(City.name.asc()).all() if name]


def list_categories(db: Session) -> list[str]:
    """Daftar nama kategori unik dari tabel categories (urut abjad)."""
    return [name for (name,) in db.query(Category.name).order_by(Category.name.asc()).all() if name]


def list_categories_with_cities(db: Session, source: str | None = None) -> dict[str, list[str]]:
    """Pasangan unik (Kategori → [Kota]) dari data leads yang ADA di DB.

    Dipakai dropdown Enrichment agar pengguna hanya bisa memilih kombinasi
    Kategori + Kota yang benar-benar sudah pernah di-scrape (ada di tabel
    Results). `source` membatasi asal lead (mis. ``"gmaps"`` = data seed).
    """
    q = (
        db.query(Category.name, City.name)
        .join(Lead, Lead.category_id == Category.id)
        .join(City, Lead.city_id == City.id)
    )
    if source:
        q = q.filter(Lead.source == source)
    rows = q.distinct().order_by(Category.name.asc(), City.name.asc()).all()
    out: dict[str, list[str]] = {}
    for cat, city in rows:
        if cat and city:
            out.setdefault(cat, []).append(city)
    return out


def list_distinct_sources(db: Session) -> list[str]:
    """Daftar sumber unik yang sudah ada di data leads."""
    return [s for (s,) in db.query(Lead.source).distinct().all() if s]


def update_lead_full(db: Session, lead_id: int, data: dict) -> Lead | None:
    """Update field lead secara detail (edit data).

    `kategori`/`kota` (string) di-resolve ke FK lookup (string kosong → NULL).
    Field yang tidak ada di `data` tidak diubah.
    """
    lead = get_lead(db, lead_id)
    if not lead:
        return None

    for f in LEAD_FIELDS:
        if f in FK_FIELDS:
            continue
        if f in data and data[f] is not None:
            setattr(lead, f, str(data[f]).strip())

    if "kategori" in data:
        if (data.get("kategori") or "").strip():
            cat = _get_or_create_category(db, data["kategori"])
            lead.category_id = cat.id if cat else None
        else:
            lead.category_id = None

    if "kota" in data:
        if (data.get("kota") or "").strip():
            city = _get_or_create_city(db, data["kota"])
            lead.city_id = city.id if city else None
        else:
            lead.city_id = None

    lead.updated_at = datetime.utcnow()
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def query_leads(
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
    """Query leads dengan filter, pencarian, sorting, dan paging.

    - search mencakup: nama_instansi, alamat, email, kategori (nama lookup), kota.
    - sort_by di-whitelist lewat SORTABLE_COLUMNS; kategori/kota sort via join.
    """
    # outer join ke lookup agar bisa sort/filter berdasarkan nama kategori & kota
    q = (
        db.query(Lead)
        .join(Category, Lead.category_id == Category.id, isouter=True)
        .join(City, Lead.city_id == City.id, isouter=True)
    )
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                Lead.kode.ilike(like),
                Lead.nama_instansi.ilike(like),
                Lead.alamat.ilike(like),
                Lead.email.ilike(like),
                Category.name.ilike(like),
                City.name.ilike(like),
            )
        )
    if source:
        q = q.filter(Lead.source == source)
    if kota:
        q = q.filter(City.name.ilike(f"%{kota}%"))
    if category:
        q = q.filter(Category.name.ilike(f"%{category}%"))
    if status:
        q = q.filter(Lead.status == status)

    # sorting (whitelist)
    col = SORTABLE_COLUMNS.get(sort_by, Lead.updated_at)()
    order = col.asc() if sort_dir.lower() == "asc" else col.desc()
    # tiebreaker: id agar stabil antar halaman
    q = q.order_by(order, Lead.id.asc())

    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size, "items": [_lead_to_dict(x) for x in items]}


def _lead_to_dict(lead: Lead) -> dict:
    d = {f: getattr(lead, f) for f in LEAD_FIELDS}
    d["id"] = lead.id
    d["created_at"] = lead.created_at.isoformat() if lead.created_at else None
    d["updated_at"] = lead.updated_at.isoformat() if lead.updated_at else None
    return d


def stats(db: Session) -> dict:
    total = db.query(func.count(Lead.id)).scalar() or 0
    by_source = dict(db.query(Lead.source, func.count(Lead.id)).group_by(Lead.source).all())
    by_city = dict(
        db.query(func.coalesce(City.name, ""), func.count(Lead.id))
        .join(City, Lead.city_id == City.id, isouter=True)
        .group_by(City.name)
        .all()
    )
    by_status = dict(db.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all())
    return {
        "total_leads": total,
        "by_source": by_source,
        "by_city": by_city,
        "by_status": by_status,
    }


import re
import uuid

# ---- ScrapeJob helpers ----

def generate_job_id(category: str) -> str:
    """Generate ID job format ringkas: SCRP_{kategori[:14]}_{YYYYMMDD_HHMMSS}.

    Total panjang dijamin <= 35 karakter sehingga aman di kolom VARCHAR(36).
    """
    clean_cat = re.sub(r'[^a-zA-Z0-9]+', '_', (category or "general").strip().lower()).strip('_')[:14] or "general"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"SCRP_{clean_cat}_{timestamp}"


def create_job(
    db: Session,
    source: str,
    category: str,
    city: str,
    max_results: int,
    job_id: str | None = None,
) -> ScrapeJob:
    jid = job_id or generate_job_id(category)
    # Pastikan jid unik jika ada bentrok detik yang sama
    existing = db.query(ScrapeJob).filter(ScrapeJob.id == jid).first()
    if existing:
        jid = f"{jid[:30]}_{uuid.uuid4().hex[:4]}"

    job = ScrapeJob(
        id=jid,
        source=source,
        category=category,
        city=city,
        max_results=max_results,
        status="pending",
        progress=0,
        total_found=0,
        items_created=0,
        items_updated=0,
        log="",
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def find_or_create_job(
    db: Session,
    source: str,
    category: str,
    city: str,
    max_results: int,
    job_id: str | None = None,
) -> ScrapeJob:
    """Jika job_id diberikan (dari aksi Ulangi / Lengkapi): update data riwayat job yang diklik.
    Jika job_id None: buat job baru (tidak pernah menimpa job sebelumnya).
    """
    if not job_id:
        return create_job(db, source, category, city, max_results)

    job = db.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
    if job:
        job.status = "pending"
        job.started_at = datetime.utcnow()
        job.finished_at = None
        job.max_results = max_results
        job.progress = 0
        job.items_created = 0
        job.items_updated = 0
        job.log = f"Job diperbarui pada {datetime.utcnow().strftime('%d %b %Y %H:%M')}\n"
        db.commit()
        db.refresh(job)
        return job

    return create_job(db, source, category, city, max_results, job_id=job_id)


def update_job(db: Session, job_id: str, **fields) -> None:
    db.query(ScrapeJob).filter(ScrapeJob.id == job_id).update(fields)
    db.commit()


def append_job_log(db: Session, job_id: str, line: str) -> None:
    job = db.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
    if not job:
        return
    new_log = (job.log or "") + line + "\n"
    db.query(ScrapeJob).filter(ScrapeJob.id == job_id).update({"log": new_log[-4000:]})
    db.commit()


def get_job(db: Session, job_id: str) -> ScrapeJob | None:
    return db.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()


def delete_job(db: Session, job_id: str) -> int:
    """Hapus 1 baris riwayat job (audit log). Return jumlah baris terhapus."""
    deleted = db.query(ScrapeJob).filter(ScrapeJob.id == job_id).delete()
    db.commit()
    return deleted


def list_jobs(db: Session, limit: int = 20) -> list[dict]:
    jobs = db.query(ScrapeJob).order_by(ScrapeJob.started_at.desc()).limit(limit).all()
    return [
        {
            "id": j.id,
            "source": j.source,
            "category": j.category,
            "city": j.city,
            "max_results": j.max_results,
            "status": j.status,
            "progress": j.progress,
            "total_found": j.total_found,
            "items_created": getattr(j, "items_created", 0),
            "items_updated": getattr(j, "items_updated", 0),
            "log": j.log,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in jobs
    ]