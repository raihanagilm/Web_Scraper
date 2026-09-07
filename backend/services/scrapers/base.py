"""Base scraper interface + rate limiting + progress emission."""
import time
import random
from abc import ABC, abstractmethod
from typing import Callable, List, Dict, Any, Optional
from backend.config import settings


class BaseScraper(ABC):
    """Kelas dasar untuk semua scraper."""

    def __init__(self, source: str, category: str, city: str, max_results: int = 100):
        self.source = source
        self.category = category
        self.city = city
        self.max_results = max_results
        self._cancelled = False
        self._progress_cb: Optional[Callable[[int, int, str], None]] = None

    def set_progress_callback(self, cb: Callable[[int, int, str], None]) -> None:
        """cb(progress, total_found, message)"""
        self._progress_cb = cb

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def is_alive(self) -> bool:
        """True jika proses scraper masih hidup.

        Override di scraper berbasis browser (mis. GmapsScraper) untuk
        mendeteksi jendela browser yang ditutup/crash — dipakai JobManager
        saat reconcile agar status job tidak stuck di "running".
        """
        return True

    def emit_progress(self, progress: int, total_found: int, message: str) -> None:
        if self._progress_cb:
            self._progress_cb(progress, total_found, message)

    def rate_limit(self) -> None:
        """Delay 1-3 detik sesuai SOP."""
        delay = random.uniform(settings.scraper_min_delay, settings.scraper_max_delay)
        time.sleep(delay)

    @abstractmethod
    def run(self) -> List[Dict[str, Any]]:
        """Jalankan scraping, return list of raw lead dicts."""
        ...
