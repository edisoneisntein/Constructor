"""Endpoints de generación/reparación de código asistida por IA (§10)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ActiveOrganization, Connection, CurrentUser, require_role
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db import repositories as repo
from app.schemas.models import GenerationCreate, GenerationOut, Role
from app.services import generation_service

router = APIRouter(tags=["generation"])


@router.post("/analyses/{analysis_id}/generations", response_model=GenerationOut, status_code=201)
def create_generation(
    analysis_id: str,
    payload: GenerationCreate,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> GenerationOut:
    require_role(organization, Role.developer)
    job = repo.get_job(conn, analysis_id, organization["id"])
    if job is None:
        raise NotFoundError("Análisis no encontrado.")
    result = generation_service.create_generation(
        conn,
        settings=get_settings(),
        job=job,
        user_id=user["id"],
        instruction=payload.instruction,
        target_path=payload.target_path,
        mode=payload.mode,
        ai_consent=payload.ai_consent,
    )
    return GenerationOut(**result)
