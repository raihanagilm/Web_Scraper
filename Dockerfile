# ============================================================
#  Web_Scraper — Deployment Container (Docker Desktop / VPS)
#  FastAPI + Playwright (Chromium) + frontend static
#  Browser TIDAK headless: dijalankan di LAYAR VIRTUAL (Xvfb) di dalam
#  container dan bisa dilihat user dari browser biasa via noVNC (:8002).
#  Bind: docker run -p 8000:8000 -p 8002:8002  →  http://localhost:8000
#        (bisa diakses dari device lain via IP LAN/VPS)
#  Detail: docker/entrypoint.sh, file.md §2.7
# ============================================================
FROM python:3.11-slim

# ---- Env container ----
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    # Chromium headful di layar virtual :99 (di-serve noVNC) + bundled Chromium
    # (tanpa system Chrome). Lihat docker/entrypoint.sh.
    DISPLAY=:99 \
    BROWSER_HEADLESS=false \
    BROWSER_CHANNEL="" \
    NOVNC_ENABLED=1 \
    NOVNC_PORT=8002 \
    SCREEN_WIDTH=1920 \
    SCREEN_HEIGHT=1080

WORKDIR /app

# ---- Python dependencies ----
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ---- Playwright Chromium + system deps (--with-deps apt-install) ----
RUN python -m playwright install --with-deps chromium

# ---- Display virtual + noVNC (monitor browser dari device user) ----
#   xvfb        → layar virtual (X11) tempat Chromium headful menggambar
#   openbox     → window manager (title bar, maximize, Alt+Tab antar job)
#   x11vnc      → server VNC (opsional berpassword via NOVNC_PASSWORD)
#   novnc/websockify → UI VNC berbasis browser (HTML5, tanpa install client)
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        openbox \
        novnc \
        websockify \
    && rm -rf /var/lib/apt/lists/*

# ---- Application ----
COPY backend ./backend
COPY frontend ./frontend
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 8000 = aplikasi web, 8002 = noVNC (monitor browser)
EXPOSE 8000 8002

# Entrypoint menyalakan display stack lalu `exec` CMD (uvicorn).
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# Bind 0.0.0.0 agar bisa diakses dari device lain di jaringan LAN/VPS
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]