"""Skrip pembersih data lead: membersihkan semua link medsos generic (tanpa username/handle seperti profile.php, groups, dll) dan merelokasi website yang berisi link medsos."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.models.base import SessionLocal
from backend.models.lead import Lead
from backend.services.cleaner import clean_social_url, is_valid_website, is_junk_website


def clean_generic_links():
    print("Memulai pembersihan link generic dan tidak valid di database...")
    db = SessionLocal()
    try:
        leads = db.query(Lead).all()
        print(f"Total leads ditemukan: {len(leads)}")
        cleaned_leads_count = 0
        cleared_fields_count = 0

        for l in leads:
            changed = False

            # 1. Bersihkan Medsos
            for field, platform in [
                ("instagram", "instagram"),
                ("facebook", "facebook"),
                ("linkedin", "linkedin"),
                ("twitter_x", "twitter_x"),
                ("tiktok", "tiktok"),
            ]:
                val = getattr(l, field, "") or ""
                if val:
                    cleaned_val = clean_social_url(val, platform)
                    if cleaned_val != val:
                        setattr(l, field, cleaned_val)
                        changed = True
                        cleared_fields_count += 1
                        print(f"  [LEAD {l.id} - {l.nama_instansi}] {field}: '{val}' -> '{cleaned_val}'")

            # 2. Periksa website: jika berisi link medsos, pindahkan ke field yang tepat
            web_val = (l.website or "").strip()
            if web_val:
                w_low = web_val.lower()
                if "instagram.com" in w_low or "instagr.am" in w_low:
                    c_ig = clean_social_url(web_val, "instagram")
                    if c_ig and not l.instagram:
                        l.instagram = c_ig
                    l.website = ""
                    changed = True
                    cleared_fields_count += 1
                    print(f"  [LEAD {l.id} - {l.nama_instansi}] website -> instagram: '{web_val}'")
                elif "facebook.com" in w_low or "fb.com" in w_low:
                    c_fb = clean_social_url(web_val, "facebook")
                    if c_fb and not l.facebook:
                        l.facebook = c_fb
                    l.website = ""
                    changed = True
                    cleared_fields_count += 1
                    print(f"  [LEAD {l.id} - {l.nama_instansi}] website -> facebook: '{web_val}'")
                elif "tiktok.com" in w_low:
                    c_tt = clean_social_url(web_val, "tiktok")
                    if c_tt and not l.tiktok:
                        l.tiktok = c_tt
                    l.website = ""
                    changed = True
                    cleared_fields_count += 1
                    print(f"  [LEAD {l.id} - {l.nama_instansi}] website -> tiktok: '{web_val}'")
                elif "linkedin.com" in w_low:
                    c_li = clean_social_url(web_val, "linkedin")
                    if c_li and not l.linkedin:
                        l.linkedin = c_li
                    l.website = ""
                    changed = True
                    cleared_fields_count += 1
                    print(f"  [LEAD {l.id} - {l.nama_instansi}] website -> linkedin: '{web_val}'")
                elif "twitter.com" in w_low or "x.com" in w_low:
                    c_tw = clean_social_url(web_val, "twitter_x")
                    if c_tw and not l.twitter_x:
                        l.twitter_x = c_tw
                    l.website = ""
                    changed = True
                    cleared_fields_count += 1
                    print(f"  [LEAD {l.id} - {l.nama_instansi}] website -> twitter_x: '{web_val}'")
                elif is_junk_website(web_val) or not is_valid_website(web_val):
                    l.website = ""
                    changed = True
                    cleared_fields_count += 1
                    print(f"  [LEAD {l.id} - {l.nama_instansi}] website junk/invalid dibersihkan: '{web_val}'")

            # 3. Periksa sosmed string bebas
            sos_val = (l.sosmed or "").strip()
            if sos_val:
                s_low = sos_val.lower()
                if "instagram.com" in s_low or "instagr.am" in s_low:
                    c_ig = clean_social_url(sos_val, "instagram")
                    if c_ig and not l.instagram:
                        l.instagram = c_ig
                    l.sosmed = ""
                    changed = True
                    cleared_fields_count += 1
                elif "facebook.com" in s_low or "fb.com" in s_low:
                    c_fb = clean_social_url(sos_val, "facebook")
                    if c_fb and not l.facebook:
                        l.facebook = c_fb
                    l.sosmed = ""
                    changed = True
                    cleared_fields_count += 1
                elif "tiktok.com" in s_low:
                    c_tt = clean_social_url(sos_val, "tiktok")
                    if c_tt and not l.tiktok:
                        l.tiktok = c_tt
                    l.sosmed = ""
                    changed = True
                    cleared_fields_count += 1
                elif "linkedin.com" in s_low:
                    c_li = clean_social_url(sos_val, "linkedin")
                    if c_li and not l.linkedin:
                        l.linkedin = c_li
                    l.sosmed = ""
                    changed = True
                    cleared_fields_count += 1
                elif "twitter.com" in s_low or "x.com" in s_low:
                    c_tw = clean_social_url(sos_val, "twitter_x")
                    if c_tw and not l.twitter_x:
                        l.twitter_x = c_tw
                    l.sosmed = ""
                    changed = True
                    cleared_fields_count += 1
                else:
                    c_gen = clean_social_url(sos_val)
                    if c_gen != sos_val:
                        l.sosmed = c_gen
                        changed = True
                        cleared_fields_count += 1

            if changed:
                cleaned_leads_count += 1
                db.add(l)

        db.commit()
        print(f"\n[SUKSES] Pembersihan selesai!")
        print(f"- Total field yang dibersihkan/direlokasi: {cleared_fields_count}")
        print(f"- Total leads yang diperbarui: {cleaned_leads_count}")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Gagal menjalankan pembersihan: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    clean_generic_links()
