"""Importer: impor data dari file CSV (kontingensi untuk sumber yang diblokir)."""
import csv
from io import StringIO
from sqlalchemy.orm import Session
from backend.services.storage_service import save_raw_items


EXPECTED_COLUMNS = {
    "nama_instansi", "kategori", "telp", "email", "alamat", "kota",
    "website", "sosmed", "source", "status", "npsn", "nama_kepsek",
    "posisi_rekrutmen", "deskripsi_it", "penanggung_jawab",
}


def _detect_delimiter(text_content: str) -> str:
    """Export memakai ';' (Excel Indonesia); importer harus menerima keduanya."""
    lines = text_content.splitlines()
    if lines:
        first = lines[0]
        if first.count(";") > first.count(","):
            return ";"
    return ","


def import_csv_text(db: Session, text_content: str, source: str = "") -> dict:
    """Parse CSV → list dict → simpan via storage (auto dedup/clean)."""
    reader = csv.DictReader(StringIO(text_content), delimiter=_detect_delimiter(text_content))
    items = []
    for row in reader:
        item = {}
        for k, v in row.items():
            if k is None:
                continue
            key = k.strip().lower().replace(" ", "_").replace("/", "_")
            # peta label Indonesia → field
            mapping = {
                "nama": "nama_instansi",
                "nama_instansi": "nama_instansi",
                "bidang_usaha_kategori": "kategori",
                "bidang_usaha": "kategori",
                "kategori": "kategori",
                "no_wa_telephon": "telp",
                "no_wa_telepon": "telp",
                "telp": "telp",
                "telepon": "telp",
                "alamat_email": "email",
                "email": "email",
                "alamat_lengkap": "alamat",
                "alamat": "alamat",
                "kota": "kota",
                "link_gmaps": "link_gmaps",
                "link_website": "website",
                "website": "website",
                "akun_media_sosial": "sosmed",
                "sosmed": "sosmed",
                "sumber": "source",
                "source": "source",
                "status": "status",
                "npsn": "npsn",
                "nama_kepsek": "nama_kepsek",
                "posisi_rekrutmen": "posisi_rekrutmen",
                "deskripsi_it": "deskripsi_it",
                "penanggung_jawab": "penanggung_jawab",
            }
            field = mapping.get(key)
            if field and v and str(v).strip():
                item[field] = str(v).strip()
        if item.get("nama_instansi"):
            item.setdefault("source", source or "gmaps")
            items.append(item)
    return save_raw_items(db, items, source=source or "gmaps")