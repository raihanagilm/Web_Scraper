"""Model Category — master data kategori lead."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from backend.models.base import Base


class Category(Base):
    """Master data kategori lead (sekolah, umkm, kafe, it, dll).

    Normalisasi dari kolom string `kategori` yang berulang di tabel `leads`.
    """

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kode = Column(String(50), unique=True, nullable=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Category(id={self.id}, name={self.name!r})>"