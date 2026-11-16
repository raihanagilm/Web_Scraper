"""Auth routes — deklarasi endpoint auth."""
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from app.Models import get_db
from app.Controllers.AuthController import AuthController, LoginRequest

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
