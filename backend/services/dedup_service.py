import re
from sqlalchemy.orm import Session

from backend.models import Lead, MergeHistory
from backend.services.cleaner import normalize_emails, normalize_name, normalize_phone, normalize_website

FIELDS_TO_COMPARE = [
    "kode", "nama_instansi", "kategori", "telp", "email", "alamat", "kota",
    "link_gmaps", "website", "sosmed", "instagram", "facebook", "linkedin", "twitter_x", "tiktok",
    "link_source", "status", "npsn", "nama_kepsek",
]


def _lead_fingerprints(lead: Lead) -> list[tuple[str, str]]:
    """Kumpulkan list of (key, val) fingerprint dari 1 lead (mendukung multi-email)."""
    fps: list[tuple[str, str]] = []
    norm_name = normalize_name(lead.nama_instansi)
    city = (lead.kota or "").strip().lower()
    if norm_name and len(norm_name) >= 5:
        fps.append(("name_city", f"{norm_name}|{city}"))
    if lead.npsn:
        fps.append(("npsn", lead.npsn.strip()))
    if lead.telp:
        fps.append(("phone", normalize_phone(lead.telp)))
    if lead.website:
        fps.append(("domain", normalize_website(lead.website)))

    # Multi-email fingerprints
    if lead.email:
        for em in re.split(r"[\s,;]+", lead.email):
            em_clean = em.strip().lower()
            if em_clean and "@" in em_clean:
                fps.append(("email", em_clean))

    # Social media fingerprints
    if lead.instagram:
        m_ig = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", lead.instagram.lower())
        if m_ig and m_ig.group(1) not in {"p", "reel", "explore"}:
            fps.append(("instagram", m_ig.group(1)))

    if lead.facebook:
        m_fb = re.search(r"(?:facebook\.com|fb\.com)/([A-Za-z0-9_.\-]+)", lead.facebook.lower())
        if m_fb and m_fb.group(1) not in {"sharer", "share", "policies"}:
            fps.append(("facebook", m_fb.group(1)))

    if lead.linkedin:
        m_li = re.search(r"linkedin\.com/(?:company|school)/([A-Za-z0-9_.\-]+)", lead.linkedin.lower())
        if m_li:
            fps.append(("linkedin", m_li.group(1)))

    return fps


def _score_pair(lead_a: Lead, lead_b: Lead) -> tuple[int, list[str]]:
    """Skor kemiripan 2 lead (jumlah key fingerprint yang cocok)."""
    fa = set(_lead_fingerprints(lead_a))
    fb = set(_lead_fingerprints(lead_b))
    score = 0
    reasons = []
    matched = fa.intersection(fb)
    label_map = {
        "name_city": "nama+kota sama",
        "npsn": "NPSN sama",
        "phone": "telepon sama",
        "email": "email sama",
        "domain": "website sama",
        "instagram": "Instagram sama",
        "facebook": "Facebook sama",
        "linkedin": "LinkedIn sama",
    }
    for key, _val in matched:
        score += 1
        reasons.append(label_map.get(key, key))
    return score, sorted(set(reasons))


def _get_field_val(obj: Lead, field: str):
    """Ambil nilai field; kategori/kota dibaca lewat relasi FK."""
    if field == "kategori":
        return obj.category.name if obj.category else ""
    if field == "kota":
        return obj.city.name if obj.city else ""
    return getattr(obj, field)


def _set_field_val(obj: Lead, field: str, from_obj: Lead | None) -> None:
    """Set field; kategori/kota disalin via FK (bukan string)."""
    if field == "kategori":
        obj.category_id = from_obj.category_id if from_obj else None
    elif field == "kota":
        obj.city_id = from_obj.city_id if from_obj else None
    else:
        setattr(obj, field, getattr(from_obj, field) if from_obj else None)


