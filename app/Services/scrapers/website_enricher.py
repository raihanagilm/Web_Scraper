"""Website Contact & Social Media Harvester.

Mengambil data kontak langsung dari website resmi bisnis/instansi:
- WhatsApp (wa.me, api.whatsapp.com, regex nomor 08/628)
- Media sosial (Instagram, TikTok, Facebook, Twitter/X, LinkedIn)
- Email resmi (mailto, Cloudflare deobfuscation, text obfuscation)

Direct HTTP (httpx) sangat cepat (<0.5 detik) dan aman dari blokir bot.
"""
import re
import urllib.parse
from bs4 import BeautifulSoup
import httpx

from app.Services.cleaner import clean_social_url, normalize_phone, is_valid_website

WA_URL_RE = re.compile(r'(?:wa\.me/|api\.whatsapp\.com/send\?(?:[^&]*&)*phone=)(\+?62\d+|08\d+)', re.IGNORECASE)
PHONE_RE = re.compile(r'(?:\+62|62|08)[\s\-\.]?\d{2,4}[\s\-\.]?\d{2,4}[\s\-\.]?\d{2,6}')
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

EXCLUDED_EMAIL_DOMAINS = {
    "example.com", "domain.com", "sentry.io", "w3.org", "schema.org", "cloudflare.com",
    "wordpress.org", "gravatar.com", "wixpress.com", "github.com",
}
CONTACT_PAGE_KEYWORDS = ["kontak", "contact", "hubungi", "tentang", "about", "profil"]


def decode_cloudflare_email(cf_hex: str) -> str:
    """Dekode email yang dilindungi proteksi Cloudflare (data-cfemail)."""
    try:
        cf_hex = cf_hex.strip()
        if len(cf_hex) < 4:
            return ""
        k = int(cf_hex[:2], 16)
        return "".join(chr(int(cf_hex[i:i + 2], 16) ^ k) for i in range(2, len(cf_hex), 2))
    except Exception:
        return ""


