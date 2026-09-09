import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import Category, City, Lead, Base
from backend.services.code_generator import (
    generate_lead_code,
    generate_category_code,
    generate_city_code,
    clean_code_segment,
)
from backend.services.cleaner import normalize_emails, clean_social_url, clean_lead
from backend.services.dedup_service import _lead_fingerprints


@pytest.fixture()
def db() -> Session:
    """Database SQLite in-memory untuk pengujian generator kode."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def test_code_generator_formatting(db: Session):
    assert clean_code_segment("SMA / SMK Negeri 1") == "SMASMKNEGE"
    assert clean_code_segment("Salatiga") == "SALATIGA"

    # Category code
    c1 = generate_category_code(db, "sekolah")
    assert c1 == "KAT-SEKOLAH-001"
    db.add(Category(name="sekolah", kode=c1))
    db.commit()

    c2 = generate_category_code(db, "sekolah")
    assert c2 == "KAT-SEKOLAH-002"

    # City code
    k1 = generate_city_code(db, "salatiga")
    assert k1 == "K-SALATIGA-001"
    db.add(City(name="salatiga", kode=k1))
    db.commit()

    k2 = generate_city_code(db, "salatiga")
    assert k2 == "K-SALATIGA-002"

    # Lead code
    ld1 = generate_lead_code(db, "sekolah")
    assert ld1 == "LD-SEKOLAH-001"
    db.add(Lead(nama_instansi="SMAN 1", source="gmaps", kode=ld1))
    db.commit()

    ld2 = generate_lead_code(db, "sekolah")
    assert ld2 == "LD-SEKOLAH-002"


def test_normalize_emails_multi():
    raw = "admin@sekolah.sch.id, info@sekolah.sch.id; humas@sekolah.sch.id  admin@sekolah.sch.id"
    res = normalize_emails(raw)
    assert "admin@sekolah.sch.id" in res
    assert "info@sekolah.sch.id" in res
    assert "humas@sekolah.sch.id" in res
    parts = [p.strip() for p in res.split(",") if p.strip()]
    assert len(parts) == 3


def test_clean_social_url():
    assert clean_social_url("https://instagram.com/edtekno.id/?hl=id") == "https://instagram.com/edtekno.id"
    assert clean_social_url("https://www.facebook.com/edtekno/") == "https://www.facebook.com/edtekno"
    assert clean_social_url("@edtekno_official", platform="instagram") == "https://instagram.com/edtekno_official"


def test_clean_lead_extracts_socials():
    raw = {
        "nama_instansi": "SMA Negeri 1 Salatiga",
        "kategori": "sekolah",
        "kota": "salatiga",
        "email": "info@sman1salatiga.sch.id, humas@sman1salatiga.sch.id",
        "instagram": "https://instagram.com/sman1salatiga",
        "facebook": "https://facebook.com/sman1salatigaofficial",
        "linkedin": "https://linkedin.com/school/sman1salatiga",
        "twitter_x": "https://x.com/sman1salatiga",
    }
    cleaned = clean_lead(raw)
    assert cleaned["email"] == "info@sman1salatiga.sch.id, humas@sman1salatiga.sch.id"
    assert cleaned["instagram"] == "https://instagram.com/sman1salatiga"
    assert cleaned["facebook"] == "https://facebook.com/sman1salatigaofficial"
    assert cleaned["linkedin"] == "https://linkedin.com/school/sman1salatiga"
    assert cleaned["twitter_x"] == "https://x.com/sman1salatiga"


def test_dedup_multi_email_fingerprints():
    lead_obj = Lead(
        nama_instansi="Test Company",
        source="gmaps",
        email="contact@test.com, sales@test.com",
        instagram="https://instagram.com/testcompany",
        facebook="https://facebook.com/testcompany",
        website="https://test.com",
        telp="62812345678",
    )
    fps = _lead_fingerprints(lead_obj)

    # Both emails should be separate fingerprints
    assert ("email", "contact@test.com") in fps
    assert ("email", "sales@test.com") in fps
    assert ("instagram", "testcompany") in fps
    assert ("facebook", "testcompany") in fps


def test_clean_social_url_tiktok():
    assert clean_social_url("https://www.tiktok.com/@smkn2salatiga?lang=id") == "https://www.tiktok.com/@smkn2salatiga"
    assert clean_social_url("@smkn2salatiga", platform="tiktok") == "https://tiktok.com/@smkn2salatiga"


def test_clean_lead_auto_relocates_misplaced_social():
    raw = {
        "nama_instansi": "SMK PGRI 1 Salatiga",
        "sosmed": "https://www.instagram.com/smkpgri1salatiga.official",
        "instagram": "",
    }
    cleaned = clean_lead(raw)
    assert cleaned["instagram"] == "https://www.instagram.com/smkpgri1salatiga.official"
    assert cleaned["sosmed"] == ""

    raw_tiktok = {
        "nama_instansi": "SMK PGRI 1 Salatiga",
        "sosmed": "https://www.tiktok.com/@smkpgri1salatiga",
        "tiktok": "",
    }
    cleaned_tiktok = clean_lead(raw_tiktok)
    assert cleaned_tiktok["tiktok"] == "https://www.tiktok.com/@smkpgri1salatiga"
    assert cleaned_tiktok["sosmed"] == ""


def test_dapodik_does_not_extract_operator_as_kepsek():
    from backend.services.scrapers.dapodik import DapodikScraper
    scraper = DapodikScraper()
    # Snippet dari referensi.data.kemendikdasmen.go.id
    html = """
    <tr><td>Nama</td><td>SMK NEGERI 2 SALATIGA</td></tr>
    <tr><td>Email</td><td>info@smkn2salatiga.sch.id</td></tr>
    <tr><td>Operator</td><td>Febri Ayuk Rikmawati</td></tr>
    """
    res = DapodikScraper._parse_detail_html(html)
    assert res["nama_kepsek"] == ""  # Operator TIDAK boleh masuk sebagai nama_kepsek!


