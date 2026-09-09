"""Dapodik / Kemendikbud scraper — enrichment Sekolah (NPSN & Nama Kepala Sekolah).

PRD v1.1 §5.2: sumber data ekosistem Kemendikbud (referensi.data.kemendikdasmen.go.id).
Peran = ENRICHMENT: hasil tidak dibuat sebagai lead baru, hanya dicocokkan
ke lead Sekolah hasil seed GMaps yang NPSN/kepsek-nya masih kosong.

Cara kerja:
- Menggunakan browser Playwright (headful, terbuka di layar) agar pengguna dapat melihat
  langsung proses pencarian data sekolah dan detail profil NPSN.
- Untuk tiap target: cari di referensi.data.kemendikdasmen.go.id → ambil NPSN baris paling mirip →
  buka halaman detail → ambil nama Kepala Sekolah & Email.
"""
import difflib
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import uuid
import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from backend.services.scrapers.base import BaseScraper

# ---- Konfigurasi endpoint Kemendikdasmen (PRD v1.1 §5.2) ----
REFERENSI_SEARCH_URL = "https://referensi.data.kemendikdasmen.go.id/pendidikan/cari/{keyword}"
REFERENSI_DETAIL_URL = "https://referensi.data.kemendikdasmen.go.id/pendidikan/npsn/{npsn}"

NPSN_RE = re.compile(r"\b(\d{8})\b")
# Regex untuk mengekstrak baris data Javascript DataTables dari halaman pencarian
CARI_ROW_RE = re.compile(
    r'/pendidikan/npsn/(\d{8})[^>]*>.*?,\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"',
    re.DOTALL
)

NAME_THRESHOLD = 0.50
CITY_BONUS = 0.25


