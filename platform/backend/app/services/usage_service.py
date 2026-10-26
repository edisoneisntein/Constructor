"""Uso, cuotas y métricas por organización (§14, §19.6, §21 Fase 11/12)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from app.core.config import Settings
from app.core.errors import QuotaExceededError
from app.core.ids import utcnow_iso
from app.db import repositories as repo
from app.db.session import get_database


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def usage_snapshot(conn: sqlite3.Connection, *, organization_id: str) -> dict:
    """Uso actual de la organización (sin mutar estado)."""
    return {
        "organization_id": organization_id,
        "projects": repo.count_projects(conn, organization_id),
        "artifacts": repo.count_artifacts(conn, organization_id),
        "storage_bytes": repo.storage_bytes_used(conn, organization_id),
        "findings": repo.count_findings_for_org(conn, organization_id),
        "active_jobs": repo.count_active_jobs(conn, organization_id),
        "jobs_by_status": repo.count_jobs_by_status(conn, organization_id),
        "usage_totals": repo.usage_totals(conn, organization_id),
    }


def _percent(used: int, limit: int) -> float | None:
    if limit <= 0:
        return None
    return round(100.0 * used / limit, 2)


def quota_report(conn: sqlite3.Connection, settings: Settings, *, organization_id: str) -> dict:
    """Uso frente a las cuotas configuradas, con porcentaje consumido."""
    usage = usage_snapshot(conn, organization_id=organization_id)
    return {
        **usage,
        "quotas": {
            "projects": {
                "used": usage["projects"],
                "limit": settings.org_max_projects,
                "percent": _percent(usage["projects"], settings.org_max_projects),
            },
            "storage_bytes": {
                "used": usage["storage_bytes"],
                "limit": settings.org_max_storage_bytes,
                "percent": _percent(usage["storage_bytes"], settings.org_max_storage_bytes),
            },
            "concurrent_jobs": {
                "used": usage["active_jobs"],
                "limit": settings.org_max_concurrent_jobs,
                "percent": _percent(usage["active_jobs"], settings.org_max_concurrent_jobs),
            },
        },
    }


def metrics_summary(conn: sqlite3.Connection, *, organization_id: str) -> dict:
    """Resumen operativo de jobs: estados, totales y duración media observable."""
    jobs = repo.list_org_jobs(conn, organization_id)
    durations: list[float] = []
    for job in jobs:
        started = _parse_iso(job.get("started_at"))
        finished = _parse_iso(job.get("finished_at"))
        if started and finished and finished >= started:
            durations.append((finished - started).total_seconds())
    by_status = repo.count_jobs_by_status(conn, organization_id)
    finished = sum(count for status, count in by_status.items() if status in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"})
    failed = by_status.get("FAILED", 0) + by_status.get("CANCELLED", 0)
    return {
        "organization_id": organization_id,
        "generated_at": utcnow_iso(),
        "jobs_total": sum(by_status.values()),
        "jobs_by_status": by_status,
        "jobs_finished": finished,
        "jobs_failed_or_cancelled": failed,
        "avg_duration_seconds": round(sum(durations) / len(durations), 3) if durations else None,
        "durations_observed": len(durations),
    }


def enforce_project_quota(conn: sqlite3.Connection, settings: Settings, *, organization_id: str) -> None:
    used = repo.count_projects(conn, organization_id)
    if settings.org_max_projects > 0 and used >= settings.org_max_projects:
        raise QuotaExceededError(
            "Se alcanzó el máximo de proyectos de la organización.",
            details={"resource": "projects", "used": used, "limit": settings.org_max_projects},
        )


def enforce_storage_quota(
    conn: sqlite3.Connection, settings: Settings, *, organization_id: str, incoming_bytes: int
) -> None:
    used = repo.storage_bytes_used(conn, organization_id)
    if settings.org_max_storage_bytes > 0 and used + incoming_bytes > settings.org_max_storage_bytes:
        raise QuotaExceededError(
            "La carga supera el almacenamiento disponible de la organización.",
            details={
                "resource": "storage_bytes",
                "used": used,
                "incoming": incoming_bytes,
                "limit": settings.org_max_storage_bytes,
            },
        )


def enforce_concurrent_jobs_quota(
    conn: sqlite3.Connection, settings: Settings, *, organization_id: str
) -> None:
    used = repo.count_active_jobs(conn, organization_id)
    if settings.org_max_concurrent_jobs > 0 and used >= settings.org_max_concurrent_jobs:
        raise QuotaExceededError(
            "Se alcanzó el máximo de análisis concurrentes de la organización.",
            details={"resource": "concurrent_jobs", "used": used, "limit": settings.org_max_concurrent_jobs},
        )


def organization_health() -> dict:
    """Estado de preparación (readiness): comprueba la base de datos."""
    database = get_database()
    try:
        connection = database.connect()
        connection.execute("SELECT 1")
        connection.close()
        return {"database": "ok"}
    except Exception as error:  # pragma: no cover - fallo real de infraestructura
        return {"database": f"error: {type(error).__name__}"}
