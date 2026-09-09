"""Google / Web Search Scraper — enrichment data kontak (Telp/WA, Email, Website, Medsos).

Peran = ENRICHMENT (PRD v1.1):
Mencari informasi kontak untuk lead umum (rumah sakit, hotel, klinik, kafe, toko,
perusahaan, dll.) yang tidak tercantum atau kosong di Google Maps.
Hasil tidak dibuat sebagai lead baru, melainkan dicocokkan ke lead yang ada
dan hanya mengisi field yang masih kosong via `enrichment_service.match_and_merge`.
"""
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import uuid
from bs4 import BeautifulSoup
import httpx
from playwright.sync_api import sync_playwright

from backend.services.scrapers.base import BaseScraper
from backend.services.cleaner import normalize_phone, clean_social_url, is_valid_website
from backend.services.browser_profile import launch_login_browser_context

# Domain yang dikecualikan dari deteksi website resmi instansi
EXCLUDED_DOMAINS = {
    "google", "gstatic", "duckduckgo", "bing", "yahoo",
    "facebook", "instagram", "twitter", "x.com", "linkedin", "tiktok", "youtube", "pinterest",
    "wikipedia", "wikimapia", "kompas", "detik", "tribunnews", "tempo",
    "yellowpages", "indonetwork", "glints", "jobstreet",
}

# Domain email yang tidak valid / spam / tracker
EXCLUDED_EMAIL_DOMAINS = {
    "example.com", "domain.com", "duckduckgo.com", "google.com",
    "sentry.io", "w3.org", "schema.org", "cloudflare.com",
}

PHONE_RE = re.compile(r'(?:\+62|62|08|\(02\d{1,2}\)|02\d{1,2})[\s\-\.]?\d{2,4}[\s\-\.]?\d{2,4}[\s\-\.]?\d{2,6}')
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
IG_RE = re.compile(r'https?://(?:www\.|m\.)?instagram\.com/([A-Za-z0-9_.]{2,30})/?', re.IGNORECASE)
IG_BLOCKED = {"p", "reel", "reels", "explore", "accounts", "stories", "direct", "tv", "about", "developer"}


