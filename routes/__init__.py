"""Routes package."""
from routes.api import api_router
from routes.auth import router as auth_router
from routes.scrape import router as scrape_router
from routes.lead import router as lead_router

__all__ = ["api_router", "auth_router", "scrape_router", "lead_router"]
