"""Endpoints de organizaciones (§4.1, §16)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Connection, CurrentUser
from app.db import repositories as repo
from app.schemas.models import OrganizationOut

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationOut])
def list_organizations(user: CurrentUser, conn: Connection) -> list[OrganizationOut]:
    memberships = repo.list_organizations_for_user(conn, user["id"])
    return [
        OrganizationOut(
            id=membership["id"],
            name=membership["name"],
            slug=membership["slug"],
            role=membership["role"],
            created_at=membership["created_at"],
        )
        for membership in memberships
    ]
