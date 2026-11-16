"""API Router Aggregator — menggabungkan semua sub-router API."""
from fastapi import APIRouter

from routes.auth import router as auth_router
from routes.scrape import router as scrape_router
from routes.lead import router as lead_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(scrape_router, tags=["scrape"])
api_router.include_router(lead_router, tags=["leads"])
