"""Análisis de aplicaciones compiladas (§6.2)."""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.api.deps import ActiveOrganization, Connection, CurrentUser, require_role
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.db import repositories as repo
from app.schemas.models import (
    ArtifactOut,
    BinaryAnalysisOut,
    BinaryAnalyzeRequest,
    BinaryCompareOut,
    BinaryCompareRequest,
    Role,
)
from app.services import binary_service

router = APIRouter(tags=["binaries"])


def _require_project(conn, project_id: str, organization_id: str) -> dict:
    project = repo.get_project(conn, project_id, organization_id)
    if project is None:
        raise NotFoundError("Proyecto no encontrado.")
    return project


def _artifact_out(artifact: dict) -> ArtifactOut:
    return ArtifactOut(
        id=artifact["id"],
        project_id=artifact["project_id"],
        kind=artifact["kind"],
        filename=artifact["filename"],
        size_bytes=artifact["size_bytes"],
        sha256=artifact["sha256"],
        detected_mime=artifact["detected_mime"],
        declared_mime=artifact["declared_mime"],
        validation_state=artifact["validation_state"],
        retention_policy=artifact["retention_policy"],
        created_at=artifact["created_at"],
    )


@router.post("/projects/{project_id}/binaries", response_model=ArtifactOut, status_code=201)
async def upload_binary(
    project_id: str,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
    file: UploadFile = File(...),
) -> ArtifactOut:
    require_role(organization, Role.developer)
    project = _require_project(conn, project_id, organization["id"])
    settings: Settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        from app.core.errors import PayloadTooLargeError

        raise PayloadTooLargeError("El archivo supera el límite de carga.")
    artifact = binary_service.ingest_binary(
        conn,
        settings=settings,
        project=project,
        user_id=user["id"],
        filename=file.filename or "binary.bin",
        declared_mime=file.content_type,
        data=data,
    )
    return _artifact_out(artifact)


@router.post(
    "/projects/{project_id}/binary-analyses", response_model=BinaryAnalysisOut, status_code=201
)
def analyze_binary(
    project_id: str,
    payload: BinaryAnalyzeRequest,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> BinaryAnalysisOut:
    require_role(organization, Role.developer)
    project = _require_project(conn, project_id, organization["id"])
    result = binary_service.analyze_binary_artifact(
        conn,
        settings=get_settings(),
        project=project,
        artifact_id=payload.artifact_id,
        user_id=user["id"],
    )
    return BinaryAnalysisOut(**result)


@router.get("/projects/{project_id}/binary-analyses", response_model=list[BinaryAnalysisOut])
def list_binary_analyses(
    project_id: str, organization: ActiveOrganization, conn: Connection
) -> list[BinaryAnalysisOut]:
    require_role(organization, Role.viewer)
    _require_project(conn, project_id, organization["id"])
    return [
        BinaryAnalysisOut(**item)
        for item in binary_service.list_binary_analyses(
            conn, project_id=project_id, organization_id=organization["id"]
        )
    ]


@router.get("/binary-analyses/{analysis_id}", response_model=BinaryAnalysisOut)
def get_binary_analysis(
    analysis_id: str, organization: ActiveOrganization, conn: Connection
) -> BinaryAnalysisOut:
    require_role(organization, Role.viewer)
    return BinaryAnalysisOut(
        **binary_service.get_binary_analysis(
            conn, analysis_id=analysis_id, organization_id=organization["id"]
        )
    )


@router.post("/binary-analyses/compare", response_model=BinaryCompareOut)
def compare_binary_analyses(
    payload: BinaryCompareRequest, organization: ActiveOrganization, conn: Connection
) -> BinaryCompareOut:
    require_role(organization, Role.viewer)
    return BinaryCompareOut(
        **binary_service.compare_analyses(
            conn,
            left_id=payload.left_id,
            right_id=payload.right_id,
            organization_id=organization["id"],
        )
    )
