"""Endpoints de autenticación (§4.1)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import Connection, CurrentUser
from app.schemas.models import LoginRequest, RegisterRequest, SessionOut, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=SessionOut, status_code=201)
def register(payload: RegisterRequest, conn: Connection) -> SessionOut:
    session = auth_service.register(
        conn,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        organization_name=payload.organization_name,
    )
    return SessionOut(**session)


@router.post("/login", response_model=SessionOut)
def login(payload: LoginRequest, conn: Connection) -> SessionOut:
    session = auth_service.login(conn, email=payload.email, password=payload.password)
    return SessionOut(**session)


@router.post("/logout", status_code=204)
def logout(request: Request, conn: Connection) -> None:
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        auth_service.logout(conn, session_id)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut(
        id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        created_at=user["created_at"],
    )
