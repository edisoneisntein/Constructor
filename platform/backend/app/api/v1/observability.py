"""Observabilidad, uso y cuotas por organización (§14, §19.6, §21 Fase 11/12)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ActiveOrganization, Connection, require_role
from app.core.config import get_settings
from app.schemas.models import MetricsOut, Role, UsageOut
from app.services import usage_service

router = APIRouter(tags=["observability"])


@router.get("/observability/metrics", response_model=MetricsOut)
def get_metrics(organization: ActiveOrganization, conn: Connection) -> MetricsOut:
    require_role(organization, Role.viewer)
    return MetricsOut(**usage_service.metrics_summary(conn, organization_id=organization["id"]))


@router.get("/observability/usage", response_model=UsageOut)
def get_usage(organization: ActiveOrganization, conn: Connection) -> UsageOut:
    require_role(organization, Role.viewer)
    report = usage_service.quota_report(conn, get_settings(), organization_id=organization["id"])
    return UsageOut(**report)
