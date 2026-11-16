"""Auth routes — deklarasi endpoint auth."""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from app.Models import get_db
from app.Middleware.auth_middleware import require_auth
from app.Controllers.AuthController import AuthController, LoginRequest, CreateUserRequest

router = APIRouter()


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    return AuthController.login(req, request, db)


@router.post("/logout")
def logout(request: Request) -> dict:
    return AuthController.logout(request)


@router.get("/me")
def me(request: Request) -> dict:
    return AuthController.me(request)


@router.get("/users")
def list_users(request: Request, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> list[dict]:
    return AuthController.list_users(request, db)


@router.post("/users")
def create_user(req: CreateUserRequest, request: Request, _: dict = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    return AuthController.create_user(req, request, db)
