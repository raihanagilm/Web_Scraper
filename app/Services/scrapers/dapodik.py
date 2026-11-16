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

from app.Services.scrapers.base import BaseScraper
from app.Services.browser_profile import build_browser_args
from app.config import settings

# ---- Konfigurasi endpoint Kemendikdasmen (PRD v1.1 §5.2) ----
REFERENSI_SEARCH_URL = "https://referensi.data.kemendikdasmen.go.id/satpen/cari?q={keyword}"
REFERENSI_DETAIL_URL = "https://referensi.data.kemendikdasmen.go.id/satpen/detail/{npsn}"

NPSN_RE = re.compile(r"\b(\d{8})\b")
CARI_ROW_RE = re.compile(
    r'/pendidikan/npsn/(\d{8})[^>]*>.*?,\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"',
    re.DOTALL
)

NAME_THRESHOLD = 0.50
CITY_BONUS = 0.25


def _extract_search_matches(html: str) -> list[tuple[str, str, str, str]]:
    """Ekstrak (npsn, nama, kec, kab_kota) dari HTML tabel pencarian Kemendikdasmen."""
    matches = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 3:
                npsn = tds[1].get_text(strip=True)
                nama = tds[2].get_text(strip=True)
                wil = tds[5].get_text(strip=True) if len(tds) > 5 else ""
                if npsn.isdigit() and len(npsn) == 8:
                    matches.append((npsn, nama, wil, wil))
    except Exception:
        pass
    if not matches:
        matches = CARI_ROW_RE.findall(html)
    return matches


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
        user_id: int | None = None,
    ):
        super().__init__(source=self.source, category=category, city=city, max_results=max_results, user_id=user_id)
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

        self.emit_progress(0, len(self.targets), f"Dapodik: Melengkapi {len(self.targets)} sekolah secara paralel (5 worker)...")
        return self._run_http_fallback(leads)

    def _find_best_npsn(self, clean_name: str, matches: list) -> str:
        best_npsn, best_score = "", 0.0
        norm_target = self._norm(clean_name)
        city_l = self.city.strip().lower()
        for npsn, found_name, kec, kab_kota in matches:
            norm_found = self._norm(found_name)
            score = difflib.SequenceMatcher(None, norm_target, norm_found).ratio()
            if city_l and city_l in (kab_kota + " " + kec + " " + found_name).lower():
                score += CITY_BONUS
            if score > best_score:
                best_score = score
                best_npsn = npsn
        return best_npsn if best_score >= NAME_THRESHOLD else ""

    @staticmethod
    def _parse_detail_html(detail_html: str, best_npsn: str = "", detail_url: str = "") -> dict:
        res = {"npsn": best_npsn, "link_source": detail_url, "nama_kepsek": "", "email": ""}
        try:
            soup = BeautifulSoup(detail_html, "html.parser")
            for row in soup.find_all("div", class_="detail-row"):
                lbl_el = row.find("div", class_="detail-label")
                val_el = row.find("div", class_="detail-value")
                if not lbl_el or not val_el:
                    continue
                lbl = lbl_el.get_text(strip=True).lower()
                val = val_el.get_text(strip=True)
                if "email" in lbl and not res["email"]:
                    res["email"] = val.replace(" ", "")
                elif "kepala sekolah" in lbl and not res["nama_kepsek"] and val != "-":
                    res["nama_kepsek"] = val

            # Format tabel tr > td klasik (fallback)
            for tr in soup.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    lbl = tds[0].get_text(strip=True).lower()
                    val = tds[-1].get_text(strip=True)
                    if "email" in lbl and not res["email"]:
                        res["email"] = val.replace(" ", "")
                    elif "kepala sekolah" in lbl and not res["nama_kepsek"] and val != "-":
                        res["nama_kepsek"] = val
        except Exception:
            pass

        # Fallback regex
        if not res["email"]:
            m_email = re.search(r'Email(?:</td>\s*<td>:</td>\s*<td>|\s*:\s*|\s+)([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', detail_html, re.IGNORECASE)
            if m_email:
                res["email"] = m_email.group(1).strip()
            else:
                m_raw = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', detail_html)
                if m_raw:
                    res["email"] = m_raw.group(0)

        if not res["nama_kepsek"]:
            m_kepsek = re.search(
                r'(?:Kepala\s*Sekolah|Kepsek)\s*(?:</td>\s*<td>:</td>\s*<td>|:|\s+)\s*([^<\n\r]+)',
                detail_html, re.IGNORECASE
            )
            if m_kepsek:
                raw_name = m_kepsek.group(1).strip()
                if raw_name and raw_name != "-" and not any(kw in raw_name.lower() for kw in ["operator", "akreditasi"]):
                    res["nama_kepsek"] = raw_name

        return res

    # ---- HTTP Parallel Methods ----

    def _run_http_fallback(self, existing_leads: list[dict]) -> list[dict]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        leads = list(existing_leads)
        processed_names = {l.get("nama_instansi") for l in leads}
        remaining_targets = [t for t in self.targets if t not in processed_names]
        total = len(self.targets)
        completed_count = len(leads)

        def _worker(name: str):
            if self.is_cancelled():
                return None
            try:
                item = self._lookup_school_http(name)
                if item and item.get("npsn"):
                    item["nama_instansi"] = name
                    item["kategori"] = self.category
                    item["kota"] = self.city
                    item["status"] = "New"
                    return item
            except Exception:
                pass
            return None

        # Gunakan 5 worker thread untuk concurrency aman tanpa 429
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_name = {executor.submit(_worker, name): name for name in remaining_targets}
            for future in as_completed(future_to_name):
                if self.is_cancelled():
                    break
                name = future_to_name[future]
                completed_count += 1
                try:
                    item = future.result()
                    if item:
                        leads.append(item)
                        extra = []
                        if item.get("nama_kepsek"): extra.append(f"Kepsek: {item['nama_kepsek']}")
                        if item.get("email"): extra.append(f"Email: {item['email']}")
                        sfx = f" ({', '.join(extra)})" if extra else ""
                        self.emit_progress(completed_count, total, f"Dapodik [{completed_count}/{total}]: {name} → NPSN {item.get('npsn')}{sfx}")
                    else:
                        self.emit_progress(completed_count, total, f"Dapodik [{completed_count}/{total}]: {name} (selesai)")
                except Exception:
                    pass

        return leads

    def _lookup_school_http(self, name: str) -> dict | None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(verify=False, timeout=15.0, headers=headers, follow_redirects=True) as client:
            clean_name = re.sub(r'["\']', '', name).strip()
            url = REFERENSI_SEARCH_URL.format(keyword=urllib.parse.quote(clean_name))
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            matches = _extract_search_matches(resp.text)
            if not matches:
                return None

            best_npsn = self._find_best_npsn(clean_name, matches)
            if not best_npsn:
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
