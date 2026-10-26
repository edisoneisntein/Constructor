"""Servicio de autenticación y organizaciones (§4.1, §16)."""

from __future__ import annotations

import sqlite3

from app.core.config import get_settings
from app.core.errors import ConflictError, UnauthorizedError, ValidationAppError
from app.core.ids import iso_after, new_id, utcnow_iso
from app.core.security import generate_session_token, hash_password, verify_password
from app.db import repositories as repo
from app.schemas.models import Role


def register(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    display_name: str,
    organization_name: str,
) -> dict:
    settings = get_settings()
    if len(password) < settings.password_min_length:
        raise ValidationAppError(
            f"La contraseña debe tener al menos {settings.password_min_length} caracteres.",
            details={"field": "password"},
        )
    if repo.get_user_by_email(conn, email) is not None:
        raise ConflictError("Ya existe una cuenta con ese correo.")
    now = utcnow_iso()
    user = repo.create_user(
        conn,
        email=email,
        display_name=display_name,
        password_hash=hash_password(password),
        created_at=now,
    )
    organization = repo.create_organization(conn, name=organization_name, created_at=now)
    repo.add_membership(
        conn,
        organization_id=organization["id"],
        user_id=user["id"],
        role=Role.owner.value,
        created_at=now,
    )
    repo.record_audit(
        conn,
        action="user.register",
        created_at=now,
        organization_id=organization["id"],
        user_id=user["id"],
        target_type="user",
        target_id=user["id"],
    )
    return _start_session(conn, user)


def login(conn: sqlite3.Connection, *, email: str, password: str) -> dict:
    user = repo.get_user_by_email(conn, email)
    if user is None or not verify_password(password, user["password_hash"]):
        # Mensaje uniforme para no filtrar existencia de cuentas.
        raise UnauthorizedError("Credenciales inválidas.")
    repo.record_audit(conn, action="user.login", created_at=utcnow_iso(), user_id=user["id"], target_type="user", target_id=user["id"])
    return _start_session(conn, user)


def _start_session(conn: sqlite3.Connection, user: dict) -> dict:
    settings = get_settings()
    now = utcnow_iso()
    raw_token, token_hash = generate_session_token()
    expires_at = iso_after(settings.session_ttl_seconds)
    repo.create_session(
        conn,
        user_id=user["id"],
        token_hash=token_hash,
        created_at=now,
        expires_at=expires_at,
    )
    return {
        "token": raw_token,
        "expires_at": expires_at,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "created_at": user["created_at"],
        },
    }


def logout(conn: sqlite3.Connection, session_id: str) -> None:
    repo.revoke_session(conn, session_id=session_id, revoked_at=utcnow_iso())


def _new_id() -> str:  # pragma: no cover - utilidad interna
    return new_id("tmp")