class GoogleScraper(BaseScraper):
    """Enrichment kontak umum via Web Search: isi `telp`, `email`, `website`, `sosmed`.

    `targets` = daftar nama instansi kandidat yang field kontaknya masih kosong.
    """

    source = "google"

    def __init__(
        self,
        category: str = "general",
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

    def _extract_from_text(self, text: str) -> tuple[str, str, str]:
        """Ekstrak telp, email, dan akun IG dari teks cuplikan hasil pencarian."""
        telp = ""
        email = ""
        ig = ""

        # 1. Telepon
        m_phones = PHONE_RE.findall(text)
        for raw_p in m_phones:
            p_clean = normalize_phone(raw_p)
            if p_clean and len(p_clean) >= 9:
                telp = p_clean
                break

        # 2. Email (kumpulkan semua email unik)
        m_emails = EMAIL_RE.findall(text)
        valid_emails = []
        for raw_e in m_emails:
            domain = raw_e.split("@")[-1].lower()
            clean_e = raw_e.lower()
            if domain not in EXCLUDED_EMAIL_DOMAINS and not domain.endswith(".png") and not domain.endswith(".jpg"):
                if clean_e not in valid_emails:
                    valid_emails.append(clean_e)
        email = ", ".join(valid_emails)

        # 3. Instagram
        m_ig = IG_RE.findall(text)
        for handle in m_ig:
            if handle.lower() not in IG_BLOCKED:
                ig = f"https://www.instagram.com/{handle}/"
                break

        return telp, email, ig

    def run(self) -> list[dict]:
        leads: list[dict] = []
        if not self.targets:
            self.emit_progress(0, 0, "Tidak ada lead dengan kontak kosong — enrichment dilewati.")
            return leads

        self.emit_progress(0, len(self.targets), f"Membuka browser pencarian kontak untuk {len(self.targets)} instansi…")

        worker_dir = None
        try:
            with sync_playwright() as p:
                context, worker_dir = launch_login_browser_context(
                    p,
                    job_id=self.job_id,
                    headless=False,
                    args=["--start-maximized"],
                )
                page = context.pages[0] if context.pages else context.new_page()
                self._page = page

                for i, target in enumerate(self.targets):
                    if self.is_cancelled():
                        break

                    self.emit_progress(i, len(self.targets), f"Mencari web: {target} ({self.city})")

                    query = f"{target} {self.city} kontak telepon email instagram website"
                    telp = ""
                    email = ""
                    website = ""
                    instagram = ""
                    facebook = ""
                    linkedin = ""
                    twitter_x = ""
                    tiktok = ""

                    try:
                        # 1. Buka Google Search dengan akun Google yang sudah login
                        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=id"
                        page.goto(search_url, timeout=35000, wait_until="domcontentloaded")
                        time.sleep(2)

                        html_content = page.content()
                        soup = BeautifulSoup(html_content, "html.parser")

                        # Cek apakah terbentur captcha Google
                        if "recaptcha" in html_content.lower() or "sorry/index" in page.url.lower():
                            # Fallback ke DuckDuckGo
                            ddg_url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}"
                            page.goto(ddg_url, timeout=35000, wait_until="domcontentloaded")
                            time.sleep(2)
                            html_content = page.content()
                            soup = BeautifulSoup(html_content, "html.parser")

                        snippets = [
                            el.get_text() for el in soup.select(
                                "#search, #rso, .MjjYud, .g, .kp-wholepage, .osrp-blk, article, .react-results--main, [data-testid='result']"
                            )
                        ]
                        combined_text = " ".join(snippets)
                        if not combined_text:
                            try:
                                combined_text = page.locator("body").inner_text()[:6000]
                            except Exception:
                                combined_text = ""

                        t_phone, t_email, t_ig = self._extract_from_text(combined_text)
                        if t_phone:
                            telp = t_phone
                        if t_email:
                            email = t_email
                        if t_ig and not instagram:
                            instagram = t_ig

                        # Cari tautan website resmi & medsos dari link hasil pencarian
                        for a in soup.find_all("a", href=True):
                            href = (a.get("href") or "").strip()
                            if not href or not href.startswith("http"):
                                continue

                            # Ekstrak IG
                            if not instagram and "instagram.com" in href.lower():
                                c_ig = clean_social_url(href, "instagram")
                                if c_ig:
                                    instagram = c_ig
                                    continue

                            # Ekstrak Facebook
                            if not facebook and ("facebook.com" in href.lower() or "fb.com" in href.lower()):
                                c_fb = clean_social_url(href, "facebook")
                                if c_fb:
                                    facebook = c_fb
                                    continue

                            # Ekstrak LinkedIn
                            if not linkedin and "linkedin.com" in href.lower():
                                c_li = clean_social_url(href, "linkedin")
                                if c_li:
                                    linkedin = c_li
                                    continue

                            # Ekstrak Twitter/X
                            if not twitter_x and ("twitter.com" in href.lower() or "x.com" in href.lower()):
                                c_tw = clean_social_url(href, "twitter_x")
                                if c_tw:
                                    twitter_x = c_tw
                                    continue

                            # Ekstrak TikTok
                            if not tiktok and "tiktok.com" in href.lower():
                                c_tt = clean_social_url(href, "tiktok")
                                if c_tt:
                                    tiktok = c_tt
                                    continue

                            # Ekstrak website resmi jika belum dapat
                            if not website:
                                if is_valid_website(href):
                                    try:
                                        parsed = urllib.parse.urlparse(href)
                                        domain = parsed.netloc.lower()
                                        if not any(ex in domain for ex in EXCLUDED_DOMAINS):
                                            website = f"{parsed.scheme}://{parsed.netloc}"
                                    except Exception:
                                        pass

                    except Exception as e:
                        self.emit_progress(i, len(self.targets), f"Pencarian '{target}' browser info: {e}")

                    leads.append({
                        "nama_instansi": target,
                        "kategori": self.category,
                        "kota": self.city,
                        "telp": telp,
                        "email": email,
                        "website": website,
                        "sosmed": instagram or facebook or linkedin or twitter_x or tiktok,
                        "instagram": instagram,
                        "facebook": facebook,
                        "linkedin": linkedin,
                        "twitter_x": twitter_x,
                        "tiktok": tiktok,
                    })

                    found_items = []
                    if telp:
                        found_items.append("Telp")
                    if email:
                        found_items.append("Email")
                    if website:
                        found_items.append("Web")
                    if instagram:
                        found_items.append("IG")
                    if facebook:
                        found_items.append("FB")
                    if linkedin:
                        found_items.append("LI")
                    if twitter_x:
                        found_items.append("X")

                    info_str = f" ({', '.join(found_items)})" if found_items else " (tidak ditemukan kontak baru)"
                    self.emit_progress(i + 1, len(self.targets), f"Selesai: {target}{info_str}")
                    self.rate_limit()

                self._page = None
                try:
                    context.close()
                except Exception:
                    pass

        except Exception as e:
            # Fallback jika browser Playwright gagal dibuka
            self.emit_progress(0, len(self.targets), f"Browser Playwright gagal dibuka, beralih ke HTTP: {e}")
            leads = self._run_http_fallback()
        finally:
            self._page = None
            if worker_dir:
                try:
                    shutil.rmtree(worker_dir, ignore_errors=True)
                except Exception:
                    pass

        return leads

    def _run_http_fallback(self) -> list[dict]:
        leads: list[dict] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        with httpx.Client(verify=False, timeout=15.0, headers=headers, follow_redirects=True) as client:
            for i, target in enumerate(self.targets):
                if self.is_cancelled():
                    break
                self.emit_progress(i, len(self.targets), f"Mencari web (HTTP): {target} ({self.city})")
                query = f"{target} {self.city} kontak telepon email instagram website"
                telp = ""
                email = ""
                website = ""
                instagram = ""
                facebook = ""
                linkedin = ""
                twitter_x = ""
                try:
                    search_url = "https://html.duckduckgo.com/html/"
                    resp = client.post(search_url, data={"q": query})
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        snippets = [el.get_text() for el in soup.select(".result__snippet")]
                        combined_text = " ".join(snippets)
                        t_phone, t_email, t_ig = self._extract_from_text(combined_text)
                        if t_phone:
                            telp = t_phone
                        if t_email:
                            email = t_email
                        if t_ig:
                            instagram = t_ig

                        for a in soup.select(".result__url"):
                            href = (a.get("href") or "").strip()
                            if not href:
                                continue
                            if not href.startswith("http"):
                                href = "https://" + href
                            if not instagram and "instagram.com" in href.lower():
                                c_ig = clean_social_url(href, "instagram")
                                if c_ig:
                                    instagram = c_ig
                                    continue
                            if not facebook and ("facebook.com" in href.lower() or "fb.com" in href.lower()):
                                c_fb = clean_social_url(href, "facebook")
                                if c_fb:
                                    facebook = c_fb
                                    continue
                            if not linkedin and "linkedin.com" in href.lower():
                                c_li = clean_social_url(href, "linkedin")
                                if c_li:
                                    linkedin = c_li
                                    continue
                            if not twitter_x and ("twitter.com" in href.lower() or "x.com" in href.lower()):
                                c_tw = clean_social_url(href, "twitter_x")
                                if c_tw:
                                    twitter_x = c_tw
                                    continue
                            if not tiktok and "tiktok.com" in href.lower():
                                c_tt = clean_social_url(href, "tiktok")
                                if c_tt:
                                    tiktok = c_tt
                                    continue
                            if not website:
                                if is_valid_website(href):
                                    try:
                                        parsed = urllib.parse.urlparse(href)
                                        domain = parsed.netloc.lower()
                                        if not any(ex in domain for ex in EXCLUDED_DOMAINS):
                                            website = f"{parsed.scheme}://{parsed.netloc}"
                                    except Exception:
                                        pass
                except Exception as e:
                    self.emit_progress(i, len(self.targets), f"Pencarian web '{target}' dilewati: {e}")

                leads.append({
                    "nama_instansi": target,
                    "kategori": self.category,
                    "kota": self.city,
                    "telp": telp,
                    "email": email,
                    "website": website,
                    "sosmed": instagram or facebook or linkedin or twitter_x,
                    "instagram": instagram,
                    "facebook": facebook,
                    "linkedin": linkedin,
                    "twitter_x": twitter_x,
                })
                self.emit_progress(i + 1, len(self.targets), f"Selesai (HTTP): {target}")
                self.rate_limit()
        return leads
