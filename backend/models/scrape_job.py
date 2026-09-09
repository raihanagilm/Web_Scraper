"""Model ScrapeJob — riwayat/audit job scraping.

Kolom `category` & `city` sengaja denormalisasi (snapshot nilai saat job berjalan).
"""
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import backref, relationship

from backend.models.base import Base


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(String(36), primary_key=True)  # UUID string
    seed_job_id = Column(String(36), ForeignKey("scrape_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    source = Column(String(50), nullable=False)
    category = Column(String(100), default="")
    city = Column(String(100), default="")
    max_results = Column(Integer, default=100)
    status = Column(Enum("pending", "running", "completed", "cancelled", "error", name="job_status_enum"), default="pending")
    progress = Column(Integer, default=0)
    total_found = Column(Integer, default=0)
    # Angka real data yang terambil/terpindah ke leads (dibedinangkan dari total_found
    # yang suka menyesatkan: e.g. 120 ditemukan tapi cuma 1 terambil karena upsert/dedup).
    # Seed: items_created + items_updated = lead yang tersimpan; Enrichment: items_created = matched.
    items_created = Column(Integer, default=0)
    items_updated = Column(Integer, default=0)
    log = Column(Text, default="")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    enrichment_jobs = relationship(
        "ScrapeJob",
        backref=backref("seed_job", remote_side=[id]),
        cascade="all, delete-orphan",
        passive_deletes=True,
    )