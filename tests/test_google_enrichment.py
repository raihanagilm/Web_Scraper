"""Unit test untuk GoogleScraper dan alur enrichment Google / Web."""
import pytest
from app.Services.scrapers.google import GoogleScraper
from app.Services.enrichment_service import ENRICHMENT_FIELDS
from app.Services.job_manager import ScraperRegistry
from app.Services.scrapers.gmaps import get_enrichment_sources


def test_google_registered_in_scraper_registry():
    """Pastikan 'google' terdaftar di ScraperRegistry."""
    sources = ScraperRegistry.list_sources()
    assert "google" in sources
    cls = ScraperRegistry.get_class("google")
    assert cls is GoogleScraper


def test_google_in_enrichment_fields():
    """Pastikan fields enrichment google mencakup telp, email, website, sosmed."""
    assert "google" in ENRICHMENT_FIELDS
    fields = ENRICHMENT_FIELDS["google"]
    for expected in ["telp", "email", "website", "sosmed"]:
        assert expected in fields


def test_get_enrichment_sources_defaults_to_google():
    """Kategori umum (seperti rumah sakit, hotel, kafe) harus merekomendasikan google."""
    assert "google" in get_enrichment_sources("rumah sakit")
    assert "google" in get_enrichment_sources("hotel")
    assert "google" in get_enrichment_sources("klinik")
    assert "google" in get_enrichment_sources("kategori_acak_lainnya")


def test_extract_from_text_method():
    """Pastikan method _extract_from_text mampu mengekstrak telp, email, dan instagram dari snippet teks."""
    scraper = GoogleScraper(category="kesehatan", city="salatiga", targets=["RS Ken Saras"])
    sample_text = (
        "Hubungi RS Ken Saras di (0298) 522-888 atau WhatsApp 0812-3456-7890. "
        "Email resmi: info@rskensaras.com. Kunjungi https://www.instagram.com/rskensaras/ untuk update."
    )
    telp, email, ig = scraper._extract_from_text(sample_text)
    assert telp != ""
    assert email == "info@rskensaras.com"
    assert "instagram.com/rskensaras" in ig


def test_website_enricher_html_extraction():
    """Pastikan WebsiteContactEnricher mampu mengekstrak WhatsApp, email, dan seluruh medsos dari HTML."""
    from app.Services.scrapers.website_enricher import WebsiteContactEnricher
    enricher = WebsiteContactEnricher()
    sample_html = """
    <html>
      <head><title>Profil Bisnis</title></head>
      <body>
        <header>
          <a href="mailto:official@perusahaan.co.id">Email Kami</a>
          <a href="https://wa.me/6285712345678?text=Halo">Chat WhatsApp</a>
        </header>
        <footer>
          <a href="https://www.instagram.com/bisnis_indonesia/">Instagram</a>
          <a href="https://www.facebook.com/bisnisindonesia.page/">Facebook</a>
          <a href="https://www.tiktok.com/@bisnis_tiktok">TikTok</a>
          <a href="https://x.com/bisnis_official">Twitter X</a>
        </footer>
      </body>
    </html>
    """
    res = enricher._extract_from_html(sample_html, "https://perusahaan.co.id")
    assert res["telp"] == "6285712345678"
    assert res["email"] == "official@perusahaan.co.id"
    assert "instagram.com/bisnis_indonesia" in res["instagram"]
    assert "facebook.com/bisnisindonesia.page" in res["facebook"]
    assert "tiktok.com/@bisnis_tiktok" in res["tiktok"]
    assert "x.com/bisnis_official" in res["twitter_x"]


