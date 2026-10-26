"""Dependencias de FastAPI: conexión, autenticación y autorización por organización.

§16: toda consulta se delimita por organización; se impide IDOR.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.ids import is_expired
from app.core.security import hash_session_token
from app.db import repositories as repo
from app.db.session import get_database
from app.schemas.models import Role

ROLE_RANK: dict[str, int] = {
    Role.viewer.value: 1,
    Role.developer.value: 2,
    Role.admin.value: 3,
    Role.owner.value: 4,
}


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    database = get_database()
    connection = database.connect()
    if hasattr(request, "state"):
        request.state.db_conn = connection
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if not database.is_ephemeral:
            connection.close()


Connection = Annotated[sqlite3.Connection, Depends(get_conn)]


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def get_current_user(request: Request, conn: Connection) -> dict:
    token = _extract_bearer(request)
    if token is None:
        if get_settings().dev_auth_bypass:
            # Modo desarrollo local: usuario simulado con rol de propietario.
            from datetime import datetime, timezone

            return {
                "id": "dev-user-000",
                "email": "dev@localhost.local",
                "display_name": "Dev User",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        raise UnauthorizedError("Autenticación requerida.")
    session = repo.get_session_by_hash(conn, hash_session_token(token))
    if session is None or session.get("revoked_at") or is_expired(session["expires_at"]):
        from app.core.logging import get_logger

        get_logger("app.auth").warning(
            "session_lookup_failed found=%s db=%s" % (session is not None, get_database().label)
        )
        raise UnauthorizedError("Sesión inválida o expirada.")
    user = repo.get_user_by_id(conn, session["user_id"])
    if user is None:
        raise UnauthorizedError("Usuario no encontrado.")
    request.state.session_id = session["id"]
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]


def resolve_organization(
    user: dict,
    conn: sqlite3.Connection,
    x_organization_id: str | None,
) -> dict:
    """Resuelve la organización activa y su rol, validando pertenencia."""
    memberships = repo.list_organizations_for_user(conn, user["id"])
    if not memberships:
        if get_settings().dev_auth_bypass:
            # Modo desarrollo local: organización simulada.
            return {
                "id": "dev-org-000",
                "name": "Dev Org",
                "role": "owner",
                "user_id": user["id"],
            }
        raise NotFoundError("El usuario no pertenece a ninguna organización.")
    if x_organization_id:
        for membership in memberships:
            if membership["id"] == x_organization_id:
                return membership
        raise ForbiddenError("No pertenece a la organización solicitada.")
    return memberships[0]


def get_active_organization(
    user: CurrentUser,
    conn: Connection,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> dict:
    return resolve_organization(user, conn, x_organization_id)


ActiveOrganization = Annotated[dict, Depends(get_active_organization)]


def require_role(organization: dict, minimum: Role) -> None:
    current = ROLE_RANK.get(organization.get("role", "viewer"), 0)
    if current < ROLE_RANK[minimum.value]:
        raise ForbiddenError(
            f"Se requiere rol {minimum.value} o superior; su rol es {organization.get('role')}."
        )
