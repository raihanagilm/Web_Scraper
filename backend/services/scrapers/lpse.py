"""LPSE Daerah scraper — lead dari instansi pemerintah yang membuka tender/pengadaan.

Sumber: portal LPSE (SPSE v4) daerah, pola host lpse.{kota}.go.id
(varian: {kota}kota / {kota}kab). Lead = instansi/pemilik anggaran;
link tender terakhir ke `link_source`.
"""
import re
import urllib.parse

from playwright.sync_api import sync_playwright

from backend.services.scrapers.base import BaseScraper

# kata kunci penanda sel "instansi" pada baris tabel SPSE
AGENCY_HINT = re.compile(
    r"(?i)(dinas|badan|sekretariat|kelurahan|kecamatan|balai|puskesmas|rumah sakit|"
    r"universitas|politeknik|polri|kepolisian|pemda|pemerintah|upt\b|satker|rs\b)"
)


class LpseScraper(BaseScraper):
    source = "lpse"

    def __init__(self, category: str = "pengadaan", city: str = "salatiga", max_results: int = 100):
        super().__init__(source=self.source, category=category, city=city, max_results=max_results)

    def _candidate_urls(self) -> list[str]:
        city = re.sub(r"\s+", "", self.city.strip().lower())
        paths = ["/eproc4/lelang", "/eproc4/aslep/lelang/current"]
        hosts = [f"lpse.{city}.go.id", f"lpse.{city}kota.go.id", f"lpse.{city}kab.go.id"]
        urls = []
        for h in hosts:
            for pth in paths:
                urls.append(f"https://{h}{pth}")
        return urls

    def run(self) -> list[dict]:
        leads: list[dict] = []
        self.emit_progress(0, 0, f"Mencari portal LPSE untuk '{self.city}'")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self._profile_dir(),
                headless=True,  # SPSE umumnya tanpa proteksi bot
                channel="chrome",
                ignore_https_errors=True,
            )
            page = context.new_page()
            try:
                rows = None
                for url in self._candidate_urls():
                    if self.is_cancelled():
                        break
                    try:
                        self.emit_progress(0, 0, f"Mencoba {url}")
                        page.goto(url, timeout=30000, wait_until="domcontentloaded")
                        page.wait_for_selector("table tr", timeout=15000)
                        rows = self._collect_rows(page, url)
                        if rows:
                            break
                    except Exception:
                        continue

                if not rows:
                    self.emit_progress(0, 0, f"Tidak menemukan portal LPSE aktif untuk '{self.city}'. Coba kota lain / cek nama host.")
                    return leads

                self.emit_progress(0, len(rows), f"Ditemukan {len(rows)} paket tender — dikelompokkan per instansi")

                by_agency: dict[str, dict] = {}
                for r in rows:
                    if self.is_cancelled() or len(by_agency) >= self.max_results:
                        break
                    agency = re.sub(r"\s+", " ", r["agency"] or "").strip(" .,")
                    if not agency:
                        continue
                    agg = by_agency.setdefault(agency, {"link": "", "paket": 0})
                    agg["paket"] += 1
                    if not agg["link"]:
                        agg["link"] = r["link"]

                leads = [
                    {
                        "nama_instansi": agency,
                        "kategori": self.category,
                        "kota": self.city,
                        "link_source": agg["link"],
                        "deskripsi_it": f"{agg['paket']} paket pengadaan aktif" if agg["paket"] > 1 else "",
                        "status": "New",
                    }
                    for agency, agg in by_agency.items()
                ]
                self.emit_progress(len(leads), len(leads), f"{len(leads)} instansi terkumpul")
            except Exception as e:
                self.emit_progress(len(leads), len(leads), f"Error browser: {e}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass
        return leads

    def _profile_dir(self) -> str:
        import os
        return os.path.expanduser("~/playwright_chrome_profile_lpse")

    def _collect_rows(self, page, base_url: str) -> list[dict]:
        """Ambil baris tabel daftar lelang: (nama paket, instansi, link detail)."""
        out: list[dict] = []
        trs = page.locator("table tr")
        n = min(trs.count(), self.max_results * 4)
        for i in range(n):
            if self.is_cancelled():
                break
            tr = trs.nth(i)
            try:
                anchor = tr.locator('a[href*="lelang"], a[href*="detail"], a[href*="view"]')
                if anchor.count() == 0:
                    continue
                href = anchor.first.get_attribute("href") or ""
                paket = anchor.first.inner_text().strip()
                if not paket:
                    continue
                link = href if href.startswith("http") else urllib.parse.urljoin(base_url, href.split("?")[0])

                cells = tr.locator("td")
                agency = ""
                if cells.count() >= 3:
                    # kolom "Instansi/Pemilik Anggaran" biasanya kolom ke-3
                    agency = cells.nth(2).inner_text().strip()
                if not AGENCY_HINT.search(agency or ""):
                    # fallback: cari sel yang mirip nama instansi
                    for j in range(min(cells.count(), 6)):
                        txt = cells.nth(j).inner_text().strip()
                        if AGENCY_HINT.search(txt):
                            agency = txt
                            break
                out.append({"paket": paket, "agency": agency, "link": link})
            except Exception:
                continue
        return out
