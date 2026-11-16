"""AuthController — Menangani logika autentikasi (login, logout, me)."""
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.Models import User
from app.Services.auth_service import verify_password


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str


class AuthController:
    @staticmethod
    def login(req: LoginRequest, request: Request, db: Session) -> dict:
        user = db.query(User).filter(User.username == req.username).first()
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        request.session["user_id"] = user.id
        request.session["username"] = user.username
        return {"ok": True, "user": {"id": user.id, "username": user.username, "full_name": user.full_name}}

    @staticmethod
    def logout(request: Request) -> dict:
        request.session.clear()
        return {"ok": True}

    @staticmethod
    def me(request: Request) -> dict:
        uid = request.session.get("user_id")
        if not uid:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return {"id": uid, "username": request.session.get("username", "")}
