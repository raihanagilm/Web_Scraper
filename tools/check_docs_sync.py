"""check_docs_sync.py — Validator sinkronisasi Trio Dokumen (prd / file / database).

Hook workflow: dipanggil oleh Cline (ON_TASK_START) & Git (pre-commit).
Tugas:
  1. Pastikan prd.md, file.md, database.md ada.
  2. Pastikan ketiganya SALING MERUJUK (cross-reference) — "saling membaca".
  3. Pastikan daftar file di file.md (blok FILE-INDEX-START..END) cocok dengan file aktual.
  4. Pastikan tabel/kolom di database.md cocok dengan model SQLAlchemy (backend/models).

Exit code: 0 = sinkron; 1 = ada drift (blokir commit / lanjutkan task dengan perbaikan).

Usage:
    venv\\Scripts\\python.exe tools\\check_docs_sync.py [--quiet]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = {
    "prd.md": "PRD (apa & mengapa)",
    "file.md": "struktur folder & jalan kode",
    "database.md": "skema database & alur data",
}

# Direktori / pola yang TIDAK dilacak (dinamis / secret / tooling / asset)
EXCLUDED_DIRS = {"venv", ".git", ".pytest_cache", "__pycache__", "node_modules",
                 "exports", "uploads", "audio", "css", "js"}
EXCLUDED_FILES = {".env"}

XREF = {  # dokumen -> wajib memuat referensi dokumen lain (saling membaca)
    "prd.md": ("file.md", "database.md"),
    "file.md": ("prd.md", "database.md"),
    "database.md": ("prd.md", "file.md"),
}


def _scan_actual_files() -> set[str]:
    """Relatif path (forward slash) semua file aktual yang dilacak."""
    out: set[str] = set()
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for f in files:
            if f.endswith(".pyc") or f in EXCLUDED_FILES or (f.startswith(".env") and f != ".env.example"):
                continue
            p = Path(root).resolve().relative_to(ROOT).as_posix()
            rel = f"{p}/{f}" if p != "." else f
            out.add(rel)
    return out

def _parse_file_index() -> set[str]:
    """Baca blok FILE-INDEX-START..END dari file.md."""
    text = (ROOT / "file.md").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"FILE-INDEX-START\s*-->(.*?)FILE-INDEX-END\s*-->", text, re.S)
    if not m:
        return set()
    return {ln.strip() for ln in m.group(1).splitlines()
            if ln.strip() and not ln.strip().startswith("#") and not ln.strip().startswith("<!--")}


def _parse_db_docs() -> dict[str, set[str]]:
    """Parse database.md → {tabel: set(kolom)}."""
    out: dict[str, set[str]] = {}
    text = (ROOT / "database.md").read_text(encoding="utf-8", errors="replace")
    cur: str | None = None
    for line in text.splitlines():
        tm = re.match(r"^##\s+\d+\.\s+Tabel:\s+(\w+)\s*$", line.strip())
        if tm:
            cur = tm.group(1)
            out.setdefault(cur, set())
            continue
        if cur is None:
            continue
        cm = re.match(r"^\|\s*\*\*(\w+)\*\*\s*\|", line)
        if cm:
            out[cur].add(cm.group(1))
    return out


def _parse_models(issues: list[str]) -> dict[str, set[str]] | None:
    """Import model SQLAlchemy & peta metadata → {tabel: set(kolom)}."""
    try:
        sys.path.insert(0, str(ROOT))
        from backend.models import Base  # noqa: F401  (memuat seluruh model)
        return {t: {c.name for c in tb.columns}
                for t, tb in sorted(Base.metadata.tables.items())}
    except Exception as e:  # pragma: no cover - environment-dependent
        issues.append(f"  [skip] model import gagal (deps?): {e}")
        return None


def check(quiet: bool) -> int:
    problems: list[str] = []

    # 1. Keberadaan dokumen
    for name, label in DOCS.items():
        if not (ROOT / name).is_file():
            problems.append(f"  [MISSING] {name} tidak ditemukan ({label})")

    # 2. Cross-reference (saling membaca)
    for name, refs in XREF.items():
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for ref in refs:
            if ref not in text:
                problems.append(f"  {name} TIDAK merujuk {ref} — wajib saling membaca.")

    # 3. file.md vs file aktual
    actual = _scan_actual_files()
    indexed = _parse_file_index()
    if indexed:
        undoc = sorted(actual - indexed)
        stale = sorted(indexed - actual)
        for f in undoc:
            problems.append(f"  [DRIFT] file baru belum di file.md §7: {f}")
        for f in stale:
            problems.append(f"  [DRIFT] file.md §7 menyebut file yang tidak ada: {f}")
    else:
        problems.append("  file.md tidak punya blok FILE-INDEX-START..END.")

    # 4. database.md vs model SQLAlchemy
    models = _parse_models(problems)
    if models:
        doc_tables = _parse_db_docs()
        for t, mod_cols in models.items():
            doc_cols = doc_tables.get(t)
            if doc_cols is None:
                problems.append(f"  [DRIFT] tabel '{t}' ada di model tapi belum di database.md")
                continue
            for c in sorted(mod_cols - doc_cols):
                problems.append(f"  [DRIFT] database.md tabel {t}: kolom '{c}' belum terdokumentasi")
            for c in sorted(doc_cols - mod_cols):
                problems.append(f"  [DRIFT] database.md tabel {t}: kolom '{c}' tidak ada di model")
        for t in set(doc_tables) - set(models):
            problems.append(f"  [DRIFT] database.md tabel '{t}' tidak ada di model SQLAlchemy")

    if not quiet:
        print("=== Pre-flight Trio Dokumen (prd.md -> file.md -> database.md) ===")
        for name, label in DOCS.items():
            ok = "OK" if (ROOT / name).is_file() else "MISSING"
            print(f"  [{ok}] {name} ({label})")
        if not problems:
            print("  Semua dokumen sinkron dengan kode. Silakan lanjut kerja.")
        else:
            print("  Drift ditemukan — perbaiki dokumen sebelum mengubah kode / commit:")
    for p in problems:
        print(p)

    return 1 if problems else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true",
                        help="output minimal (untuk hook)")
    args = parser.parse_args()
    sys.exit(check(quiet=args.quiet))

