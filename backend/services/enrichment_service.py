"""Enrichment Service — mengisi field pendukung lead hasil seed (PRD v1.1 §5.3).

Prinsip (Seed → Enrichment → Merge):
- Google Maps = sumber utama (seed) yang menghasilkan daftar leads dasar.
- Sumber pendukung (Dapodik / Google Search) HANYA dipakai
  sebagai enrichment: mencocokkan hasil scrape ke lead seed yang field
  pendukungnya masih kosong, lalu mengisi field kosong itu (merge field-level).
- Enrichment TIDAK membuat lead baru; hasil yang gagal match dilaporkan
  (dilog di job) untuk review manual, bukan otomatis disimpan.

Mapping kategori ke sumber enrichment (PRD v1.1):
- Sekolah → Dapodik Kemendikbud (NPSN, Nama Kepsek, Email) & Google Search
- Entitas Lainnya → Google Search (Kontak umum: Telp/WA, Email, Web, IG, FB, LI, X, TikTok)
"""
import difflib
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models import Category, City, Lead
from backend.services.cleaner import normalize_name, normalize_website

# Field pendukung yang boleh diisi tiap sumber enrichment (PRD §5.1)
ENRICHMENT_FIELDS: dict[str, list[str]] = {
    "google": ["telp", "email", "website", "sosmed", "instagram", "facebook", "linkedin", "twitter_x", "tiktok"],            # Web Search (Kontak umum: WA/Telp, Email, Web, IG, FB, LI, X, TikTok)
    "dapodik": ["npsn", "nama_kepsek", "email", "link_source"],  # Sekolah (NPSN, Kepsek, Email, & Link Kemendikdasmen)
}

# Mapping kategori ke sumber enrichment (PRD v1.1 §5.3)
CATEGORY_ENRICHMENT_SOURCES: dict[str, list[str]] = {
    "sekolah": ["dapodik", "google"],
    "corporate": ["google"],
    "perusahaan": ["google"],
    "umkm": ["google"],
    "retail": ["google"],
    "resto": ["google"],
    "restoran": ["google"],
    "kafe": ["google"],
    "cafe": ["google"],
    "vendor": ["google"],
    "kontraktor": ["google"],
    "b2g": ["google"],
}

# Source yang berperan sebagai seed (target enrichment). PRD v1.1: GMaps = seed semua segmen.
SEED_SOURCES = {"gmaps"}


def get_enrichment_sources_for_category(category: str) -> list[str]:
    """Mengembalikan list sumber enrichment untuk kategori tertentu (PRD v1.1).

    Args:
        category: Nama kategori (sekolah, corporate, umkm, vendor, dll)

    Returns:
        List sumber enrichment yang tersedia untuk kategori tersebut.
    """
    cat = category.strip().lower()
    # Cari exact match dulu
    if cat in CATEGORY_ENRICHMENT_SOURCES:
        return CATEGORY_ENRICHMENT_SOURCES[cat]
    # Fallback: cari partial match
    for key, sources in CATEGORY_ENRICHMENT_SOURCES.items():
        if key in cat or cat in key:
            return sources
    return ["google"]

# Threshold kemiripan nama (fuzzy) untuk match di kota yang sama
MATCH_THRESHOLD = 0.75
# Tanpa kecocokan kota, butuh nama hampir identik
MATCH_THRESHOLD_NO_CITY = 0.9

_EMPTY = (None, "", "-")


def fields_for(source: str) -> list[str]:
    """Field pendukung yang bisa diisi oleh sumber enrichment tertentu."""
    return ENRICHMENT_FIELDS.get(source, [])


def _city_name(lead: Lead) -> str:
    return (lead.city.name if lead.city else "").strip().lower()


def _is_empty(val) -> bool:
    return val in _EMPTY or (isinstance(val, str) and not val.strip())


def find_incomplete_leads(
    db: Session,
    source: str,
    target_sources: set[str] | None = None,
    category: str = "",
    city: str = "",
    limit: int | None = None,
) -> list[Lead]:
    """Lead seed (default: gmaps) yang field pendukungnya masih kosong untuk `source`.

    Alur kerja enrichment (PRD v1.1 §5.3 + requirement menu Enrichment):
    - Target data = lead seed yang sudah ada di DB (menu Results).
    - Hanya lead yang cocok dengan parameter **Kategori** & **Kota** yang diinput
      pengguna yang dijadikan kandidat (filter ilike via tabel lookup).
    - Hanya lead yang field pendukungnya ADA yang masih kosong (NULL/blank/"-"),
      karena enrichment SELALU mengisi field kosong saja (tidak me-replace).

    Lead yang dibuat langsung dari sumber enrichment tidak diproses ulang
    (anti-loop). `limit` membatasi jumlah lead yang diproses sesuai "Maks. hasil".
    """
    fields = fields_for(source)
    if not fields:
        return []
    targets = target_sources if target_sources is not None else SEED_SOURCES
    q = (
        db.query(Lead)
        .join(Category, Lead.category_id == Category.id, isouter=True)
        .join(City, Lead.city_id == City.id, isouter=True)
        .filter(Lead.source.in_(targets))
    )
    if category.strip():
        q = q.filter(Category.name.ilike(f"%{category.strip()}%"))
    if city.strip():
        q = q.filter(City.name.ilike(f"%{city.strip()}%"))
    # kandidat = field pendukung ADA yang masih kosong (isi hanya yang kosong, jangan replace)
    conds = []
    for f in fields:
        col = getattr(Lead, f)
        conds.append(col.is_(None))
        conds.append(col == "")
        conds.append(col == "-")
    q = q.filter(or_(*conds))
    if limit:
        q = q.order_by(Lead.id.asc()).limit(limit)
    return q.all()


