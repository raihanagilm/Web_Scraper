"""Konfigurasi aplikasi — membaca environment variable."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "scraping_data"
    db_ssl_ca: str = ""
    db_ssl_verify: bool = True

    # Session / App
    session_secret: str = "change-me-in-production"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # Seed user
    seed_username: str = "admin"
    seed_password: str = "agiltampan"
    seed_full_name: str = "Administrator"

    # Scraper defaults
    scraper_min_delay: float = 1.0
    scraper_max_delay: float = 3.0
    scraper_default_max_results: int = 100

    # Job watchdog: job "running" tanpa progres selama sekian detik
    # dianggap mati/hang → reconcile menandainya "error" (lihat job_manager).
    job_stale_seconds: int = 600

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