class WebsiteContactEnricher:
    """Harvester kontak dan media sosial dari website resmi."""

    def __init__(self, timeout: float = 7.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def _extract_from_html(self, html: str, base_url: str) -> dict:
        result = {
            "telp": "", "email": "", "instagram": "", "facebook": "",
            "tiktok": "", "twitter_x": "", "linkedin": "", "subpages": [],
        }
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return result

        found_emails: list[str] = []

        # 1. Dekode proteksi email Cloudflare (__cf_email__ / email-protection)
        for el in soup.find_all(attrs={"data-cfemail": True}):
            dec = decode_cloudflare_email(el["data-cfemail"])
            if dec and "@" in dec and dec not in found_emails:
                found_emails.append(dec.lower())

        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href:
                continue

            # Cloudflare email protection link
            if "/cdn-cgi/l/email-protection#" in href:
                cf_code = href.split("#")[-1]
                dec = decode_cloudflare_email(cf_code)
                if dec and "@" in dec and dec not in found_emails:
                    found_emails.append(dec.lower())

            # WhatsApp direct
            if "wa.me/" in href.lower() or "api.whatsapp.com" in href.lower() or href.startswith("whatsapp:"):
                m_wa = WA_URL_RE.search(href)
                if m_wa and not result["telp"]:
                    result["telp"] = normalize_phone(m_wa.group(1))

            # tel:
            if href.startswith("tel:") and not result["telp"]:
                p_norm = normalize_phone(href[4:].split("?")[0].strip())
                if p_norm and len(p_norm) >= 9:
                    result["telp"] = p_norm

            # mailto:
            if href.startswith("mailto:"):
                e_raw = href[7:].split("?")[0].strip().lower()
                dom = e_raw.split("@")[-1] if "@" in e_raw else ""
                if dom and dom not in EXCLUDED_EMAIL_DOMAINS and e_raw not in found_emails:
                    found_emails.append(e_raw)

            # Media sosial
            h_low = href.lower()
            if not result["instagram"] and "instagram.com" in h_low:
                c = clean_social_url(href, "instagram")
                if c: result["instagram"] = c
            if not result["facebook"] and ("facebook.com" in h_low or "fb.com" in h_low):
                c = clean_social_url(href, "facebook")
                if c: result["facebook"] = c
            if not result["tiktok"] and "tiktok.com" in h_low:
                c = clean_social_url(href, "tiktok")
                if c: result["tiktok"] = c
            if not result["twitter_x"] and ("twitter.com" in h_low or "x.com" in h_low):
                c = clean_social_url(href, "twitter_x")
                if c: result["twitter_x"] = c
            if not result["linkedin"] and "linkedin.com" in h_low:
                c = clean_social_url(href, "linkedin")
                if c: result["linkedin"] = c

            # Kumpulkan link subpage kontak
            if len(result["subpages"]) < 2:
                for kw in CONTACT_PAGE_KEYWORDS:
                    if kw in h_low and not h_low.startswith(("mailto:", "tel:", "javascript:")):
                        full_sub = urllib.parse.urljoin(base_url, href)
                        if full_sub not in result["subpages"] and full_sub != base_url:
                            result["subpages"].append(full_sub)
                        break

        # 2. Regex cadangan pada teks (termasuk email terobfuskasi seperti 'user [at] domain.com')
        text = soup.get_text()
        if not result["telp"]:
            for p in PHONE_RE.findall(text):
                p_clean = normalize_phone(p)
                if p_clean and len(p_clean) >= 10:
                    result["telp"] = p_clean
                    break

        if not found_emails:
            clean_text = re.sub(r'[\(\[\{]\s*(?:at|@)\s*[\)\]\}]', '@', text, flags=re.IGNORECASE)
            clean_text = re.sub(r'[\(\[\{]\s*(?:dot|\.)\s*[\)\]\}]', '.', clean_text, flags=re.IGNORECASE)
            for e in EMAIL_RE.findall(clean_text):
                e_clean = e.lower().strip()
                dom = e_clean.split("@")[-1]
                if dom not in EXCLUDED_EMAIL_DOMAINS and not dom.endswith((".png", ".jpg", ".jpeg", ".gif")):
                    if e_clean not in found_emails:
                        found_emails.append(e_clean)

        if found_emails:
            result["email"] = ", ".join(found_emails[:3])

        return result

    def enrich(self, url: str) -> dict:
        """Kunjungi website dan ambil kontak & media sosial."""
        contacts = {
            "telp": "", "email": "", "instagram": "", "facebook": "",
            "tiktok": "", "twitter_x": "", "linkedin": "", "sosmed": "",
        }
        if not url or not is_valid_website(url):
            return contacts

        target_url = url if url.startswith("http") else f"https://{url}"
        try:
            with httpx.Client(
                headers=self.headers, timeout=self.timeout,
                follow_redirects=True, verify=False,
            ) as client:
                resp = client.get(target_url)
                if resp.status_code != 200:
                    return contacts

                home_data = self._extract_from_html(resp.text, str(resp.url))
                for k in ["telp", "email", "instagram", "facebook", "tiktok", "twitter_x", "linkedin"]:
                    if home_data.get(k):
                        contacts[k] = home_data[k]

                subpages = home_data.get("subpages", [])
                if subpages and (not contacts["telp"] or not contacts["email"] or not contacts["instagram"]):
                    try:
                        sub_resp = client.get(subpages[0])
                        if sub_resp.status_code == 200:
                            sub_data = self._extract_from_html(sub_resp.text, str(sub_resp.url))
                            for k in ["telp", "email", "instagram", "facebook", "tiktok", "twitter_x", "linkedin"]:
                                if not contacts[k] and sub_data.get(k):
                                    contacts[k] = sub_data[k]
                    except Exception:
                        pass
        except Exception:
            pass

        contacts["sosmed"] = (
            contacts["instagram"] or contacts["tiktok"] or contacts["facebook"]
            or contacts["twitter_x"] or contacts["linkedin"]
        )
        return contacts
