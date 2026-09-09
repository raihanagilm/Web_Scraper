"""Cleaner: normalisasi & validasi data lead sebelum masuk DB."""
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


def clean_social_url(url: str, platform: str = "") -> str:
    """Bersihkan query string tracking & trailing slash dari URL media sosial."""
    if not url:
        return ""
    u = url.strip()
    if u.startswith("@") and platform:
        handle = u.lstrip("@").strip()
        if platform == "instagram":
            return f"https://instagram.com/{handle}"
        elif platform == "facebook":
            return f"https://facebook.com/{handle}"
        elif platform == "twitter" or platform == "twitter_x":
            return f"https://x.com/{handle}"
        elif platform == "tiktok":
            return f"https://tiktok.com/@{handle}"
    u = u.split("?")[0].rstrip(".,;)'\"/")
    return u


# Domain CDN/asset (bukan website bisnis) — jangan disimpan sebagai website
JUNK_WEBSITE_DOMAINS = (
    "ggpht.com",              # CDN gambar Google (ikon aplikasi/foto profil)
    "googleusercontent.com",  # CDN konten Google
    "gstatic.com",            # aset statis Google
)


def is_junk_website(url: str) -> bool:
    """True jika URL adalah CDN/aset (bukan website bisnis yang valid)."""
    if not url:
        return False
    d = normalize_website(url)
    return any(dom in d for dom in JUNK_WEBSITE_DOMAINS)


def clean_lead(raw: dict) -> dict:
    """Bersihkan 1 raw lead dict dari scraper."""
    cleaned = dict(raw)
    cleaned["telp"] = normalize_phone(cleaned.get("telp", ""))
    cleaned["email"] = normalize_emails(cleaned.get("email", ""))
    website = cleaned.get("website", "").strip()
    # CDN Google (mis. lh3.ggpht.com) bukan website bisnis — kosongkan
    cleaned["website"] = "" if is_junk_website(website) else website
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

    # Auto-sortir: jika sosmed berisi link Instagram/FB/LI/X/TikTok, pindahkan ke kolom masing-masing
    raw_sos = clean_social_url(cleaned.get("sosmed", ""))
    if raw_sos:
        s_low = raw_sos.lower()
        if "instagram.com" in s_low:
            if not cleaned["instagram"]:
                cleaned["instagram"] = raw_sos
            raw_sos = ""
        elif "facebook.com" in s_low or "fb.com" in s_low:
            if not cleaned["facebook"]:
                cleaned["facebook"] = raw_sos
            raw_sos = ""
        elif "linkedin.com" in s_low:
            if not cleaned["linkedin"]:
                cleaned["linkedin"] = raw_sos
            raw_sos = ""
        elif "twitter.com" in s_low or "x.com" in s_low:
            if not cleaned["twitter_x"]:
                cleaned["twitter_x"] = raw_sos
            raw_sos = ""
        elif "tiktok.com" in s_low:
            if not cleaned["tiktok"]:
                cleaned["tiktok"] = raw_sos
            raw_sos = ""

    cleaned["sosmed"] = raw_sos
    return cleaned

