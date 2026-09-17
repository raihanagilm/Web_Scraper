#!/usr/bin/env bash
# ============================================================
#  docker/entrypoint.sh — Display virtual + noVNC (monitor browser)
#
#  MASALAH: di container (Docker/VPS) tidak ada layar, sehingga Chromium
#  Playwright wajib headless dan jendelanya tidak bisa dilihat user.
#  SOLUSI: container ini menyediakan LAYAR VIRTUAL (Xvfb) + server VNC
#  (x11vnc) + UI HTML5 (noVNC/websockify). Chromium tetap "headful" di
#  layar virtual itu, dan user melihat/mengendalikannya dari browser
#  biasa lewat http://<host>:8002/vnc.html.
#
#  Urutan start: Xvfb (:99) → openbox (window manager) → x11vnc (5900)
#                → websockify + noVNC (HTTP :8002) → exec CMD (uvicorn)
#
#  Env:
#    NOVNC_ENABLED=0        matikan display stack (balik ke headless)
#    DISPLAY=:99            nomor display virtual
#    SCREEN_WIDTH/HEIGHT/DEPTH   ukuran layar (default 1920x1080x24)
#    NOVNC_PORT=8002        port web noVNC (dipublikasikan compose)
#    VNC_PORT=5900          port RFB internal (TIDAK dipublikasikan)
#    NOVNC_PASSWORD=""      password VNC (opsional, maks 8 karakter RFB)
#
#  Dokumentasi: file.md §2.7 dan README §4.
# ============================================================
set -e

DISPLAY_NUM="${DISPLAY:-:99}"
SCREEN_WIDTH="${SCREEN_WIDTH:-1920}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-1080}"
SCREEN_DEPTH="${SCREEN_DEPTH:-24}"
NOVNC_ENABLED="${NOVNC_ENABLED:-1}"
NOVNC_PORT="${NOVNC_PORT:-8002}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PASSWORD="${NOVNC_PASSWORD:-}"
NOVNC_WEB="${NOVNC_WEB:-/usr/share/novnc}"

log() { echo "[entrypoint] $*"; }

# Tunggu socket X (maks ±10 detik) agar tidak ada race saat Chromium start.
wait_for_x_socket() {
  local sock="/tmp/.X11-unix/X${DISPLAY_NUM#:}"
  local i
  for i in $(seq 1 50); do
    if [ -S "$sock" ]; then return 0; fi
    sleep 0.2
  done
  return 1
}

# Return 0 bila display stack siap dipakai; 1 bila harus fallback headless.
start_display_stack() {
  if [ "$NOVNC_ENABLED" = "0" ]; then
    log "NOVNC_ENABLED=0 → monitor browser dimatikan."
    return 1
  fi
  if ! command -v Xvfb >/dev/null 2>&1; then
    log "Xvfb tidak ada di image → monitor browser dimatikan."
    return 1
  fi

  Xvfb "$DISPLAY_NUM" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac -nolisten tcp >/dev/null 2>&1 &
  if ! wait_for_x_socket; then
    log "Xvfb gagal siap (socket ${DISPLAY_NUM} tidak muncul) → fallback headless."
    return 1
  fi
  log "Xvfb aktif: ${DISPLAY_NUM} ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}"

  # Window manager (opsional tapi sangat membantu): title bar, maximize
  # (agar --start-maximized berlaku) dan Alt+Tab untuk pindah antar jendela
  # saat 2–3 job scraping berjalan bersamaan.
  if command -v openbox >/dev/null 2>&1; then
    openbox --sm-disable >/dev/null 2>&1 &
    log "Window manager openbox aktif — Alt+Tab untuk pindah jendela job."
  else
    log "openbox tidak tersedia — jendela tetap tampil tanpa title bar."
  fi

  if ! command -v x11vnc >/dev/null 2>&1; then
    log "x11vnc tidak tersedia → monitor browser dimatikan."
    return 1
  fi

  local rfb_auth=(-nopw)
  if [ -n "$NOVNC_PASSWORD" ]; then
    if [ "${#NOVNC_PASSWORD}" -gt 8 ]; then
      log "Peringatan: protokol VNC hanya memakai 8 karakter pertama password."
    fi
    mkdir -p /root/.vnc
    x11vnc -storepasswd "$NOVNC_PASSWORD" /root/.vnc/passwd >/dev/null 2>&1
    rfb_auth=(-rfbauth /root/.vnc/passwd)
    log "x11vnc aktif: ${VNC_PORT} (password wajib)"
  else
    log "x11vnc aktif: ${VNC_PORT} (TANPA password — batasi port ${NOVNC_PORT} via firewall/tunnel!)"
  fi
  x11vnc -display "$DISPLAY_NUM" -forever -shared -rfbport "$VNC_PORT" \
         -quiet -noxrecord "${rfb_auth[@]}" >/dev/null 2>&1 &

  if ! command -v websockify >/dev/null 2>&1 || [ ! -d "$NOVNC_WEB" ]; then
    log "websockify/noVNC tidak tersedia → monitor browser dimatikan."
    return 1
  fi

  local page="vnc.html"
  if [ ! -f "${NOVNC_WEB}/vnc.html" ]; then page="vnc_lite.html"; fi
  websockify --web="$NOVNC_WEB" "0.0.0.0:${NOVNC_PORT}" "127.0.0.1:${VNC_PORT}" >/dev/null 2>&1 &
  sleep 1
  log "noVNC siap → http://<host>:${NOVNC_PORT}/${page}?autoconnect=1&resize=scale"
  return 0
}

if start_display_stack; then
  export BROWSER_HEADLESS=false
  log "BROWSER_HEADLESS=false → Chromium headful di ${DISPLAY_NUM} (terlihat via noVNC)."
else
  export BROWSER_HEADLESS=true
  log "BROWSER_HEADLESS=true → Chromium headless (tanpa jendela yang bisa dilihat)."
fi

exec "$@"
