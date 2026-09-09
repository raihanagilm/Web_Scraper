"""Model Lead — tabel utama leads (normalisasi kategori & kota via FK)."""
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.models.base import Base


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("source", "nama_instansi", "city_id", name="uq_lead_source_name_city"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    kode = Column(String(50), unique=True, nullable=True, index=True)
    source = Column(Enum("gmaps", "dapodik", name="source_enum"), nullable=False)
    priority = Column(Enum("high", "medium", name="priority_enum"), nullable=False, default="medium")

    # Base fields (sesuai tabel default)
    nama_instansi = Column(String(255), nullable=False, default="")
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    telp = Column(String(20), default="")
    email = Column(Text, default="")
    alamat = Column(Text, default="")
    city_id = Column(Integer, ForeignKey("cities.id", ondelete="SET NULL"), nullable=True)
    link_gmaps = Column(Text, default="")
    website = Column(Text, default="")
    sosmed = Column(Text, default="")
    instagram = Column(Text, default="")
    facebook = Column(Text, default="")
    linkedin = Column(Text, default="")
    twitter_x = Column(Text, default="")
    tiktok = Column(Text, default="")
    link_source = Column(Text, default="")
    status = Column(Enum("New", "Contacted", "Follow Up", "Deal", "Rejected", name="status_enum"), default="New")

    # Relasi ke tabel lookup (lazy load)
    category = relationship("Category", lazy="joined")
    city = relationship("City", lazy="joined")

    # Extra nullable fields per kategori
    npsn = Column(String(20), default="")
    nama_kepsek = Column(String(200), default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def kategori(self) -> str:
        """Backward-compatible accessor: mengembalikan nama kategori sebagai string."""
        return self.category.name if self.category else ""

    @kategori.setter
    def kategori(self, value: str) -> None:
        """Setter no-op — kategori diset via category_id, bukan via properti ini.

        Dipakai agar kode lama yang masih mengacu ``lead.kategori = ...``
        tidak crash (nilainya akan diabaikan / dikelola oleh storage_service).
        """
        pass

    @property
    def kota(self) -> str:
        """Backward-compatible accessor: mengembalikan nama kota sebagai string."""
        return self.city.name if self.city else ""

    @kota.setter
    def kota(self, value: str) -> None:
        """Setter no-op — kota diset via city_id, bukan via properti ini."""
        pass