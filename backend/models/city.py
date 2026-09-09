"""Model City — master data kota/kabupaten."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from backend.models.base import Base


class City(Base):
    """Master data kota/kabupaten.

    Normalisasi dari kolom string `kota` yang berulang dan rawan inkonsistensi
    kapitalisasi di tabel `leads`.
    """

    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kode = Column(String(50), unique=True, nullable=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    province = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<City(id={self.id}, name={self.name!r})>"