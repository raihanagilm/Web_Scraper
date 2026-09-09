"""Google Maps scraper — multi-kategori sesuai PRD v1.1.

Kategori utama:
- Sekolah
- Perusahaan / Corporate (Jateng)
- UMKM, Retail, Resto/Kafe
- Vendor B2G / Kontraktor
"""
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import uuid

from playwright.sync_api import sync_playwright

from backend.services.scrapers.base import BaseScraper
from backend.services.cleaner import normalize_phone
from backend.services.browser_profile import (
    launch_login_browser_context,
    get_login_profile_dir,
    is_login_profile_ready,
)

# Regex filter untuk kategori sekolah (mencakup singkatan Indonesia, bahasa Inggris, dan variasi Islam/Kristen)
VALID_SCHOOL = (
    r'(?i)\b('
    r'paud|tk|tka|tkb|ra|ba|kb|playgroup|'
    r'sd|sdn|sdi|sdit|sdtq|mi|min|'
    r'smp|smpn|smpi|smpit|mts|mtsn|'
    r'sma|sman|smai|smait|smk|smkn|ma|man|mak|'
    r'slb|universitas|institut|politeknik|akademi|sekolah|pesantren|ponpes|'
    r'school|high\s*school|junior\s*high|elementary|kindergarten|vocational|college|academy|madrasah'
    r')\b'
)
INVALID_SCHOOL = r'(?i)\b(lpk|kursus|les|bimbel|toko|agen|pt|cv|pelatihan|bengkel|tour|travel|printing|fotocopy|jasa|sewa|warung|koperasi|klinik|apotek|salon)\b'

# Mapping kategori PRD v1.1 ke keyword pencarian GMaps
CATEGORY_KEYWORDS = {
    # Sekolah
    "sekolah": "sekolah",
    # Perusahaan / Corporate
    "corporate": "perusahaan",
    "perusahaan": "perusahaan",
    # UMKM, Retail, Resto/Kafe
    "umkm": "umkm",
    "retail": "retail",
    "resto": "restoran",
    "restoran": "restoran",
    "kafe": "kafe",
    "cafe": "kafe",
    # Vendor B2G / Kontraktor
    "vendor": "vendor pengadaan",
    "kontraktor": "kontraktor",
    "b2g": "vendor pemerintah",
}

# Mapping kategori ke sumber enrichment (PRD v1.1 §5.3)
CATEGORY_ENRICHMENT = {
    "sekolah": ["dapodik", "google"],
    "corporate": ["google"],
    "perusahaan": ["google"],
    "umkm": ["google"],
    "retail": ["google"],
    "resto": ["google"],
    "restoran": ["google"],
    "kafe": ["google"],
    "cafe": ["google"],
    "rumah sakit": ["google"],
    "klinik": ["google"],
    "hotel": ["google"],
    "vendor": ["google"],
    "kontraktor": ["google"],
    "b2g": ["google"],
}


def get_enrichment_sources(category: str) -> list[str]:
    """Mengembalikan list sumber enrichment untuk kategori tertentu (PRD v1.1)."""
    cat = category.strip().lower()
    # Cari exact match dulu
    if cat in CATEGORY_ENRICHMENT:
        return CATEGORY_ENRICHMENT[cat]
    # Fallback: cari partial match
    for key, sources in CATEGORY_ENRICHMENT.items():
        if key in cat or cat in key:
            return sources
    # Default fallback untuk kategori umum adalah google search
    return ["google"]


# --- Instagram: hanya profil bisnis yang valid ---
IG_PROFILE_RE = re.compile(
    r'https?://(?:www\.|m\.)?instagram\.com/([A-Za-z0-9_.]{1,30})/?', re.IGNORECASE
)
# Path non-profil: post/reel/explore/dll — bukan akun bisnis
IG_BLOCKED_SEGMENTS = {
    "p", "reel", "reels", "explore", "accounts", "stories", "direct", "tv",
    "directory", "hashtag", "about", "legal", "developer", "press", "sitemap",
    "google", "web", "api", "graphql", "invites", "share",
}


