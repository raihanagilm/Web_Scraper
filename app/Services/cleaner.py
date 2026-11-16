"""Cleaner: normalisasi & validasi data lead sebelum masuk DB."""
import urllib.parse
import re


def normalize_phone(raw: str) -> str:
    """Standarisasi nomor telepon ke format 628xxxxxxxx."""
    if not raw:
        return ""
    # Hapus selain digit dan +
    phone = re.sub(r"[^\d+]", "", raw.strip())
    if not phone:
        return ""
    # Hilangkan + di depan
    phone = phone.lstrip("+")
    # 08xxx -> 628xxx
    if phone.startswith("0"):
        phone = "62" + phone[1:]
    # 62 8xxx (tanpa nol) sudah benar
    elif phone.startswith("62") and not phone.startswith("628"):
        # 62 diikuti non-8, biarkan (kemungkinan tetap valid)
        pass
    # 8xxx tanpa 0/62
    elif phone.startswith("8"):
        phone = "62" + phone
    return phone


def normalize_name(name: str) -> str:
    """Bersihkan nama untuk perbandingan fuzzy."""
    if not name:
        return ""
    n = name.lower().strip()
    # Hapus tanda baca berlebih
    n = re.sub(r"[^\w\s]", " ", n)
    # Hapus kata umum perusahaan
    for token in ["pt", "cv", "tbk", "persero", "yayasan", "madrasah"]:
        n = re.sub(rf"\b{token}\b", " ", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalize_website(url: str) -> str:
    """Ambil domain saja untuk perbandingan."""
    if not url:
        return ""
    u = url.lower().strip()
    u = re.sub(r"^https?://(www\.)?", "", u)
    u = u.rstrip("/")
    return u.split("/")[0]  # hanya domain


def is_valid_email(email: str) -> bool:
    if not email:
        return False
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email.strip()))


def normalize_emails(raw: str) -> str:
    """Bersihkan & pisahkan multi-email (koma/titik koma/baris baru), buang duplikat."""
    if not raw:
        return ""
    parts = re.split(r"[\s,;\n\r]+", str(raw).strip())
    valid_emails = []
    seen = set()
    for p in parts:
        clean_p = p.strip().lower()
        if is_valid_email(clean_p) and clean_p not in seen:
            seen.add(clean_p)
            valid_emails.append(clean_p)
    return ", ".join(valid_emails)


# Path sistem & umum yang bukan identitas/akun profil pengguna
GENERIC_SOCIAL_BLOCKED_PATHS = {
    "", "home", "home.php", "login", "login.php", "signup", "register",
    "about", "help", "privacy", "terms", "legal", "policies", "contact",
    "search", "explore", "settings", "feedback", "notifications",
    "sharer", "share", "sharer.php", "dialog", "recover", "watch", "marketplace",
    "gaming", "events", "groups", "pages", "people", "profile", "profile.php",
    "business", "ads", "fundraisers",
    "p", "reel", "reels", "stories", "direct", "tv", "developer", "accounts",
    "foryou", "live", "tag", "music", "upload", "following",
    "jobs", "feed", "company", "school", "in", "pub", "sharing", "learning",
    "intent", "i", "hashtag", "tos", "compose", "messages",
    "lazadaid", "wordpress",
}


