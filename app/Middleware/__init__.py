"""Middleware package."""
from app.Middleware.auth_middleware import require_auth

__all__ = ["require_auth"]
