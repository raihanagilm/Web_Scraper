"""Glints scraper — lead dari perusahaan yang sedang membuka lowongan kerja.

Lead = perusahaan (nama_instansi). Posisi lowongan digabung ke
`posisi_rekrutmen`; link lowongan pertama ke `link_source`.
"""
import re
import urllib.parse

from playwright.sync_api import sync_playwright

from backend.services.scrapers.base import BaseScraper


class GlintsScraper(BaseScraper):
    source = "glints"

    def __init__(self, category: str = "it", city: str = "salatiga", max_results: int = 100):
        super().__init__(source=self.source, category=category, city=city, max_results=max_results)

    def _profile_dir(self) -> str:
        import os
        return os.path.expanduser("~/playwright_chrome_profile_glints")

    def _build_url(self) -> str:
        return "https://glints.com/id/opportunities?" + urllib.parse.urlencode(
            {"keyword": self.category, "locationName": self.city}
        )

    def run(self) -> list[dict]:
        leads: list[dict] = []
        self.emit_progress(0, 0, f"Membuka Glints: '{self.category}' di {self.city}")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self._profile_dir(),
                headless=False,
                channel="chrome",
                ignore_https_errors=True,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            )
            page = context.new_page()
            try:
                page.goto(self._build_url(), timeout=60000, wait_until="domcontentloaded")
                page.wait_for_selector('a[href*="/opportunities/"]', timeout=25000)
                self.rate_limit()

                # scroll untuk memuat kartu (SPA — lazy load)
                seen, no_change = 0, 0
                while no_change < 3 and not self.is_cancelled():
                    page.evaluate("window.scrollBy(0, 1600)")
                    self.rate_limit()
                    count = page.locator('a[href*="/opportunities/"]').count()
                    if count == seen:
                        no_change += 1
                    else:
                        no_change, seen = 0, count
                    if seen >= self.max_results * 3:
                        break

                cards = self._collect_cards(page)
                self.emit_progress(0, len(cards), f"Ditemukan {len(cards)} lowongan — dikelompokkan per perusahaan")

                by_company: dict[str, dict] = {}
                for c in cards:
                    if self.is_cancelled() or len(by_company) >= self.max_results:
                        break
                    company = re.sub(r"\s+", " ", c["company"] or "").strip()
                    if not company:
                        continue
                    agg = by_company.setdefault(company, {"titles": [], "link": ""})
                    if c["title"] and c["title"] not in agg["titles"]:
                        agg["titles"].append(c["title"])
                    if not agg["link"]:
                        agg["link"] = c["link"]

                leads = [
                    {
                        "nama_instansi": company,
                        "kategori": self.category,
                        "kota": self.city,
                        "posisi_rekrutmen": "; ".join(agg["titles"])[:255],
                        "link_source": agg["link"],
                        "status": "New",
                    }
                    for company, agg in by_company.items()
                ]
                self.emit_progress(len(leads), len(leads), f"{len(leads)} perusahaan terkumpul")
            except Exception as e:
                self.emit_progress(len(leads), len(leads), f"Error browser: {e}")
            finally:
                try:
                    context.close()
                except Exception:
                    pass
        return leads

    def _collect_cards(self, page) -> list[dict]:
        """Kartu Glints: anchor ke /opportunities/, teks biasanya
        'Judul Lowongan\\nNama Perusahaan'."""
        out: list[dict] = []
        anchors = page.locator('a[href*="/opportunities/"]')
        n = min(anchors.count(), self.max_results * 4)
        for i in range(n):
            if self.is_cancelled():
                break
            a = anchors.nth(i)
            try:
                href = a.get_attribute("href") or ""
                text = a.inner_text().strip()
                if not href or not text:
                    continue
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if len(lines) >= 2:
                    title, company = lines[0], lines[1]
                else:
                    title, company = lines[0] if lines else "", ""
                out.append({
                    "title": title,
                    "company": company,
                    "link": href if href.startswith("http") else f"https://glints.com{href}",
                })
            except Exception:
                continue
        return out