def find_duplicate_groups(db: Session, min_score: int = 1) -> list[dict]:
    """Cari grup kandidat duplikat dari semua lead di DB.

    Returns list of dict: {key, score, reason, member_ids}.
    """
    leads = db.query(Lead).all()
    # map fingerprint -> list of lead ids
    index: dict[tuple, list[int]] = {}
    for lead in leads:
        for key, val in _lead_fingerprints(lead):
            index.setdefault((key, val), []).append(lead.id)

    groups: dict[str, dict] = {}
    for (fp_key, fp_val), ids in index.items():
        if len(ids) < 2:
            continue
        members = db.query(Lead).filter(Lead.id.in_(ids)).all()
        # score grup = skor pair terbaik di antara member
        best_score = 0
        best_reason = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                s, reasons = _score_pair(members[i], members[j])
                if s > best_score:
                    best_score = s
                    best_reason = reasons
        if best_score >= min_score:
            key = f"{fp_key}:{fp_val}"
            trigger_field = {
                "domain": "website",
                "phone": "telp",
                "email": "email",
                "npsn": "npsn",
                "name_city": "nama_instansi",
                "instagram": "instagram",
                "facebook": "facebook",
                "linkedin": "linkedin",
            }.get(fp_key, fp_key)
            groups[key] = {
                "key": key,
                "score": best_score,
                "reason": best_reason,
                "members": sorted(set(ids)),
                "trigger_field": trigger_field,
                "trigger_type": fp_key,
                "trigger_value": str(fp_val),
            }
    return sorted(groups.values(), key=lambda g: -g["score"])


def resolve_group(
    db: Session,
    group_key: str,
    member_ids: list[int],
    action: str,
    winner_id: int | None = None,
    field_choices: dict | None = None,
) -> dict:
    """Eksekusi aksi review: keep | merge | delete_all."""
    members = db.query(Lead).filter(Lead.id.in_(member_ids)).all()
    if not members:
        raise ValueError("No members found")

    snapshots = []
    for m in members:
        snapshots.append({f: getattr(m, f) for f in FIELDS_TO_COMPARE})

    if action == "keep":
        if winner_id is None or winner_id not in member_ids:
            raise ValueError("winner_id required for keep")
        deleted = [m for m in members if m.id != winner_id]
        snapshot_deleted = [{f: getattr(m, f) for f in FIELDS_TO_COMPARE} for m in deleted]
        for m in deleted:
            db.delete(m)
        db.commit()
    elif action == "delete_all":
        snapshot_deleted = snapshots
        for m in members:
            db.delete(m)
        db.commit()
    elif action == "merge":
        if winner_id is None or winner_id not in member_ids:
            raise ValueError("winner_id required for merge")
        winner = next(m for m in members if m.id == winner_id)
        others = [m for m in members if m.id != winner_id]
        # pilihan per field: field_choices maps field -> lead_id sumber data
        for f in FIELDS_TO_COMPARE:
            chosen_id = (field_choices or {}).get(f)
            if chosen_id:
                chosen = next((m for m in members if m.id == int(chosen_id)), None)
                if chosen and _get_field_val(chosen, f):
                    _set_field_val(winner, f, chosen)
            elif f == "email":
                # Gabungkan semua email unik dari member tanpa saling timpa
                combined_emails = [winner.email or ""] + [m.email or "" for m in others]
                winner.email = normalize_emails(", ".join(filter(None, combined_emails)))
            elif not _get_field_val(winner, f):
                # isi otomatis dari member lain yang punya data
                for m in others:
                    if _get_field_val(m, f):
                        _set_field_val(winner, f, m)
                        break
        for m in others:
            db.delete(m)
        db.add(winner)
        db.commit()
        snapshot_deleted = [{f: getattr(m, f) for f in FIELDS_TO_COMPARE} for m in others]
    else:
        raise ValueError(f"Unknown action: {action}")

    db.add(
        MergeHistory(
            group_key=group_key,
            action=action,
            winner_id=winner_id,
            member_ids=member_ids,
            field_choices=field_choices or {},
            snapshot_deleted=snapshot_deleted,
        )
    )
    db.commit()
    return {"ok": True, "action": action, "winner_id": winner_id}