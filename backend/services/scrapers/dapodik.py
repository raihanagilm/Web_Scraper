"""Dapodik / Kemendikbud scraper — enrichment Sekolah (NPSN & Nama Kepala Sekolah).

PRD v1.1 §5.2: sumber data ekosistem Kemendikbud (dapo.kemdikbud.go.id,
referensi.data.kemdikbud.go.id) — BUKAN portal berita kemendikdasmen.go.id.
Peran = ENRICHMENT: hasil tidak dibuat sebagai lead baru, hanya dicocokkan
ke lead Sekolah hasil seed GMaps yang NPSN/kepsek-nya masih kosong.

Cara kerja (berbeda dari scraper keyword lain):
- Situs Dapodik/referensi hanya menyediakan pencarian **per nama sekolah**,
  jadi scraper ini menerima daftar nama target (dari JobManager: lead seed
  gmaps yang NPSN/kepsek-nya masih kosong, difilter kategori+kota).
- Untuk tiap target: cari di referensi.data.kemdikbud.go.id (DataTables) →
  ambil NPSN baris paling mirip → buka halaman detail → ambil nama Kepsek.

Semua selector terpusat di konstanta di bawah agar mudah disesuaikan bila
struktur situs berubah.
"""
import difflib
import re

from playwright.sync_api import sync_playwright

from backend.services.scrapers.base import BaseScraper

# ---- Konfigurasi selector / endpoint (ubah di sini bila situs berubah) ----
DAPO_SEARCH_URL = "https://dapo.kemdikbud.go.id/sekolah"
DAPO_SEARCH_INPUT = 'input[type="search"], input[name="keyword"], input#keyword'
DAPO_RESULT_LINK = 'table td a, .table td a'
# API JSON internal referensi (dicoba dulu; jika gagal → fallback halaman web)
REFERENSI_SEARCH_URL = "https://referensi.data.kemdikbud.go.id/pendidikan/dikdas/"
REFERENSI_DETAIL_URL = "https://referensi.data.kemdikbud.go.id/pendidikan/dikdas/{npsn}"
REFERENSI_SEARCH_INPUTS = ['input[type="search"]', "#table_search", "input[name='table_search']"]
REFERENSI_TABLE_ROWS = "table tbody tr"

# Detail sekolah: kolom tabel "Kepala Sekolah" → nilai di sel berikutnya
KEPSEK_XPATH = (
    "//td[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
    "'abcdefghijklmnopqrstuvwxyz'), 'kepala sekolah')]/following-sibling::td[1]"
)

NPSN_RE = re.compile(r"\b(\d{8})\b")
# Jumlah baris hasil pencarian yang diperiksa per target
MAX_ROWS = 6
# Ambang kemiripan nama sekolah hasil pencarian vs nama target
NAME_THRESHOLD = 0.55
# Bonus skor bila baris memuat nama kota target
CITY_BONUS = 0.15