def _match_score(lead: Lead, item: dict) -> tuple[int, str]:
    """Skor kecocokan 1 hasil enrichment ke 1 lead. 0 = tidak match.

    Strategi (PRD §5.3): fuzzy match nama + kota; alternatif NPSN (Sekolah)
    atau domain website/email (Perusahaan/UMKM).
    """
    ln = normalize_name(lead.nama_instansi or "")
    iname = normalize_name(str(item.get("nama_instansi") or ""))
    if not ln or not iname:
        return 0, ""

    score = 0
    reasons: list[str] = []

    # --- NPSN (Sekolah): match terkuat ---
    item_npsn = str(item.get("npsn") or "").strip()
    if item_npsn and (lead.npsn or "").strip() and item_npsn == lead.npsn.strip():
        return 10, "NPSN sama"

    # --- Domain website sama ---
    item_web = str(item.get("website") or "").strip()
    if item_web and lead.website:
        d_item, d_lead = normalize_website(item_web), normalize_website(lead.website)
        if d_item and d_lead and d_item == d_lead:
            score += 3
            reasons.append("domain website sama")

    # --- Email sama ---
    item_email = str(item.get("email") or "").strip().lower()
    if item_email and lead.email and lead.email.strip().lower() == item_email:
        score += 3
        reasons.append("email sama")

    # --- Fuzzy nama + kota ---
    sim = difflib.SequenceMatcher(None, ln, iname).ratio()
    lc, ic = _city_name(lead), str(item.get("kota") or "").strip().lower()
    if lc and ic and lc == ic:
        if ln == iname:
            score += 4
            reasons.append("nama+kota sama")
        elif sim >= MATCH_THRESHOLD:
            score += 3
            reasons.append(f"nama mirip ({sim:.2f}) + kota sama")
    elif sim >= MATCH_THRESHOLD_NO_CITY:
        score += 2
        reasons.append(f"nama hampir sama ({sim:.2f})")

    return score, "; ".join(reasons)


def match_and_merge(
    db: Session,
    source: str,
    raw_items: list[dict],
    progress_cb=None,
    cancel_check=None,
    target_sources: set[str] | None = None,
    category: str = "",
    city: str = "",
    limit: int | None = None,
) -> dict:
    """Cocokkan hasil scraper pendukung ke lead seed, isi field kosong saja.

    Core logic enrichment (PRD v1.1 §5.3 + requirement menu Enrichment):
    1. Target = lead seed di DB (Results) yang cocok dengan `category` & `city`
       input user dan field pendukung-nya masih kosong (lihat find_incomplete_leads).
    2. Hasil `raw_items` dari sumber enrichment dicocokkan ke target tsb via
       nama instansi / NPSN / domain / email (fuzzy).
    3. HANYA mengisi kolom yang masih kosong (NULL/blank/"-") — tidak replace.
    Enrichment TIDAK membuat lead baru.

    `progress` yang dilaporkan = jumlah lead yang berhasil diisi (bukan jumlah
    raw item), sehingga progress bar "sesuai Maks. hasil yang diinput" di frontend.

    Returns: {"candidates", "matched", "filled", "unmatched"}.
    `unmatched` = nama hasil enrichment yang tidak cocok ke lead mana pun
    (dilog untuk review manual — TIDAK disimpan sebagai lead baru).
    """
    fields = fields_for(source)
    if not fields:
        raise ValueError(f"Sumber '{source}' bukan sumber enrichment")

    candidates = find_incomplete_leads(
        db, source,
        target_sources=target_sources, category=category, city=city, limit=limit,
    )
    matched = filled = 0
    unmatched: list[str] = []

    for item in raw_items:
        if cancel_check and cancel_check():
            break
        name = str(item.get("nama_instansi") or "").strip()
        if not name:
            continue

        best, best_score, best_reason = None, 0, ""
        for lead in candidates:
            if cancel_check and cancel_check():
                break
            s, reason = _match_score(lead, item)
            if s > best_score:
                best, best_score, best_reason = lead, s, reason

        if best is None or best_score < 1:
            unmatched.append(name)
            if progress_cb:
                progress_cb(matched, matched, f"Tidak match (review manual): {name}")
            continue

        changed: list[str] = []
        for f in fields:
            val = str(item.get(f) or "").strip()
            if val and _is_empty(getattr(best, f)):
                setattr(best, f, val)
                changed.append(f)
        if changed:
            best.updated_at = datetime.utcnow()
            db.add(best)
            matched += 1
            filled += len(changed)
            if progress_cb:
                progress_cb(matched, matched,
                            f"Match: {name} → {best.nama_instansi} ({best_reason}) | isi: {', '.join(changed)}")
        elif progress_cb:
            progress_cb(matched, matched,
                        f"Match: {name} → {best.nama_instansi} (field sudah lengkap, dilewati)")

    db.commit()
    return {
        "candidates": len(candidates),
        "matched": matched,
        "filled": filled,
        "unmatched": unmatched,
    }
