import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from backend.config import settings
from backend.models import init_db
from backend.seed import seed_default_user

from backend.controllers.auth_routes import router as auth_router
from backend.controllers.scrape_routes import router as scrape_router
from backend.controllers.lead_routes import router as lead_router

BASE_DIR = Path(__file__).resolve().parent  # backend/
ROOT_DIR = BASE_DIR.parent                 # Web_Scraper/


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_default_user()
    yield


app = FastAPI(title="Edtekno Lead Scraper", version="1.0.0", lifespan=lifespan)

# Signed session cookie middleware
# (starlette >=0.40: parameter `same_site` & `https_only`; cookie selalu HttpOnly)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    max_age=86400,
    same_site="lax",
    https_only=False,
)

# Routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(scrape_router, prefix="/api", tags=["scrape"])
app.include_router(lead_router, prefix="/api", tags=["leads"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": "Edtekno Lead Scraper"}


# noVNC reverse proxy WebSocket & static mounting
# Memungkinkan noVNC diakses langsung dari port utama (8000) dan via Cloudflare Tunnel
@app.websocket("/websockify")
@app.websocket("/novnc/websockify")
async def novnc_websocket_proxy(websocket: WebSocket):
    requested = websocket.headers.get("sec-websocket-protocol", "")
    subprotocol = "binary" if "binary" in [p.strip() for p in requested.split(",")] else None
    await websocket.accept(subprotocol=subprotocol)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 5900)
    except Exception:
        await websocket.close()
        return

    async def ws_to_tcp():
        try:
            while True:
                msg = await websocket.receive()
                if "bytes" in msg and msg["bytes"]:
                    writer.write(msg["bytes"])
                    await writer.drain()
                elif "text" in msg and msg["text"]:
                    writer.write(msg["text"].encode("latin1"))
                    await writer.drain()
                elif msg.get("type") == "websocket.disconnect":
                    break
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def tcp_to_ws():
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                await websocket.send_bytes(data)
        except Exception:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    await asyncio.gather(ws_to_tcp(), tcp_to_ws(), return_exceptions=True)


# Serve noVNC static UI bila ada di container
novnc_dir = Path("/usr/share/novnc")
if novnc_dir.is_dir():
    app.mount("/novnc", StaticFiles(directory=str(novnc_dir), html=True), name="novnc")

# Serve audio sound-effects (dipasang sebelum mount "/" agar tidak ketutup)
audio_dir = BASE_DIR / "audio"
if audio_dir.is_dir():
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

# Static frontend — WAJIB di akhir agar tidak menutupi /api/*
frontend_dir = ROOT_DIR / "frontend"
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
