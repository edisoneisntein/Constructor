"""Endpoints de migración Gemini → NVIDIA NIM (§11/§12/§17)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ActiveOrganization, Connection, CurrentUser, require_role
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db import repositories as repo
from app.schemas.models import (
    MigrationChangeOut,
    MigrationCreate,
    MigrationPlanDetailOut,
    MigrationPlanOut,
    NimStatusOut,
    Role,
)
from app.services import migration_service

router = APIRouter(tags=["migrations"])


def _require_project(conn, project_id: str, organization_id: str) -> dict:
    project = repo.get_project(conn, project_id, organization_id)
    if project is None:
        raise NotFoundError("Proyecto no encontrado.")
    return project


@router.post("/migrations/nim/verify", response_model=NimStatusOut)
def verify_nim(
    user: CurrentUser,
    organization: ActiveOrganization,
) -> NimStatusOut:
    """Verifica credenciales y modelo de NVIDIA NIM (consulta en vivo)."""

    require_role(organization, Role.developer)
    report = migration_service.verify_nim_connection(get_settings())
    return NimStatusOut(**report)


@router.post("/projects/{project_id}/migrations", response_model=MigrationPlanDetailOut, status_code=201)
def create_migration_plan(
    project_id: str,
    payload: MigrationCreate,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> MigrationPlanDetailOut:
    require_role(organization, Role.developer)
    project = _require_project(conn, project_id, organization["id"])
    analysis = migration_service.require_analysis(
        conn, payload.analysis_id, organization["id"]
    )
    if analysis["project_id"] != project_id:
        raise NotFoundError("El análisis no pertenece al proyecto.")
    plan = migration_service.create_migration_plan(
        conn, settings=get_settings(), project=project, analysis=analysis, user_id=user["id"]
    )
    detail = migration_service.get_migration_plan_detail(
        conn, plan_id=plan["id"], organization_id=organization["id"]
    )
    return _detail_out(detail)


@router.get("/projects/{project_id}/migrations", response_model=list[MigrationPlanOut])
def list_migration_plans(
    project_id: str, organization: ActiveOrganization, conn: Connection
) -> list[MigrationPlanOut]:
    _require_project(conn, project_id, organization["id"])
    return [
        MigrationPlanOut(**_plan_fields(item))
        for item in migration_service.list_migration_plans(
            conn, project_id=project_id, organization_id=organization["id"]
        )
    ]


@router.get("/migrations/{migration_id}", response_model=MigrationPlanDetailOut)
def get_migration_plan(
    migration_id: str, organization: ActiveOrganization, conn: Connection
) -> MigrationPlanDetailOut:
    detail = migration_service.get_migration_plan_detail(
        conn, plan_id=migration_id, organization_id=organization["id"]
    )
    return _detail_out(detail)


_PLAN_FIELDS = set(MigrationPlanOut.model_fields)
_CHANGE_FIELDS = set(MigrationChangeOut.model_fields)


def _plan_fields(item: dict) -> dict:
    return {key: value for key, value in item.items() if key in _PLAN_FIELDS}


def _detail_out(detail: dict) -> MigrationPlanDetailOut:
    payload = _plan_fields(detail)
    payload["plan"] = detail.get("plan")
    payload["limitations"] = detail.get("limitations")
    payload["sources"] = detail.get("sources")
    payload["changes"] = [
        MigrationChangeOut(**{k: v for k, v in change.items() if k in _CHANGE_FIELDS})
        for change in detail.get("changes", [])
    ]
    return MigrationPlanDetailOut(**payload)