def clean_social_url(url: str, platform: str = "") -> str:
    """Bersihkan query string tracking & trailing slash dari URL media sosial.
    Menolak link yang tidak memiliki identitas profil (mis. hanya instagram.com/ atau facebook.com/profile.php/).
    """
    if not url:
        return ""
    u = str(url).strip()
    if not u:
        return ""

    # Format handle @user
    if u.startswith("@"):
        handle = u.lstrip("@").strip().rstrip("/.,;)'\"")
        if not handle or len(handle) < 2 or handle.lower() in GENERIC_SOCIAL_BLOCKED_PATHS:
            return ""
        if platform == "instagram":
            return f"https://instagram.com/{handle}"
        elif platform == "facebook":
            return f"https://facebook.com/{handle}"
        elif platform in ("twitter", "twitter_x"):
            return f"https://x.com/{handle}"
        elif platform == "tiktok":
            return f"https://tiktok.com/@{handle}"
        elif platform == "linkedin":
            return f"https://linkedin.com/in/{handle}"
        return ""

    if not u.startswith(("http://", "https://")):
        u = "https://" + u

    try:
        parsed = urllib.parse.urlsplit(u)
    except Exception:
        return ""

    host = (parsed.netloc or "").lower().split(":")[0]
    while host.startswith(("www.", "m.", "mobile.", "web.", "id-id.")):
        host = re.sub(r"^(www\.|m\.|mobile\.|web\.|id-id\.)", "", host)

    # Tangani wrapper redirect (seperti l.instagram.com/?u=...)
    if host.startswith("l.") and "instagram.com" in host:
        qs = urllib.parse.parse_qs(parsed.query)
        if "u" in qs and qs["u"]:
            return clean_social_url(qs["u"][0], platform)

    path_raw = (parsed.path or "").strip()
    path_segments = [s.strip() for s in path_raw.split("/") if s.strip()]

    # Tanpa segment path = hanya homepage generic (mis. www.instagram.com/) -> INVALID
    if not path_segments:
        return ""

    first_seg = path_segments[0].rstrip(".,;)'\"")
    first_seg_lower = first_seg.lower()

    if not platform:
        if "instagram.com" in host or "instagr.am" in host:
            platform = "instagram"
        elif "facebook.com" in host or "fb.com" in host or "fb.watch" in host:
            platform = "facebook"
        elif "tiktok.com" in host:
            platform = "tiktok"
        elif "linkedin.com" in host:
            platform = "linkedin"
        elif "twitter.com" in host or "x.com" in host:
            platform = "twitter_x"

    # Selalu gunakan HTTPS untuk URL media sosial
    scheme = "https"
    orig_netloc = parsed.netloc

    if platform == "instagram":
        if first_seg_lower in GENERIC_SOCIAL_BLOCKED_PATHS or len(first_seg) < 2:
            return ""
        if not re.match(r"^[A-Za-z0-9_.]{2,30}$", first_seg):
            return ""
        return f"{scheme}://{orig_netloc}/{first_seg}"

    elif platform == "facebook":
        if first_seg_lower == "profile.php":
            qs = urllib.parse.parse_qs(parsed.query)
            if "id" in qs and qs["id"] and qs["id"][0].isdigit():
                return f"{scheme}://{orig_netloc}/profile.php?id={qs['id'][0]}"
            return ""
        if first_seg_lower in ("people", "pages", "groups"):
            if len(path_segments) < 2:
                return ""
            sub_path = "/".join(path_segments).rstrip(".,;)'\"")
            return f"{scheme}://{orig_netloc}/{sub_path}"
        if first_seg_lower in GENERIC_SOCIAL_BLOCKED_PATHS or len(first_seg) < 2:
            return ""
        return f"{scheme}://{orig_netloc}/{first_seg}"

    elif platform == "tiktok":
        handle_clean = first_seg[1:] if first_seg.startswith("@") else first_seg
        if not handle_clean or handle_clean.lower() in GENERIC_SOCIAL_BLOCKED_PATHS or len(handle_clean) < 2:
            return ""
        return f"{scheme}://{orig_netloc}/@{handle_clean}"

    elif platform == "linkedin":
        if first_seg_lower in ("company", "school", "in", "pub"):
            if len(path_segments) < 2:
                return ""
            slug = path_segments[1].rstrip(".,;)'\"")
            if not slug or slug.lower() in GENERIC_SOCIAL_BLOCKED_PATHS or len(slug) < 2:
                return ""
            return f"{scheme}://{orig_netloc}/{first_seg_lower}/{slug}"
        if first_seg_lower in GENERIC_SOCIAL_BLOCKED_PATHS or len(first_seg) < 2:
            return ""
        return f"{scheme}://{orig_netloc}/in/{first_seg}"

    elif platform in ("twitter", "twitter_x"):
        tw_handle = first_seg.lstrip("@")
        if not tw_handle or tw_handle.lower() in GENERIC_SOCIAL_BLOCKED_PATHS or len(tw_handle) < 2:
            return ""
        return f"{scheme}://{orig_netloc}/{tw_handle}"

    else:
        if first_seg_lower in GENERIC_SOCIAL_BLOCKED_PATHS or len(first_seg) < 2:
            return ""
        cleaned_path = "/".join(path_segments).rstrip(".,;)'\"")
        return f"{scheme}://{orig_netloc}/{cleaned_path}"


# Domain CDN/asset (bukan website bisnis) — jangan disimpan sebagai website
JUNK_WEBSITE_DOMAINS = (
    "ggpht.com",              # CDN gambar Google (ikon aplikasi/foto profil)
    "googleusercontent.com",  # CDN konten Google
    "gstatic.com",            # aset statis Google
    "w3.org",
    "schema.org",
)


def is_junk_website(url: str) -> bool:
    """True jika URL adalah CDN/aset (bukan website bisnis yang valid)."""
    if not url:
        return False
    d = normalize_website(url)
    return any(dom in d for dom in JUNK_WEBSITE_DOMAINS)


def is_valid_website(url: str) -> bool:
    """True jika URL website valid, bukan generic domain / cdn / medsos / search engine."""
    if not url:
        return False
    u = str(url).strip()
    if not u:
        return False
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        parsed = urllib.parse.urlsplit(u)
    except Exception:
        return False
    host = (parsed.netloc or "").lower().split(":")[0]
    while host.startswith(("www.", "m.")):
        host = host[4:] if host.startswith("www.") else host[2:]
    if not host or "." not in host or len(host) < 4:
        return False
    if any(dom in host for dom in JUNK_WEBSITE_DOMAINS):
        return False
    # Bukan search engine umum
    if host in ("google.com", "google.co.id", "bing.com", "duckduckgo.com", "yahoo.com"):
        return False
    # Bukan domain medsos murni tanpa sub-page/profil
    if host in ("instagram.com", "facebook.com", "fb.com", "tiktok.com", "linkedin.com", "twitter.com", "x.com"):
        return False
    # Domain bio-link / aggregator tanpa slug/halaman profil
    if host in ("linktr.ee", "campsite.bio", "bio.link", "beacons.ai", "bit.ly", "lynk.id", "s.id", "heylink.me"):
        path_segments = [s for s in (parsed.path or "").strip().split("/") if s.strip()]
        if not path_segments or len(path_segments[0]) < 2:
            return False
    return True


