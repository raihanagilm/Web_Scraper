"""SQLAlchemy setup: Base, engine, SessionLocal, get_db, init_db."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import settings

Base = declarative_base()


def _connect_args() -> dict:
    """Konfigurasi koneksi DB beserta SSL (TiDB Cloud mewajibkan TLS)."""
    kwargs: dict = {}
    if settings.db_ssl_verify:
        ssl_cfg: dict = {}
        if settings.db_ssl_ca:
            ssl_cfg["ca"] = settings.db_ssl_ca
        kwargs["ssl"] = ssl_cfg
    return kwargs


# Engine dengan pooling + recycle (TiDB idle disconnect ~5 menit)
engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
    pool_pre_ping=True,
    future=True,
    connect_args=_connect_args(),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)