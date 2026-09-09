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
