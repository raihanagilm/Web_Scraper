"""AuthController — Menangani logika autentikasi (login, logout, me)."""
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.Models import User
from app.Services.auth_service import verify_password


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    full_name: str = ""


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

    @staticmethod
    def list_users(request: Request, db: Session) -> list[dict]:
        uid = request.session.get("user_id")
        if uid != 1:
            raise HTTPException(status_code=403, detail="Hanya Admin yang dapat mengelola pengguna")
        users = db.query(User).order_by(User.id.asc()).all()
        return [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name or "",
                "created_at": u.created_at.strftime("%d %b %Y %H:%M") if u.created_at else "",
            }
            for u in users
        ]

    @staticmethod
    def create_user(req: CreateUserRequest, request: Request, db: Session) -> dict:
        uid = request.session.get("user_id")
        if uid != 1:
            raise HTTPException(status_code=403, detail="Hanya Admin yang dapat membuat pengguna")
        uname = req.username.strip()
        if not uname or len(uname) < 3:
            raise HTTPException(status_code=422, detail="Username minimal 3 karakter")
        if not req.password or len(req.password) < 3:
            raise HTTPException(status_code=422, detail="Password minimal 3 karakter")
        existing = db.query(User).filter(User.username == uname).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username sudah digunakan")
        from app.Services.auth_service import hash_password
        user = User(
            username=uname,
            password_hash=hash_password(req.password),
            full_name=req.full_name.strip() or uname,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"ok": True, "user": {"id": user.id, "username": user.username, "full_name": user.full_name}}
