"""Utilitas profil browser Chrome untuk scraping & enrichment.

Menggunakan profil Chrome persisten dari tombol 'Buka Browser Login'
(~/playwright_chrome_profile_gmaps) agar semua scraper (Google Maps & Enrichment)
berjalan dengan akun Google yang SUDAH LOGIN.

Jika profil utama sedang terbuka (misal tombol login sedang aktif atau ada job lain),
secara otomatis membuat kloning isolasi sementara agar sesi login tetap terbawa 100%
tanpa bentrok file lock (ProcessSingleton).
"""

import os
import re
import shutil
import logging
import tempfile
import uuid
from typing import Tuple, Optional
from playwright.sync_api import sync_playwright, BrowserContext

logger = logging.getLogger(__name__)

LOGIN_PROFILE_DIR = os.path.expanduser("~/playwright_chrome_profile_gmaps")


def get_login_profile_dir() -> str:
    """Mendapatkan path profil Chrome persisten yang dipakai tombol 'Buka Browser Login'."""
    os.makedirs(LOGIN_PROFILE_DIR, exist_ok=True)
    return LOGIN_PROFILE_DIR


def is_login_profile_ready() -> bool:
    """Cek apakah profil login sudah ada dan memiliki cookie sesi Google."""
    p_dir = get_login_profile_dir()
    cookie_file = os.path.join(p_dir, "Default", "Network", "Cookies")
    if not os.path.isfile(cookie_file):
        cookie_file = os.path.join(p_dir, "Default", "Cookies")
    return os.path.isfile(cookie_file) and os.path.getsize(cookie_file) > 0


def clone_login_profile(worker_dir: str) -> str:
    """Kloning seluruh direktori ~/playwright_chrome_profile_gmaps ke worker_dir,
    mengabaikan file lock Chromium (SingletonLock, *.lock) agar sesi login Google
    dapat dibuka secara bersamaan di instance Playwright terpisah."""
    src = get_login_profile_dir()
    os.makedirs(worker_dir, exist_ok=True)
    shutil.rmtree(worker_dir, ignore_errors=True)

    if os.path.isdir(src):
        try:
            shutil.copytree(
                src,
                worker_dir,
                ignore=shutil.ignore_patterns("*.lock", "Singleton*", "Crashpad", "BrowserMetrics"),
            )
            logger.info("Berhasil mengkloning profil login Google ke %s", worker_dir)
        except Exception as e:
            logger.warning("Gagal mengkloning profil login Google secara penuh: %s", e)
            os.makedirs(worker_dir, exist_ok=True)

    return worker_dir


def launch_login_browser_context(
    playwright_instance,
    job_id: Optional[str] = None,
    headless: bool = False,
    args: Optional[list] = None,
) -> Tuple[BrowserContext, Optional[str]]:
    """Membuka persistent context Playwright dengan akun Google yang sudah login.

    Strategi:
    1. Coba buka profil utama ~/playwright_chrome_profile_gmaps secara langsung (instan & tanpa overhead).
    2. Jika gagal karena terkunci (TargetClosedError / SingletonLock), kloning ke direktori worker sementara.

    Mengembalikan tuple: (context, temp_worker_dir_yang_perlu_dibersihkan_atau_None).
    """
    cmd_args = args or ["--start-maximized"]
    primary_dir = get_login_profile_dir()

    # 1. Coba buka direktori profil login utama
    try:
        context = playwright_instance.chromium.launch_persistent_context(
            user_data_dir=primary_dir,
            headless=headless,
            channel="chrome",
            ignore_https_errors=True,
            args=cmd_args,
        )
        logger.info("Browser berhasil dibuka langsung menggunakan profil login utama: %s", primary_dir)
        return context, None
    except Exception as e:
        logger.info("Profil login utama sedang terkunci (%s), menggunakan worker clone...", e)

    # 2. Fallback: kloning profil login ke folder worker sementara
    clean_id = re.sub(r"[^a-zA-Z0-9]+", "_", job_id or uuid.uuid4().hex[:8])
    worker_dir = os.path.join(tempfile.gettempdir(), "playwright_login_workers", f"worker_{clean_id}")
    clone_login_profile(worker_dir)

    context = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=worker_dir,
        headless=headless,
        channel="chrome",
        ignore_https_errors=True,
        args=cmd_args,
    )
    logger.info("Browser berhasil dibuka menggunakan worker clone login: %s", worker_dir)
    return context, worker_dir
