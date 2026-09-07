"""Jobstreet scraper — lead dari perusahaan yang sedang membuka lowongan kerja.

Lead = perusahaan (nama_instansi). Semua posisi lowongan per perusahaan
digabung ke kolom `posisi_rekrutmen`; link lowongan pertama ke `link_source`.
"""
import re
import urllib.parse

from playwright.sync_api import sync_playwright

from backend.services.scrapers.base import BaseScraper


class JobstreetScraper(BaseScraper):
    source = "jobstreet"

    def __init__(self, category: str = "it", city: str = "salatiga", max_results: int = 100):
        super().__init__(source=self.source, category=category, city=city, max_results=max_results)

    def _profile_dir(self) -> str:
        import os
        return os.path.expanduser("~/playwright_chrome_profile_jobstreet")

    def _build_url(self) -> str:
        return "https://www.jobstreet.co.id/id/job-search?" + urllib.parse.urlencode(
            {"q": self.category, "where": self.city}
        )

    def run(self) -> list[dict]:
        leads: list[dict] = []
        self.emit_progress(0, 0, f"Membuka Jobstreet: '{self.category}' di {self.city}")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self._profile_dir(),
                headless=False,  # Jobstreet memblokir headless — pakai Chrome headful
                channel="chrome",
                ignore_https_errors=True,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            )
            page = context.new_page()
            try:
                page.goto(self._build_url(), timeout=60000)
                page.wait_for_selector("article", timeout=20000)
                self.rate_limit()

                # scroll feed untuk memuat kartu lowongan
                seen, no_change = 0, 0
                while no_change < 3 and not self.is_cancelled():
                    page.evaluate("window.scrollBy(0, 1600)")
                    self.rate_limit()
                    count = page.locator("article").count()
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
                    agg = by_company.setdefault(
                        company, {"titles": [], "link": "", "location": ""}
                    )
                    if c["title"] and c["title"] not in agg["titles"]:
                        agg["titles"].append(c["title"])
                    if not agg["link"]:
                        agg["link"] = c["link"]
                    if not agg["location"]:
                        agg["location"] = c["location"]

                leads = [
                    {
                        "nama_instansi": company,
                        "kategori": self.category,
                        "kota": agg["location"] or self.city,
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
        """Ambil (judul, perusahaan, lokasi, link) dari kartu lowongan."""
        out: list[dict] = []
        cards = page.locator("article")
        n = min(cards.count(), self.max_results * 4)
        for i in range(n):
            if self.is_cancelled():
                break
            card = cards.nth(i)
            try:
                title, link = "", ""
                anchors = card.locator('a[href*="jobstreet.co.id"]')
                for j in range(min(anchors.count(), 6)):
                    href = anchors.nth(j).get_attribute("href") or ""
                    if "/job/" in href:
                        link = href.split("?")[0]
                        title = anchors.nth(j).inner_text().strip()
                        break
                if not title:
                    h = card.locator("h1, h2, h3")
                    if h.count() > 0:
                        title = h.first.inner_text().strip()

                company = self._first_text(
                    card,
                    ['[data-testid="job-card__company-name"]', "a[href*='/companies/']", "span[class*='company']"],
                )
                location = self._first_text(
                    card, ['[data-testid="job-card__location"]', "span[class*='location']"]
                )
                if title or company:
                    out.append({"title": title, "company": company, "location": location, "link": link})
            except Exception:
                continue
        return out

    @staticmethod
    def _first_text(card, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                el = card.locator(sel)
                if el.count() > 0:
                    return el.first.inner_text().strip()
            except Exception:
                continue
        return ""
