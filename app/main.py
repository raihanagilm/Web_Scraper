import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.Models import init_db
from database.seeders.user_seeder import seed_default_user
from routes.api import api_router

BASE_DIR = Path(__file__).resolve().parent  # app/
ROOT_DIR = BASE_DIR.parent                 # Web_Scraper/


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_default_user()
    yield


app = FastAPI(title="Edtekno Lead Scraper", version="1.0.0", lifespan=lifespan)

# Signed session cookie middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    max_age=86400,
    same_site="lax",
    https_only=False,
)

# API Routers
app.include_router(api_router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": "Edtekno Lead Scraper"}


# noVNC reverse proxy WebSocket & static mounting
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

# Serve audio sound-effects
audio_dir = ROOT_DIR / "public" / "audio"
if not audio_dir.is_dir():
    audio_dir = ROOT_DIR / "backend" / "audio"
if audio_dir.is_dir():
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

# Static frontend (public) — WAJIB di akhir agar tidak menutupi /api/*
public_dir = ROOT_DIR / "public"
if not public_dir.is_dir():
    public_dir = ROOT_DIR / "frontend"
if public_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(public_dir), html=True), name="frontend")
