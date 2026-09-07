"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
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


# Serve audio sound-effects (dipasang sebelum mount "/" agar tidak ketutup)
audio_dir = BASE_DIR / "audio"
if audio_dir.is_dir():
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

# Static frontend — WAJIB di akhir agar tidak menutupi /api/*
frontend_dir = ROOT_DIR / "frontend"
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
