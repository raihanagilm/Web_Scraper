"""Exporter: mengekspor leads ke Excel profesional (openpyxl)."""
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from backend.config import settings

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"

# Base columns (label Excel) sesuai tabel Results (20 kolom)
BASE_COLUMNS = [
    ("no", "No"),
    ("kode", "Kode ID"),
    ("nama_instansi", "Nama Instansi"),
    ("kategori", "Bidang Usaha / Kategori"),
    ("telp", "No. WA / Telephon"),
    ("email", "Alamat Email"),
    ("alamat", "Alamat Lengkap"),
    ("kota", "Kota"),
    ("link_gmaps", "Link Gmaps"),
    ("website", "Link Website"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("linkedin", "LinkedIn"),
    ("twitter_x", "Twitter / X"),
    ("tiktok", "TikTok"),
    ("sosmed", "Media Sosial Lainnya"),
    ("npsn", "NPSN"),
    ("nama_kepsek", "Nama Kepsek"),
    ("link_source", "Link Kemendikdasmen"),
    ("source", "Sumber"),
    ("status", "Status"),
]

# Kolom tambahan sesuai sumber (muncul bila ada isi)
EXTRA_COLUMNS = {
    "dapodik": [("npsn", "NPSN"), ("nama_kepsek", "Nama Kepsek")],
    "jobstreet": [],
    "glints": [],
    "lpse": [],
    "gmaps": [],
}

STATUS_OPTIONS = "New, Contacted, Follow Up, Deal, Rejected"

HEADER_FILL = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
ZEBRA_FILL = PatternFill(start_color="F8F9F9", end_color="F8F9F9", fill_type="solid")
WHITE_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin", color="D5D8DC"),
    right=Side(style="thin", color="D5D8DC"),
    top=Side(style="thin", color="D5D8DC"),
    bottom=Side(style="thin", color="D5D8DC"),
)


def _build_columns(items: list[dict]) -> list[tuple[str, str]]:
    """Base columns + extra columns dari sumber yang muncul di items."""
    cols = list(BASE_COLUMNS)
    sources = {it.get("source") for it in items}
    seen = {key for key, _ in cols}
    for src in ["dapodik", "jobstreet", "glints", "lpse"]:
        if src in sources:
            for key, label in EXTRA_COLUMNS.get(src, []):
                if key not in seen:
                    cols.append((key, label))
                    seen.add(key)
    return cols


def export_leads_csv(items: list[dict]) -> str:
    """Buat isi file CSV dari items. Delimiter ';' agar Excel Indonesia
    langsung memisah kolom, plus BOM utf-8 agar karakter tampil benar."""
    import csv
    import io

    columns = _build_columns(items)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    w.writerow([label for _, label in columns])
    for i, it in enumerate(items, start=1):
        row = []
        for key, _label in columns:
            if key == "no":
                row.append(i)
                continue
            val = it.get(key) or ""
            # cegah formula injection saat dibuka di Excel
            if isinstance(val, str) and val[:1] in ("=", "+", "-", "@"):
                val = "'" + val
            row.append(val)
        w.writerow(row)
    return "\ufeff" + buf.getvalue()


def export_leads(items: list[dict], city: str = "", category: str = "") -> str:
    """Tulis items → file .xlsx, return path file."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    columns = _build_columns(items)
    ts = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
    safe_name = (city or category or "leads").replace("/", "_").replace("\\", "_")
    filename = f"Leads_{safe_name}_{ts}.xlsx"
    filepath = EXPORT_DIR / filename

    wb = Workbook()
    ws = wb.active
    ws.title = "Database Leads"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Header
    for ci, (_, label) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=ci, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
    ws.row_dimensions[1].height = 28

    # Data
    for ri, it in enumerate(items, start=2):
        ws.row_dimensions[ri].height = 20
        fill = ZEBRA_FILL if (ri % 2 == 0) else WHITE_FILL
        for ci, (key, _label) in enumerate(columns, start=1):
            if key == "no":
                val = ri - 1
            else:
                val = it.get(key) or ""
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.fill = fill
            cell.border = THIN_BORDER
            cell.font = Font(name="Calibri", size=10)
            if key in ("no", "npsn", "kota", "status"):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Dropdown status
    status_col_idx = None
    for ci, (key, _) in enumerate(columns, start=1):
        if key == "status":
            status_col_idx = ci
            break
    if status_col_idx:
        letter = get_column_letter(status_col_idx)
        dv = DataValidation(type="list", formula1=f'"{STATUS_OPTIONS}"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{letter}2:{letter}{len(items) + 1}")

    # Lebar kolom
    for ci, (key, _) in enumerate(columns, start=1):
        max_len = len(str(columns[ci - 1][1]))
        for it in items[:200]:
            val = it.get(key, "") if key != "no" else "No"
            val_len = len(str(val)) if val else 0
            max_len = max(max_len, min(val_len, 40))
        ws.column_dimensions[get_column_letter(ci)].width = max_len + 4

    wb.save(filepath)
    return str(filepath)