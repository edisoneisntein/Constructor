"""Endpoints de gestión de cambios (§15)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ActiveOrganization, Connection, CurrentUser, require_role
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db import repositories as repo
from app.schemas.models import (
    ChangeApprovalIn,
    ChangeSetCreate,
    ChangeSetDetailOut,
    ChangeSetOut,
    Role,
)
from app.services import change_service
from app.services.change_service import FileEdit

router = APIRouter(tags=["changes"])


def _require_analysis(conn, analysis_id: str, organization_id: str) -> dict:
    job = repo.get_job(conn, analysis_id, organization_id)
    if job is None:
        raise NotFoundError("Análisis no encontrado.")
    return job


@router.post("/analyses/{analysis_id}/change-sets", response_model=ChangeSetDetailOut, status_code=201)
def create_change_set(
    analysis_id: str,
    payload: ChangeSetCreate,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ChangeSetDetailOut:
    require_role(organization, Role.developer)
    job = _require_analysis(conn, analysis_id, organization["id"])
    change_set = change_service.create_change_set(
        conn,
        settings=get_settings(),
        job=job,
        user_id=user["id"],
        reason=payload.reason,
        produced_by_rule=payload.produced_by_rule,
        edits=[FileEdit(path=edit.path, new_content=edit.new_content) for edit in payload.edits],
    )
    detail = change_service.get_change_set_detail(
        conn, change_set_id=change_set["id"], organization_id=organization["id"]
    )
    return ChangeSetDetailOut(**detail)


@router.get("/analyses/{analysis_id}/change-sets", response_model=list[ChangeSetOut])
def list_change_sets(
    analysis_id: str, organization: ActiveOrganization, conn: Connection
) -> list[ChangeSetOut]:
    _require_analysis(conn, analysis_id, organization["id"])
    return [
        ChangeSetOut(**item)
        for item in change_service.list_change_sets(
            conn, analysis_id=analysis_id, organization_id=organization["id"]
        )
    ]


@router.get("/change-sets/{change_set_id}", response_model=ChangeSetDetailOut)
def get_change_set(change_set_id: str, organization: ActiveOrganization, conn: Connection) -> ChangeSetDetailOut:
    detail = change_service.get_change_set_detail(
        conn, change_set_id=change_set_id, organization_id=organization["id"]
    )
    return ChangeSetDetailOut(**detail)


@router.post("/change-sets/{change_set_id}/approve", response_model=ChangeSetDetailOut)
def approve_change_set(
    change_set_id: str,
    payload: ChangeApprovalIn,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ChangeSetDetailOut:
    require_role(organization, Role.admin)
    detail = change_service.approve_change_set(
        conn,
        change_set_id=change_set_id,
        organization_id=organization["id"],
        user_id=user["id"],
        decision=payload.decision,
        comment=payload.comment,
    )
    return ChangeSetDetailOut(**detail)


@router.post("/change-sets/{change_set_id}/apply", response_model=ChangeSetDetailOut)
def apply_change_set(
    change_set_id: str,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ChangeSetDetailOut:
    require_role(organization, Role.developer)
    detail = change_service.apply_change_set(
        conn, change_set_id=change_set_id, organization_id=organization["id"], user_id=user["id"]
    )
    return ChangeSetDetailOut(**detail)


@router.post("/change-sets/{change_set_id}/validate", response_model=ChangeSetDetailOut)
def validate_change_set(
    change_set_id: str,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ChangeSetDetailOut:
    require_role(organization, Role.developer)
    detail = change_service.validate_change_set(
        conn,
        settings=get_settings(),
        change_set_id=change_set_id,
        organization_id=organization["id"],
        user_id=user["id"],
    )
    return ChangeSetDetailOut(**detail)


@router.post("/change-sets/{change_set_id}/rollback", response_model=ChangeSetDetailOut)
def rollback_change_set(
    change_set_id: str,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ChangeSetDetailOut:
    require_role(organization, Role.developer)
    detail = change_service.rollback_change_set(
        conn, change_set_id=change_set_id, organization_id=organization["id"], user_id=user["id"]
    )
    return ChangeSetDetailOut(**detail)
