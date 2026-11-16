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

from app.Services.scrapers.base import BaseScraper
from app.Services.cleaner import normalize_phone, clean_social_url, is_valid_website
from app.Services.scrapers.website_enricher import WebsiteContactEnricher
from app.config import settings
from app.Services.browser_profile import (
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

    def __init__(self, category: str = "sekolah", city: str = "salatiga", max_results: int = 100, job_id: str | None = None, user_id: int | None = None):
        super().__init__(source=self.source, category=category, city=city, max_results=max_results, user_id=user_id)
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

    def _is_city_match(self, alamat: str) -> bool:
        """Validasi apakah alamat masih berada di wilayah kota target (anti-nyasar)."""
        if not alamat or alamat == "-" or not self.city:
            return True
        c = self.city.strip().lower()
        a = alamat.lower()
        # Jika nama kota langsung ada di teks alamat -> valid
        if c in a:
            return True

        # Daftar kota/kabupaten lain di Indonesia untuk mendeteksi hasil rekomendasi yang meluber
        known_other_cities = [
            "semarang", "surakarta", "solo", "salatiga", "magelang", "pekalongan", "tegal",
            "kudus", "pati", "jepara", "demak", "kendal", "batang", "boyolali", "klaten",
            "sukoharjo", "karanganyar", "sragen", "wonogiri", "purwokerto", "banyumas",
            "cilacap", "kebumen", "purworejo", "temanggung", "wonosobo", "brebes", "pemalang",
            "jogja", "yogyakarta", "sleman", "bantul", "kulon progo", "gunungkidul",
            "surabaya", "malang", "sidoarjo", "gresik", "bandung", "jakarta", "bekasi", "tangerang", "bogor"
        ]
        for other in known_other_cities:
            if other != c and other in a and not (c in other or other in c):
                return False
        return True

    def _is_category_match(self, name: str, category_text: str) -> bool:
        """Validasi apakah entitas sesuai dengan kategori pencarian (anti-salah kategori)."""
        cat_lower = self.category.strip().lower()
        name_lower = name.strip().lower()
        ct_lower = category_text.strip().lower()

        # 1. Kategori Sekolah
        if cat_lower == "sekolah" or "sekolah" in cat_lower:
            if not re.search(VALID_SCHOOL, name_lower):
                if not re.search(r'(?i)\b(sekolah|school|madrasah|pesantren|universitas|akademi|politeknik|college|institut)\b', ct_lower):
                    return False
            if re.search(INVALID_SCHOOL, name_lower) and not re.search(r'(?i)\b(sekolah|school|sd|smp|sma|smk|madrasah|pesantren|tk|paud|slb)\b', name_lower):
                return False
            if re.search(r'(?i)\b(toko|fotokopi|percetakan|bengkel|dealer|agen|counter|pulsa|laundry|salon)\b', ct_lower):
                return False
            return True

        # 2. Kategori Kafe / Resto
        if cat_lower in ("kafe", "cafe", "resto", "restoran"):
            if ct_lower:
                fnb_pattern = r'(?i)\b(kafe|cafe|kopi|coffee|resto|restoran|rumah makan|warung|kuliner|bakso|mie|food|beverage|snack|kedai|bistro|eatery)\b'
                if not re.search(fnb_pattern, ct_lower) and not re.search(fnb_pattern, name_lower):
                    if re.search(r'(?i)\b(apotek|bank|bengkel|toko|salon|laundry|klinik|kantor|dealer|fotokopi)\b', ct_lower):
                        return False
            return True

        # 3. Kategori Perusahaan / Corporate
        if cat_lower in ("corporate", "perusahaan"):
            if ct_lower and re.search(r'(?i)\b(warung|toko kelontong|pasar|penjual|kios)\b', ct_lower):
                return False
            return True

        return True

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
        """Setelah klik listing, ekstrak field khusus dari panel detail aktif (div[role="main"])."""
        # Tunggu panel detail siap secara cepat
        try:
            page.locator('div[role="main"]').wait_for(state="visible", timeout=1200)
        except Exception:
            pass

        alamat = "-"
        kategori_gmaps = ""
        telp = ""
        website = ""
        instagram = ""
        facebook = ""
        tiktok = ""
        twitter_x = ""
        linkedin = ""
        email = ""
        npsn = ""

        # 1. Alamat
        try:
            addr_el = page.locator('div[role="main"] button[data-item-id="address"] div.Io6YTe')
            if addr_el.count() > 0:
                alamat = addr_el.first.inner_text().strip()
        except Exception:
            pass

        # 2. Kategori Resmi Google Maps
        try:
            cat_loc = page.locator('div[role="main"] button[jsaction*="category"], div[role="main"] button.DkEaL')
            if cat_loc.count() > 0:
                kategori_gmaps = cat_loc.first.inner_text().strip()
        except Exception:
            pass

        # 3. Telepon
        try:
            telp_el = page.locator('div[role="main"] button[data-item-id^="phone:tel:"] div.Io6YTe')
            if telp_el.count() > 0:
                telp = normalize_phone(telp_el.first.inner_text().strip())
        except Exception:
            pass

        # 4. Website Resmi — HANYA ambil dari tombol authority di panel aktif
        # Jangan regex ke seluruh halaman/iframe karena akan mencemari data tempat lain!
        try:
            web_el = page.locator('div[role="main"] a[data-item-id="authority"]')
            if web_el.count() > 0:
                raw_web = web_el.first.get_attribute("href") or ""
                if is_valid_website(raw_web):
                    website = raw_web
        except Exception:
            pass

        # 5. Media Sosial — HANYA ambil dari anchor di dalam div[role="main"] milik tempat ini
        try:
            anchors = page.locator('div[role="main"] a[href]')
            for i in range(min(anchors.count(), 20)):
                href = anchors.nth(i).get_attribute("href") or ""
                h_low = href.lower()
                if not instagram and "instagram.com" in h_low:
                    c = clean_social_url(href, "instagram")
                    if c: instagram = c
                elif not facebook and ("facebook.com" in h_low or "fb.com" in h_low):
                    c = clean_social_url(href, "facebook")
                    if c: facebook = c
                elif not tiktok and "tiktok.com" in h_low:
                    c = clean_social_url(href, "tiktok")
                    if c: tiktok = c
                elif not twitter_x and ("twitter.com" in h_low or "x.com" in h_low):
                    c = clean_social_url(href, "twitter_x")
                    if c: twitter_x = c
                elif not linkedin and "linkedin.com" in h_low:
                    c = clean_social_url(href, "linkedin")
                    if c: linkedin = c
        except Exception:
            pass

        # 6. Email & NPSN jika tertera di teks panel detail
        try:
            detail_text = page.locator('div[role="main"]').inner_text(timeout=1000)
            m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', detail_text)
            if m:
                email = m.group(0)
            n = re.search(r'(?i)NPSN[\s\:\-]*(\d{8})', detail_text)
            if not n:
                n = re.search(r'\b(\d{8})\b', detail_text)
            if n:
                npsn = n.group(1)
        except Exception:
            pass

        # 7. Deteksi direct WhatsApp dari link website jika ada
        if website and ("wa.me" in website.lower() or "api.whatsapp.com" in website.lower()):
            m_wa = re.search(r'(?:phone=|wa\.me/)([\d\+]+)', website)
            if m_wa:
                wa_clean = normalize_phone(m_wa.group(1))
                if wa_clean and not telp:
                    telp = wa_clean

        # 8. Auto-enrichment langsung: ekstrak WhatsApp, medsos, dan email dari website resmi secara otomatis
        if website:
            try:
                enricher = WebsiteContactEnricher(timeout=3.5)
                w_data = enricher.enrich(website)
                if not telp and w_data.get("telp"):
                    telp = w_data["telp"]
                if not email and w_data.get("email"):
                    email = w_data["email"]
                if not instagram and w_data.get("instagram"):
                    instagram = w_data["instagram"]
                if not facebook and w_data.get("facebook"):
                    facebook = w_data["facebook"]
                if not tiktok and w_data.get("tiktok"):
                    tiktok = w_data["tiktok"]
                if not twitter_x and w_data.get("twitter_x"):
                    twitter_x = w_data["twitter_x"]
                if not linkedin and w_data.get("linkedin"):
                    linkedin = w_data["linkedin"]
            except Exception:
                pass

        return {
            "nama_instansi": "",
            "kategori": self.category,
            "kategori_gmaps": kategori_gmaps,
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
            "link_source": "",
            "npsn": npsn,
            "status": "New",
        }
    def _profile_dir(self) -> str:
        """Profil Chrome persisten per pengguna — login berlaku untuk pengguna tersebut."""
        return get_login_profile_dir(self.user_id)

    # ---- Browser login (akun Google utk Maps) ----
    def browser_status(self) -> dict:
        """Cek profil persisten: ada & berisi cookie login."""
        profile = self._profile_dir()
        return {
            "profile": profile,
            "profile_exists": os.path.isdir(profile),
            "has_cookies": is_login_profile_ready(self.user_id),
            "headless": settings.browser_headless,
        }

    def browser_login(self) -> None:
        """Buka browser ke Google Maps agar user login manual sekali.

        Konfigurasi browser (headful/headless, Chrome sistem vs Chromium bundled)
        mengikuti settings — lihat `launch_login_browser_context`. Sesi tersimpan
        di profil persisten; jendela ditutup manual oleh user.
        """
        with sync_playwright() as p:
            context, worker_dir = launch_login_browser_context(p, job_id=self.job_id, user_id=self.user_id)
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
                # Bersihkan worker-clone sementara bila profil utama tadi terkunci
                if worker_dir:
                    try:
                        shutil.rmtree(worker_dir, ignore_errors=True)
                    except Exception:
                        pass

    def run(self) -> list[dict]:
        leads: list[dict] = []
        self.emit_progress(0, 0, f"Membuka Google Maps untuk '{self._build_query()}'")

        with sync_playwright() as p:
            context, worker_dir = launch_login_browser_context(
                p,
                job_id=self.job_id,
                user_id=self.user_id,
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

                            # Validasi batas wilayah / kota (anti-nyasar)
                            if not self._is_city_match(detail.get("alamat", "")):
                                self.emit_progress(len(leads), len(listings), f"Skip (lokasi di luar {self.city}): {name}")
                                processed.add(name)
                                continue

                            # Validasi kesesuaian kategori (anti-salah kategori)
                            if not self._is_category_match(name, detail.get("kategori_gmaps", "")):
                                self.emit_progress(len(leads), len(listings), f"Skip (kategori tidak sesuai): {name}")
                                processed.add(name)
                                continue

                            detail["nama_instansi"] = name
                            detail["source"] = self.source
                            leads.append(detail)
                            processed.add(name)
                            target = min(self.max_results, len(listings))
                            enrich_tags = []
                            if detail.get("telp"):
                                enrich_tags.append("WA/Telp")
                            if detail.get("email"):
                                enrich_tags.append("Email")
                            if detail.get("sosmed"):
                                enrich_tags.append("Medsos")
                            enrich_str = f" + auto-enrich ({', '.join(enrich_tags)})" if enrich_tags else ""
                            self.emit_progress(len(leads), len(listings), f"Berhasil mengekstrak ({len(leads)}/{target}): {name}{enrich_str}")
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