class GmapsScraper(BaseScraper):
    source = "gmaps"

    def __init__(self, category: str = "sekolah", city: str = "salatiga", max_results: int = 100, job_id: str | None = None):
        super().__init__(source=self.source, category=category, city=city, max_results=max_results)
        self.job_id = job_id
        self._page = None  # page aktif — dipakai is_alive() untuk deteksi browser ditutup

    def is_alive(self) -> bool:
        """False jika jendela Chrome scrape sudah ditutup/crash (dipakai JobManager.reconcile)."""
        try:
            return self._page is None or not self._page.is_closed()
        except Exception:
            return True

    def _build_query(self) -> str:
        keyword = CATEGORY_KEYWORDS.get(self.category.strip().lower(), self.category.strip())
        return f"{keyword} di {self.city}"

    def _is_target(self, name: str) -> bool:
        """Filter nama: hanya untuk kategori sekolah; umum tidak difilter keras."""
        cat = self.category.strip().lower()
        if cat in ("sekolah", "paud", "sd", "smp", "sma", "smk") or "sekolah" in cat:
            n = name.lower()
            if not re.search(VALID_SCHOOL, n):
                return False
            # Jika mengandung entitas sekolah valid (misal 'Sekolah', 'School', 'SMK', 'SMA', 'SMP', 'SD'),
            # jangan tolak hanya karena ada kata 'yayasan' di depannya.
            if re.search(INVALID_SCHOOL, n) and not re.search(r'(?i)\b(sekolah|school|sd|smp|sma|smk|madrasah|pesantren|tk|paud|slb)\b', n):
                return False
        return True

    def _extract_detail(self, page) -> dict:
        """Setelah klik listing, ekstrak semua field dari halaman detail."""
        time.sleep(1.5)

        # Scroll panel detail ke bawah secara langsung agar link medsos / website termuat
        try:
            page.evaluate("""() => {
                const main = document.querySelector('div[role="main"]');
                if (main) main.scrollTop = main.scrollHeight;
            }""")
            time.sleep(1.0)
        except Exception:
            pass

        alamat = "-"
        try:
            addr_el = page.locator('button[data-item-id="address"] div.Io6YTe')
            if addr_el.count() > 0:
                alamat = addr_el.first.inner_text().strip()
        except Exception:
            pass

        telp = "-"
        try:
            telp_el = page.locator('button[data-item-id^="phone:tel:"] div.Io6YTe')
            if telp_el.count() > 0:
                telp = normalize_phone(telp_el.first.inner_text().strip())
        except Exception:
            pass
        if not telp or telp == "-":
            telp = ""

        website = ""
        try:
            web_el = page.locator('a[data-item-id="authority"]')
            if web_el.count() > 0:
                website = web_el.first.get_attribute("href") or ""
        except Exception:
            pass

        # email / NPSN / instagram dari seluruh teks halaman
        email = ""
        npsn = ""
        instagram = ""
        kemendikdasmen_link = ""
        try:
            detail_text = page.locator('div[role="main"]').inner_text(timeout=5000)
        except Exception:
            detail_text = ""
        m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', detail_text)
        if m:
            email = m.group(0)
        n = re.search(r'(?i)NPSN[\s\:\-]*(\d{8})', detail_text)
        if not n:
            n = re.search(r'\b(\d{8})\b', detail_text)
        if n:
            npsn = n.group(1)

        # cek content + frames utk link eksternal (website, IG, kemendikdasmen)
        html = ""
        try:
            html += page.content()
        except Exception:
            pass
        for frame in page.frames:
            try:
                html += frame.content()
            except Exception:
                pass
        unquoted = urllib.parse.unquote(html)
        if not website:
            web_matches = re.findall(r'(https?://[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}[^\s"\'<\\]*)', unquoted)
            exclusions = ["google", "gstatic", "ggpht", "googleusercontent", "facebook", "youtube", "wikipedia", "kemendikbud",
                          "kemendikdasmen", "instagram", "twitter", "tiktok", "linkedin", "w3.org",
                          "playwright", "schema.org", "wa.me", "whatsapp"]
            for w in web_matches:
                clean_w = w.split('&')[0].rstrip('.,;)')
                if not any(ex in clean_w.lower() for ex in exclusions):
                    website = clean_w
                    break
        instagram = self._find_instagram(page, unquoted)
        facebook = ""
        fb_match = re.search(r'https?://(?:www\.)?(?:facebook\.com|fb\.com)/[A-Za-z0-9_.\-]+', unquoted)
        if fb_match:
            cand_fb = fb_match.group(0).rstrip('.,;)')
            if not any(b in cand_fb.lower() for b in ["sharer", "share", "policies", "help", "login"]):
                facebook = cand_fb

        linkedin = ""
        li_match = re.search(r'https?://(?:www\.)?linkedin\.com/(?:company|school)/[A-Za-z0-9_.\-]+', unquoted)
        if li_match:
            linkedin = li_match.group(0).rstrip('.,;)')

        twitter_x = ""
        tw_match = re.search(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+', unquoted)
        if tw_match:
            cand_tw = tw_match.group(0).rstrip('.,;)')
            if not any(b in cand_tw.lower() for b in ["intent", "share", "home", "search"]):
                twitter_x = cand_tw

        tiktok = ""
        tt_match = re.search(r'https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9_.\-]+', unquoted)
        if tt_match:
            tiktok = tt_match.group(0).rstrip('.,;)')

        if not kemendikdasmen_link:
            kem = re.search(r'(https?://[a-zA-Z0-9.\-]*kemendikdasmen\.go\.id/[^\s"\'<>\\&]+)', unquoted)
            if kem:
                kemendikdasmen_link = kem.group(1).rstrip('.,;)')

        return {
            "nama_instansi": "",
            "kategori": self.category,
            "telp": telp,
            "email": email,
            "alamat": alamat if alamat != "-" else "",
            "kota": self.city,
            "link_gmaps": page.url,
            "website": website,
            "sosmed": instagram or facebook or linkedin or twitter_x or tiktok,
            "instagram": instagram,
            "facebook": facebook,
            "linkedin": linkedin,
            "twitter_x": twitter_x,
            "tiktok": tiktok,
            "link_source": kemendikdasmen_link or "",
            "npsn": npsn,
            "status": "New",
        }
    def _profile_dir(self) -> str:
        """Profil Chrome persisten bersama — login sekali berlaku utk semua kota."""
        return get_login_profile_dir()

    # ---- Ekstraksi Instagram (akurat, ala file lama tapi diperketat) ----
    def _clean_ig_url(self, url: str) -> str:
        """Normalisasi & validasi URL IG → hanya URL profil yang valid."""
        u = (url or "").split("&")[0].split("?")[0].rstrip(".,;)'\"")
        m = IG_PROFILE_RE.match(u)
        if not m:
            return ""
        if m.group(1).lower() in IG_BLOCKED_SEGMENTS:
            return ""
        return f"https://www.instagram.com/{m.group(1)}/"

    def _find_instagram(self, page, unquoted_html: str) -> str:
        """Cari IG milik bisnis: prioritas link yang tampil di panel detail,
        lalu fallback URL di HTML/frames dengan voting frekuensi.
        (Regex mentah ala script lama sering menangkap IG milik orang lain
        dari atribusi foto reviewer.)"""
        # 1) Anchor IG yang benar-benar dirender di panel detail (link resmi bisnis)
        try:
            anchors = page.locator('div[role="main"] a[href*="instagram.com"]')
            for i in range(min(anchors.count(), 10)):
                cand = self._clean_ig_url(anchors.nth(i).get_attribute("href") or "")
                if cand:
                    return cand
        except Exception:
            pass
        # 2) Fallback: kandidat dari HTML/frames, pilih yang paling sering muncul
        counts: dict[str, int] = {}
        for raw in re.findall(
            r'https?://(?:www\.|m\.)?instagram\.com/[A-Za-z0-9_.]+', unquoted_html
        ):
            clean = self._clean_ig_url(raw)
            if clean:
                counts[clean] = counts.get(clean, 0) + 1
        return max(counts, key=counts.get) if counts else ""

    # ---- Browser login (akun Google utk Maps) ----
    def browser_status(self) -> dict:
        """Cek profil persisten: ada & berisi cookie login."""
        profile = self._profile_dir()
        return {
            "profile": profile,
            "profile_exists": os.path.isdir(profile),
            "has_cookies": is_login_profile_ready(),
        }

    def browser_login(self) -> None:
        """Buka Chrome headful ke Google Maps agar user login manual sekali.
        Sesi tersimpan di profil persisten; jendela ditutup manual oleh user."""
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self._profile_dir(),
                headless=False,
                channel="chrome",
                ignore_https_errors=True,
                args=["--start-maximized"],
            )
            page = context.new_page()
            try:
                page.goto("https://www.google.com/maps", timeout=60000)
                page.wait_for_event("close", timeout=0)  # tunggu user menutup tab
            except Exception:
                pass
            finally:
                try:
                    context.close()
                except Exception:
                    pass

    def run(self) -> list[dict]:
        leads: list[dict] = []
        self.emit_progress(0, 0, f"Membuka Google Maps untuk '{self._build_query()}'")

        with sync_playwright() as p:
            context, worker_dir = launch_login_browser_context(
                p,
                job_id=self.job_id,
                headless=False,
                args=["--start-maximized"],
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                self._page = page
                url = f"https://www.google.com/maps/search/{urllib.parse.quote(self._build_query())}"
                try:
                    page.goto(url, timeout=60000)
                    try:
                        page.wait_for_selector('div[role="feed"]', timeout=20000)
                    except Exception:
                        pass
                    time.sleep(4)

                    # scroll untuk memuat daftar
                    max_scroll = 5
                    last_count = 0
                    scroll_no_change = 0
                    current = 0
                    while current < self.max_results and scroll_no_change < max_scroll:
                        if self.is_cancelled():
                            break
                        try:
                            page.evaluate("""() => {
                                const feed = document.querySelector('div[role="feed"]');
                                if (feed) feed.scrollBy(0, 1500);
                            }""")
                            self.rate_limit()  # delay 1-3 detik
                        except Exception:
                            pass
                        try:
                            current = page.locator('div[role="feed"] a.hfpxzc').count()
                        except Exception:
                            current = 0

                        self.emit_progress(0, current, f"Memuat daftar Google Maps ({current} item ditemukan)...")

                        # Cek apakah sudah mencapai akhir daftar
                        try:
                            is_end = page.evaluate("""() => {
                                const endEl = document.querySelector('span.HlvSq');
                                return endEl && endEl.innerText.length > 0;
                            }""")
                            if is_end:
                                break
                        except Exception:
                            pass

                        if current == last_count:
                            scroll_no_change += 1
                        else:
                            scroll_no_change = 0
                            last_count = current

                    listings = page.locator('div[role="feed"] a.hfpxzc').all()
                    self.emit_progress(0, len(listings), f"Ditemukan {len(listings)} hasil")

                    processed: set[str] = set()
                    for i, listing in enumerate(listings):
                        if len(leads) >= self.max_results or self.is_cancelled():
                            break
                        try:
                            # Scroll feed container via JS agar item ke-i pasti berada di viewport
                            # dan dirender oleh virtual DOM Google Maps
                            try:
                                page.evaluate("""(idx) => {
                                    const feed = document.querySelector('div[role="feed"]');
                                    if (!feed) return;
                                    const items = feed.querySelectorAll('a.hfpxzc');
                                    if (items[idx]) {
                                        items[idx].scrollIntoView({ block: 'center' });
                                    } else {
                                        feed.scrollBy(0, 400);
                                    }
                                }""", i)
                                time.sleep(0.3)
                            except Exception:
                                pass

                            try:
                                raw_name = listing.get_attribute("aria-label", timeout=2500) or f"Item {i+1}"
                            except Exception:
                                # Jika get_attribute timeout karena virtual DOM belum render, scroll lagi dan re-try sekali
                                try:
                                    page.evaluate("""() => {
                                        const feed = document.querySelector('div[role="feed"]');
                                        if (feed) feed.scrollBy(0, 500);
                                    }""")
                                    time.sleep(0.5)
                                    raw_name = listing.get_attribute("aria-label", timeout=2500) or f"Item {i+1}"
                                except Exception:
                                    continue

                            name = re.sub(r'\s*·?\s*Visited link\s*', '', raw_name, flags=re.IGNORECASE).strip()
                            if name in processed:
                                continue
                            if not self._is_target(name):
                                self.emit_progress(len(leads), len(listings), f"Skip (bukan target): {name}")
                                continue
                            self.emit_progress(len(leads), len(listings), f"Mengekstrak: {name}")
                            try:
                                listing.click(timeout=4000)
                            except Exception:
                                try:
                                    listing.click(force=True, timeout=2000)
                                except Exception:
                                    page.evaluate("""(idx) => {
                                        const feed = document.querySelector('div[role="feed"]');
                                        if (feed) {
                                            const items = feed.querySelectorAll('a.hfpxzc');
                                            if (items[idx]) items[idx].click();
                                        }
                                    }""", i)
                            detail = self._extract_detail(page)
                            detail["nama_instansi"] = name
                            detail["source"] = self.source
                            leads.append(detail)
                            processed.add(name)
                            target = min(self.max_results, len(listings))
                            self.emit_progress(len(leads), len(listings), f"Berhasil mengekstrak ({len(leads)}/{target}): {name}")
                            self.rate_limit()
                        except Exception as e:
                            self.emit_progress(len(leads), len(listings), f"Error item: {e}")
                            continue
                except Exception as e:
                    self.emit_progress(len(leads), len(leads), f"Error browser: {e}")
            finally:
                self._page = None
                try:
                    context.close()
                except Exception:
                    pass
                if worker_dir:
                    try:
                        shutil.rmtree(worker_dir, ignore_errors=True)
                    except Exception:
                        pass
        return leads
