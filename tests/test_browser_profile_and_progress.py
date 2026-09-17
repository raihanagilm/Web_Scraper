"""Test unit untuk browser_profile helper dan logika progress job."""
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from backend.services.browser_profile import (
    get_login_profile_dir,
    is_login_profile_ready,
    clone_login_profile,
    launch_login_browser_context,
)


def test_get_login_profile_dir():
    """Memastikan helper mendeteksi direktori profil Playwright tombol 'Buka Browser Login'."""
    p_dir = get_login_profile_dir()
    assert p_dir is not None
    assert "playwright_chrome_profile_gmaps" in p_dir
    assert os.path.exists(p_dir)


def test_is_login_profile_ready():
    """Memastikan helper mengecek keberadaan file cookie di direktori profil login."""
    res = is_login_profile_ready()
    # Harus boolean True/False tanpa error
    assert isinstance(res, bool)


def test_clone_login_profile():
    """Memastikan clone_login_profile menduplikasi direktori profil ke worker target."""
    with tempfile.TemporaryDirectory() as tmp_worker:
        dest = clone_login_profile(tmp_worker)
        assert os.path.isdir(dest)
        assert os.path.exists(dest)


def test_needs_no_sandbox_container_root():
    """Chromium di container (root) butuh --no-sandbox JUGA saat headful (noVNC)."""
    from backend.services.browser_profile import needs_no_sandbox

    with patch("backend.services.browser_profile.settings") as mock_settings, \
         patch.dict(os.environ, {}, clear=True), \
         patch("backend.services.browser_profile.is_container_runtime", return_value=True):
        mock_settings.browser_headless = False
        assert needs_no_sandbox(headless=False) is True  # container → no-sandbox


def test_needs_no_sandbox_host_headful():
    """Di mesin host (non-root, bukan container) headful tidak butuh --no-sandbox."""
    from backend.services.browser_profile import needs_no_sandbox

    with patch("backend.services.browser_profile.settings") as mock_settings, \
         patch.dict(os.environ, {}, clear=True), \
         patch("backend.services.browser_profile.os.geteuid", create=True, return_value=1000), \
         patch("backend.services.browser_profile.is_container_runtime", return_value=False):
        mock_settings.browser_headless = False
        assert needs_no_sandbox(headless=False) is False


def test_build_browser_args_headless_default_and_dedup():
    """build_browser_args: default --start-maximized + penyesuaian container, tanpa duplikasi flag."""
    from backend.services.browser_profile import build_browser_args, needs_no_sandbox

    # Headless (mesin apa pun) → selalu butuh no-sandbox
    assert "--no-sandbox" in build_browser_args(None, True)
    assert "--disable-dev-shm-usage" in build_browser_args(None, True)

    # User args tidak tertimpa & flag tidak diduplikasi
    base = build_browser_args(["--start-maximized", "--no-sandbox"], True)
    assert base.count("--no-sandbox") == 1
    assert base.count("--start-maximized") == 1
    assert "--disable-blink-features=AutomationControlled" not in base

    # Env override BROWSER_NO_SANDBOX → no-sandbox walau headful di host
    with patch.dict(os.environ, {"BROWSER_NO_SANDBOX": "1"}, clear=True):
        assert needs_no_sandbox(headless=False) is True


def test_novnc_settings_flags():
    """Setelan noVNC: tersedia hanya bila enabled DAN browser tidak headless."""
    from backend.config import Settings

    cfg = Settings(novnc_enabled=True, browser_headless=False, novnc_public_url=" https://vnc.example.com ")
    assert cfg.novnc_available is True
    assert cfg.novnc_url == "https://vnc.example.com"

    cfg_headless = Settings(novnc_enabled=True, browser_headless=True)
    assert cfg_headless.novnc_available is False

    cfg_off = Settings(novnc_enabled=False, browser_headless=False)
    assert cfg_off.novnc_available is False
    assert cfg_off.novnc_url == ""


def test_on_progress_preserves_total_found():
    """Memastikan _on_progress tidak menimpa total_found dengan angka yang lebih kecil."""
    from backend.services.job_manager import JobManager
    from backend.models.scrape_job import ScrapeJob

    jm = JobManager()
    mock_db = MagicMock()
    mock_job = ScrapeJob(id="test-job-1", status="running", progress=0, total_found=120)

    with patch("backend.services.job_manager.SessionLocal", return_value=mock_db), \
         patch("backend.services.job_manager.store.get_job", return_value=mock_job), \
         patch("backend.services.job_manager.store.update_job") as mock_update_job, \
         patch("backend.services.job_manager.store.append_job_log"):
        
        # Panggil saat penyimpanan DB dengan total=50 (lebih kecil dari total_found 120)
        jm._on_progress("test-job-1", progress=10, total=50, message="Menyimpan lead 10/50")

        # total_found harus tetap 120, bukan turun ke 50
        mock_update_job.assert_called_once_with(
            mock_db, "test-job-1", progress=10, total_found=120
        )