class DapodikScraper(BaseScraper):
    """Enrichment Sekolah via Dapodik Kemendikdasmen: isi `npsn` & `nama_kepsek`.

    `targets` = daftar nama sekolah yang akan dicari (dikirim JobManager).
    Output raw item: {nama_instansi, npsn, nama_kepsek, email, kategori, kota} →
    dicocokkan `enrichment_service.match_and_merge` (isi field kosong saja).
    """

    source = "dapodik"

    def __init__(
        self,
        category: str = "sekolah",
        city: str = "salatiga",
        max_results: int = 100,
        targets: list[str] | None = None,
        job_id: str | None = None,
    ):
        super().__init__(source=self.source, category=category, city=city, max_results=max_results)
        self.targets = [t.strip() for t in (targets or []) if t and t.strip()][:max_results]
        self.job_id = job_id
        self._page = None

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

        self.emit_progress(0, len(self.targets), f"Membuka browser Dapodik untuk {len(self.targets)} sekolah…")

        clean_id = re.sub(r'[^a-zA-Z0-9]+', '_', self.job_id or uuid.uuid4().hex[:8])
        worker_dir = os.path.join(tempfile.gettempdir(), "playwright_dapodik_workers", f"worker_{clean_id}")
        os.makedirs(worker_dir, exist_ok=True)

        browser_success = False
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=worker_dir,
                    headless=False,
                    channel="chrome",
                    ignore_https_errors=True,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                )
                page = context.pages[0] if context.pages else context.new_page()
                self._page = page
                browser_success = True

                for idx, name in enumerate(self.targets):
                    if self.is_cancelled():
                        break

                    self.emit_progress(idx, len(self.targets), f"Mencari Dapodik ({idx + 1}/{len(self.targets)}): {name}")
                    item = None
                    try:
                        item = self._lookup_school_browser(page, name)
                    except Exception as e:
                        self.emit_progress(len(leads), len(self.targets), f"Info pencarian '{name}': {e}")
                        # Fallback HTTP jika ada kendala di browser
                        try:
                            item = self._lookup_school_http(name)
                        except Exception:
                            item = None

                    if item and item.get("npsn"):
                        item["nama_instansi"] = name
                        item["kategori"] = self.category
                        item["kota"] = self.city
                        item["status"] = "New"
                        leads.append(item)
                        extra_info = []
                        if item.get("nama_kepsek"):
                            extra_info.append(f"Kepsek: {item['nama_kepsek']}")
                        if item.get("email"):
                            extra_info.append(f"Email: {item['email']}")
                        suffix = f" | {', '.join(extra_info)}" if extra_info else ""
                        self.emit_progress(
                            len(leads), len(self.targets),
                            f"Dapodik ({len(leads)}/{len(self.targets)}): {name} → NPSN {item.get('npsn')}{suffix}",
                        )
                    else:
                        self.emit_progress(len(leads), len(self.targets), f"Tidak ditemukan di Dapodik: {name}")

                    self.rate_limit()

                self._page = None
                try:
                    context.close()
                except Exception:
                    pass

        except Exception as e:
            # Jika Playwright gagal dijalankan (misal environment headless), fallback ke HTTP
            if not browser_success:
                self.emit_progress(0, len(self.targets), f"Mode browser info ({e}), menggunakan koneksi direct Dapodik…")
                return self._run_http_fallback(leads)

        finally:
            shutil.rmtree(worker_dir, ignore_errors=True)

        return leads

    # ---- Browser Lookup Methods ----

    def _lookup_school_browser(self, page, name: str) -> dict | None:
        """Cari 1 sekolah di referensi Kemendikdasmen via Playwright."""
        clean_name = re.sub(r'["\']', '', name).strip()
        q = urllib.parse.quote(clean_name)
        url = REFERENSI_SEARCH_URL.format(keyword=q)

        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(1.5)

        html = page.content()
        matches = CARI_ROW_RE.findall(html)
        if not matches:
            tokens = [t for t in clean_name.split() if len(t) > 2]
            if len(tokens) > 2:
                short_q = urllib.parse.quote(" ".join(tokens[:3]))
                page.goto(REFERENSI_SEARCH_URL.format(keyword=short_q), timeout=30000, wait_until="domcontentloaded")
                time.sleep(1.5)
                html = page.content()
                matches = CARI_ROW_RE.findall(html)

        if not matches:
            return None

        best_npsn, best_score = "", 0.0
        norm_target = self._norm(clean_name)
        city_l = self.city.strip().lower()

        for npsn, found_name, kec, kab_kota in matches:
            norm_found = self._norm(found_name)
            score = difflib.SequenceMatcher(None, norm_target, norm_found).ratio()
            kab_kec_str = (kab_kota + " " + kec + " " + found_name).lower()
            if city_l and city_l in kab_kec_str:
                score += CITY_BONUS
            if score > best_score:
                best_score = score
                best_npsn = npsn

        if best_score < NAME_THRESHOLD or not best_npsn:
            return None

        # Buka halaman detail di browser agar terlihat oleh pengguna
        detail_url = REFERENSI_DETAIL_URL.format(npsn=best_npsn)
        page.goto(detail_url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(1)

        detail_html = page.content()
        return self._parse_detail_html(detail_html, best_npsn, detail_url)

    @staticmethod
    def _parse_detail_html(detail_html: str, best_npsn: str = "", detail_url: str = "") -> dict:
        res = {"npsn": best_npsn, "link_source": detail_url, "nama_kepsek": "", "email": ""}

        m_email = re.search(r'Email</td>\s*<td>:</td>\s*<td>\s*([^<\s]+@[^<\s]+)', detail_html, re.IGNORECASE)
        if m_email:
            res["email"] = m_email.group(1).strip()

        m_kepsek = re.search(
            r'(?:Kepala\s*Sekolah|Kepsek)\s*</td>\s*<td>:</td>\s*<td>\s*([^<]+)',
            detail_html, re.IGNORECASE
        )
        if m_kepsek:
            raw_name = m_kepsek.group(1).strip()
            if raw_name and raw_name != "-":
                res["nama_kepsek"] = raw_name

        return res

    # ---- HTTP Fallback Methods ----

    def _run_http_fallback(self, existing_leads: list[dict]) -> list[dict]:
        leads = list(existing_leads)
        processed_names = {l.get("nama_instansi") for l in leads}
        remaining_targets = [t for t in self.targets if t not in processed_names]

        for name in remaining_targets:
            if self.is_cancelled():
                break
            try:
                item = self._lookup_school_http(name)
                if item and item.get("npsn"):
                    item["nama_instansi"] = name
                    item["kategori"] = self.category
                    item["kota"] = self.city
                    item["status"] = "New"
                    leads.append(item)
                    self.emit_progress(len(leads), len(self.targets), f"Dapodik: {name} → NPSN {item.get('npsn')}")
            except Exception:
                pass
            self.rate_limit()

        return leads

    def _lookup_school_http(self, name: str) -> dict | None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(verify=False, timeout=15.0, headers=headers, follow_redirects=True) as client:
            clean_name = re.sub(r'["\']', '', name).strip()
            q = urllib.parse.quote(clean_name)
            url = REFERENSI_SEARCH_URL.format(keyword=q)
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            matches = CARI_ROW_RE.findall(resp.text)
            if not matches:
                return None

            best_npsn, best_score = "", 0.0
            norm_target = self._norm(clean_name)
            city_l = self.city.strip().lower()
            for npsn, found_name, kec, kab_kota in matches:
                norm_found = self._norm(found_name)
                score = difflib.SequenceMatcher(None, norm_target, norm_found).ratio()
                if city_l and city_l in (kab_kota + " " + kec).lower():
                    score += CITY_BONUS
                if score > best_score:
                    best_score = score
                    best_npsn = npsn

            if best_score < NAME_THRESHOLD or not best_npsn:
                return None

            detail_url = REFERENSI_DETAIL_URL.format(npsn=best_npsn)
            d_resp = client.get(detail_url)
            if d_resp.status_code == 200:
                return self._parse_detail_html(d_resp.text, best_npsn, detail_url)
            return {"npsn": best_npsn, "link_source": detail_url, "nama_kepsek": "", "email": ""}

    @staticmethod
    def _norm(s: str) -> str:
        s = re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())
        return re.sub(r"\s+", " ", s).strip()
