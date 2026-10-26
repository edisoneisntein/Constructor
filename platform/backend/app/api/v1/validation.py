"""Endpoints del Implementation Validator (§ validación de requisitos)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ActiveOrganization, Connection, CurrentUser, require_role
from app.core.config import get_settings
from app.schemas.models import (
    ConformanceReportOut,
    Role,
    ValidationRequirementOut,
    ValidationRunOut,
    ValidationRunRequest,
    ValidationRunSummaryOut,
)
from app.services import validation_service

router = APIRouter(tags=["validation"])


@router.get("/validation/requirements", response_model=list[ValidationRequirementOut])
def list_requirements(organization: ActiveOrganization, conn: Connection) -> list[ValidationRequirementOut]:
    require_role(organization, Role.viewer)
    return [ValidationRequirementOut(**item) for item in validation_service.list_requirements(conn)]


@router.get("/validation/requirements/{requirement_id}", response_model=ValidationRequirementOut)
def get_requirement(
    requirement_id: str, organization: ActiveOrganization, conn: Connection
) -> ValidationRequirementOut:
    require_role(organization, Role.viewer)
    return ValidationRequirementOut(**validation_service.get_requirement(conn, requirement_id))


@router.post("/validation/run", response_model=ValidationRunOut, status_code=201)
def run_validation(
    payload: ValidationRunRequest,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ValidationRunOut:
    require_role(organization, Role.developer)
    run = validation_service.run_validation(
        conn,
        settings=get_settings(),
        user_id=user["id"],
        requirement_ids=payload.requirement_ids,
    )
    return ValidationRunOut(**run)


@router.get("/validation/runs", response_model=list[ValidationRunSummaryOut])
def list_runs(organization: ActiveOrganization, conn: Connection) -> list[ValidationRunSummaryOut]:
    require_role(organization, Role.viewer)
    return [ValidationRunSummaryOut(**item) for item in validation_service.list_runs(conn)]


@router.get("/validation/runs/{run_id}", response_model=ValidationRunOut)
def get_run(run_id: str, organization: ActiveOrganization, conn: Connection) -> ValidationRunOut:
    require_role(organization, Role.viewer)
    return ValidationRunOut(**validation_service.get_run_detail(conn, run_id))


@router.get("/validation/report", response_model=ConformanceReportOut)
def conformance_report(organization: ActiveOrganization, conn: Connection) -> ConformanceReportOut:
    require_role(organization, Role.viewer)
    return ConformanceReportOut(**validation_service.conformance_report(conn))
