"""Unit test untuk GoogleScraper dan alur enrichment Google / Web."""
import pytest
from backend.services.scrapers.google import GoogleScraper
from backend.services.enrichment_service import ENRICHMENT_FIELDS
from backend.services.job_manager import ScraperRegistry
from backend.services.scrapers.gmaps import get_enrichment_sources


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