class DapodikScraper(BaseScraper):
    """Enrichment Sekolah via Dapodik: isi `npsn` & `nama_kepsek` lead seed.

    `targets` = daftar nama sekolah yang akan dicari (dikirim JobManager).
    Output raw item: {nama_instansi, npsn, nama_kepsek, kategori, kota} →
    dicocokkan `enrichment_service.match_and_merge` (isi field kosong saja).
    """

    source = "dapodik"

    def __init__(self, category: str = "sekolah", city: str = "salatiga",
                 max_results: int = 100, targets: list[str] | None = None):
        super().__init__(source=self.source, category=category, city=city, max_results=max_results)
        self.targets = [t.strip() for t in (targets or []) if t and t.strip()][:max_results]
        self._page = None  # untuk is_alive() (deteksi browser ditutup)

    def is_alive(self) -> bool:
        try:
            return self._page is None or not self._page.is_closed()
        except Exception:
            return True

    def run(self) -> list[dict]:
        leads: list[dict] = []
        if not self.targets:
            self.emit_progress(0, 0, "Tidak ada lead Sekolah dengan NPSN/kepsek kosong — enrichment dilewati.")
            return leads

        self.emit_progress(0, len(self.targets), f"Mencari {len(self.targets)} sekolah di Dapodik Kemdikbud…")
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self._profile_dir(),
                headless=True,  # situs pemerintah — umumnya tanpa proteksi bot
                channel="chrome",
                ignore_https_errors=True,
            )
            page = context.new_page()
            self._page = page
            try:
                for name in self.targets:
                    if self.is_cancelled():
                        break
                    item = None
                    try:
                        item = self._lookup_school(page, name)
                    except Exception as e:
                        self.emit_progress(len(leads), len(self.targets), f"Error cari '{name}': {e}")
                    if item:
                        item["nama_instansi"] = name
                        item["kategori"] = self.category
                        item["kota"] = self.city
                        item["status"] = "New"
                        leads.append(item)
                        self.emit_progress(
                            len(leads), len(self.targets),
                            f"Dapodik: {name} → NPSN {item.get('npsn', '-')}"
                            + (f" | Kepsek: {item['nama_kepsek']}" if item.get("nama_kepsek") else ""),
                        )
                    else:
                        self.emit_progress(len(leads), len(self.targets), f"Tidak ditemukan di Dapodik: {name}")
                    self.rate_limit()  # delay 1–3 detik antar pencarian (SOP)
            except Exception as e:
                self.emit_progress(len(leads), len(self.targets), f"Error browser: {e}")
            finally:
                self._page = None
                try:
                    context.close()
                except Exception:
                    pass
        return leads

    # ---- Pencarian per sekolah ----

    def _lookup_school(self, page, name: str) -> dict | None:
        """Cari 1 sekolah → {"npsn": ..., "nama_kepsek": ...} atau None."""
        npsn = self._find_npsn(page, name)
        if not npsn:
            return None
        kepsek = self._find_kepsek(page, npsn)
        return {"npsn": npsn, "nama_kepsek": kepsek or ""}

    def _find_npsn(self, page, name: str) -> str:
        """Ketik nama sekolah di pencarian referensi dikdas → NPSN baris paling mirip."""
        page.goto(REFERENSI_SEARCH_URL, timeout=45000, wait_until="domcontentloaded")
        search = self._first_visible(page, REFERENSI_SEARCH_INPUTS)
        if search is None:
            return ""
        search.fill(name)
        page.wait_for_timeout(3000)  # DataTables server-side reload
        rows = page.locator(REFERENSI_TABLE_ROWS)
        n = min(rows.count(), MAX_ROWS)
        best_npsn, best_score = "", 0.0
        norm = self._norm(name)
        city_l = self.city.strip().lower()
        for i in range(n):
            if self.is_cancelled():
                break
            try:
                text = " ".join(rows.nth(i).inner_text().split())
                m = NPSN_RE.search(text)
                if not m:
                    continue
                ratio = difflib.SequenceMatcher(None, norm, self._norm(text)).ratio()
                if city_l and city_l in text.lower():
                    ratio += CITY_BONUS  # baris memuat kota target → lebih dipercaya
                if ratio > best_score:
                    best_score, best_npsn = ratio, m.group(1)
            except Exception:
                continue
        return best_npsn if best_score >= NAME_THRESHOLD else ""

    def _find_kepsek(self, page, npsn: str) -> str:
        """Buka halaman detail sekolah → ambil nama Kepala Sekolah."""
        try:
            page.goto(REFERENSI_DETAIL_URL.format(npsn=npsn), timeout=45000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            cell = page.locator(f"xpath={KEPSEK_XPATH}")
            if cell.count() > 0:
                return cell.first.inner_text().strip()
            m = re.search(
                r"Kepala\s*Sekolah\s*:?\s*([A-Za-z .,'()\-]{3,80})",
                page.content(), re.IGNORECASE,
            )
            return m.group(1).strip() if m else ""
        except Exception:
            return ""

    # ---- Helper ----

    @staticmethod
    def _first_visible(page, selectors: list[str]):
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue
        return None

    @staticmethod
    def _norm(s: str) -> str:
        s = re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())
        return re.sub(r"\s+", " ", s).strip()

    def _profile_dir(self) -> str:
        import os
        return os.path.expanduser("~/playwright_chrome_profile_dapodik")