def clean_lead(raw: dict) -> dict:
    """Bersihkan 1 raw lead dict dari scraper."""
    cleaned = dict(raw)
    cleaned["telp"] = normalize_phone(cleaned.get("telp", ""))
    cleaned["email"] = normalize_emails(cleaned.get("email", ""))
    cleaned["nama_instansi"] = (cleaned.get("nama_instansi") or "").strip()
    cleaned["kategori"] = (cleaned.get("kategori") or "").strip()
    cleaned["kota"] = (cleaned.get("kota") or "").strip()
    cleaned["source"] = cleaned.get("source", "gmaps")
    cleaned.setdefault("status", "New")

    # Medsos spesifik
    cleaned["instagram"] = clean_social_url(cleaned.get("instagram", ""), "instagram")
    cleaned["facebook"] = clean_social_url(cleaned.get("facebook", ""), "facebook")
    cleaned["linkedin"] = clean_social_url(cleaned.get("linkedin", ""), "linkedin")
    cleaned["twitter_x"] = clean_social_url(cleaned.get("twitter_x", ""), "twitter_x")
    cleaned["tiktok"] = clean_social_url(cleaned.get("tiktok", ""), "tiktok")

    # Auto-sortir website: jika website sebenarnya berisi link medsos, pindahkan ke kolom medsos terkait
    website = (cleaned.get("website") or "").strip()
    if website:
        w_low = website.lower()
        if "instagram.com" in w_low or "instagr.am" in w_low:
            cleaned_ig = clean_social_url(website, "instagram")
            if cleaned_ig and not cleaned.get("instagram"):
                cleaned["instagram"] = cleaned_ig
            website = ""
        elif "facebook.com" in w_low or "fb.com" in w_low:
            cleaned_fb = clean_social_url(website, "facebook")
            if cleaned_fb and not cleaned.get("facebook"):
                cleaned["facebook"] = cleaned_fb
            website = ""
        elif "tiktok.com" in w_low:
            cleaned_tt = clean_social_url(website, "tiktok")
            if cleaned_tt and not cleaned.get("tiktok"):
                cleaned["tiktok"] = cleaned_tt
            website = ""
        elif "linkedin.com" in w_low:
            cleaned_li = clean_social_url(website, "linkedin")
            if cleaned_li and not cleaned.get("linkedin"):
                cleaned["linkedin"] = cleaned_li
            website = ""
        elif "twitter.com" in w_low or "x.com" in w_low:
            cleaned_tw = clean_social_url(website, "twitter_x")
            if cleaned_tw and not cleaned.get("twitter_x"):
                cleaned["twitter_x"] = cleaned_tw
            website = ""
        elif is_junk_website(website) or not is_valid_website(website):
            website = ""

    cleaned["website"] = website

    # Auto-sortir sosmed: jika sosmed berisi link Instagram/FB/LI/X/TikTok, pindahkan ke kolom masing-masing
    raw_sos = (cleaned.get("sosmed") or "").strip()
    if raw_sos:
        s_low = raw_sos.lower()
        if "instagram.com" in s_low or "instagr.am" in s_low:
            cleaned_ig = clean_social_url(raw_sos, "instagram")
            if cleaned_ig and not cleaned["instagram"]:
                cleaned["instagram"] = cleaned_ig
            raw_sos = ""
        elif "facebook.com" in s_low or "fb.com" in s_low:
            cleaned_fb = clean_social_url(raw_sos, "facebook")
            if cleaned_fb and not cleaned["facebook"]:
                cleaned["facebook"] = cleaned_fb
            raw_sos = ""
        elif "linkedin.com" in s_low:
            cleaned_li = clean_social_url(raw_sos, "linkedin")
            if cleaned_li and not cleaned["linkedin"]:
                cleaned["linkedin"] = cleaned_li
            raw_sos = ""
        elif "twitter.com" in s_low or "x.com" in s_low:
            cleaned_tw = clean_social_url(raw_sos, "twitter_x")
            if cleaned_tw and not cleaned["twitter_x"]:
                cleaned["twitter_x"] = cleaned_tw
            raw_sos = ""
        elif "tiktok.com" in s_low:
            cleaned_tt = clean_social_url(raw_sos, "tiktok")
            if cleaned_tt and not cleaned["tiktok"]:
                cleaned["tiktok"] = cleaned_tt
            raw_sos = ""
        else:
            raw_sos = clean_social_url(raw_sos)

    cleaned["sosmed"] = raw_sos
    return cleaned

