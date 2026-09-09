"""Generator kode unik untuk Lead, Kategori, dan Kota.

Format:
- Lead:       LD-{KATEGORI}-{001}   (contoh: LD-SEKOLAH-001, LD-UMKM-002)
- Kategori:   KAT-{KATEGORI}-{001}  (contoh: KAT-SEKOLAH-001, KAT-IT-002)
- Kota:       K-{KOTA}-{001}        (contoh: K-SALATIGA-001, K-SEMARANG-002)
"""
import re
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.category import Category
from backend.models.city import City
from backend.models.lead import Lead


def _slug(text: str) -> str:
    """Bersihkan teks menjadi slug huruf kapital aman untuk kode (misal 'Sekolah Dasar' -> 'SEKOLAH')."""
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '', text or '').upper()
    return cleaned[:10] if cleaned else "GEN"


clean_code_segment = _slug


def generate_category_code(db: Session, category_name: str) -> str:
    """Generate kode kategori unik format KAT-{KATEGORI}-{001}."""
    tag = _slug(category_name)
    prefix = f"KAT-{tag}-"
    last = (
        db.query(Category.kode)
        .filter(Category.kode.like(f"{prefix}%"))
        .order_by(Category.id.desc())
        .first()
    )
    next_seq = 1
    if last and last[0]:
        m = re.search(r'-(\d+)$', last[0])
        if m:
            next_seq = int(m.group(1)) + 1
    return f"{prefix}{next_seq:03d}"


def generate_city_code(db: Session, city_name: str) -> str:
    """Generate kode kota unik format K-{KOTA}-{001}."""
    tag = _slug(city_name)
    prefix = f"K-{tag}-"
    last = (
        db.query(City.kode)
        .filter(City.kode.like(f"{prefix}%"))
        .order_by(City.id.desc())
        .first()
    )
    next_seq = 1
    if last and last[0]:
        m = re.search(r'-(\d+)$', last[0])
        if m:
            next_seq = int(m.group(1)) + 1
    return f"{prefix}{next_seq:03d}"


def generate_lead_code(db: Session, category_name: str) -> str:
    """Generate kode lead unik format LD-{KATEGORI}-{001}."""
    tag = _slug(category_name)
    prefix = f"LD-{tag}-"
    last = (
        db.query(Lead.kode)
        .filter(Lead.kode.like(f"{prefix}%"))
        .order_by(Lead.id.desc())
        .first()
    )
    next_seq = 1
    if last and last[0]:
        m = re.search(r'-(\d+)$', last[0])
        if m:
            next_seq = int(m.group(1)) + 1
    else:
        # Jika belum ada prefix spesifik, hitung total leads kategori ini
        count = (
            db.query(func.count(Lead.id))
            .join(Category, Lead.category_id == Category.id, isouter=True)
            .filter(func.lower(Category.name) == category_name.strip().lower())
            .scalar() or 0
        )
        next_seq = count + 1
    return f"{prefix}{next_seq:03d}"
