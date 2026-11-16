"""Dependency bersama: proteksi auth untuk semua API."""
from fastapi import Request, HTTPException


def require_auth(request: Request) -> dict:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"id": uid, "username": request.session.get("username", "")}