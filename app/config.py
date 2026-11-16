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
# Browser (Playwright / Chromium)
    browser_headless: bool = False      # True saat jalan di Docker/CI (env BROWSER_HEADLESS)
    browser_channel: str = "chrome"     # 'chrome'=system Google Chrome (lokal); kosong='' = bundled Chromium (Docker)
    scraper_default_max_results: int = 100

    # Monitor browser (noVNC) — hanya aktif di container yang menjalankan
    # docker/entrypoint.sh (Xvfb + x11vnc + noVNC, lihat file.md §2.7).
    # Frontend membaca info ini dari /api/browser-status untuk menampilkan
    # tombol "Lihat Browser (Monitor)".
    novnc_enabled: bool = False          # NOVNC_ENABLED (di container = 1)
    novnc_port: int = 8002               # NOVNC_PORT (port web noVNC)
    novnc_public_url: str = ""           # NOVNC_PUBLIC_URL (opsional; mis. via Cloudflare tunnel)
    novnc_password: str = ""             # NOVNC_PASSWORD (hanya untuk indikator "butuh password")

    # Job watchdog: job "running" tanpa progres selama sekian detik
    # dianggap mati/hang → reconcile menandainya "error" (lihat job_manager).
    job_stale_seconds: int = 600

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def novnc_url(self) -> str:
        """URL noVNC eksplisit bila diisi (NOVNC_PUBLIC_URL); kosong = frontend menyusun sendiri dari hostname+port."""
        return self.novnc_public_url.strip()

    @property
    def novnc_available(self) -> bool:
        """True bila monitor browser benar-benar bisa dipakai: noVNC aktif DAN browser headful."""
        return self.novnc_enabled and not self.browser_headless


settings = Settings()
