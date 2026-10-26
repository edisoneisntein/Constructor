"""Agregador de la API v1 y metadatos del producto (§0, §17)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    binaries,
    changes,
    generations,
    migrations,
    observability,
    organizations,
    projects,
    validation,
)
from app.core.config import get_settings
from app.engines.binary_analysis.formats import SUPPORTED_FORMATS
from app.core.execution_profiles import current_profile_spec
from app.core.sandbox import limits_supported

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(changes.router)
api_router.include_router(migrations.router)
api_router.include_router(observability.router)
api_router.include_router(generations.router)
api_router.include_router(validation.router)
api_router.include_router(binaries.router)


@api_router.get("/meta", tags=["meta"])
def meta() -> dict:
    settings = get_settings()
    return {
        "product_name": settings.product_name,
        "product_short_name": settings.product_short_name,
        "product_slug": settings.product_slug,
        "environment": settings.environment,
        "supported_languages": ["python", "typescript", "javascript"],
        "ingestion_formats": ["application/zip"],
        "binary_formats": sorted(SUPPORTED_FORMATS),
        "limits": {
            "max_upload_bytes": settings.max_upload_bytes,
            "max_extracted_bytes": settings.max_extracted_bytes,
            "max_archive_entries": settings.max_archive_entries,
            "max_compression_ratio": settings.max_compression_ratio,
        },
        "capabilities": {
            "static_source_analysis": "IMPLEMENTED",
            "architecture_graph": "IMPLEMENTED",
            "change_management": "IMPLEMENTED",
            "rea_adapter": "IMPLEMENTED" if settings.rea_enabled else "DISABLED",
            "binary_analysis": "PARTIALLY_IMPLEMENTED",
            "binary_analysis_advanced": "PROPOSED_NOT_IMPLEMENTED",
            "gemini_to_nim_migration": "PARTIALLY_IMPLEMENTED",
            "nim_integration": "IMPLEMENTED" if settings.nim_api_key else "DISABLED",
            "ai_code_generation": "IMPLEMENTED" if settings.nim_api_key else "DISABLED",
            "implementation_validator": "IMPLEMENTED",
            "artifact_retention_and_deletion": "IMPLEMENTED",
            "project_deletion": "IMPLEMENTED",
            "execution_profiles": "IMPLEMENTED",
            "outbound_network_guard": "IMPLEMENTED",
            "observability": "IMPLEMENTED",
            "organization_quotas": "IMPLEMENTED",
            "rate_limiting": (
                "IMPLEMENTED" if settings.rate_limit_backend == "database" else "PARTIALLY_IMPLEMENTED"
            ),
            "external_job_workers": "IMPLEMENTED" if settings.job_queue_backend == "external" else "DISABLED",
            "billing": "PROPOSED_NOT_IMPLEMENTED",
        },
        "quotas": {
            "org_max_projects": settings.org_max_projects,
            "org_max_storage_bytes": settings.org_max_storage_bytes,
            "org_max_concurrent_jobs": settings.org_max_concurrent_jobs,
            "rate_limit_api_per_minute": settings.rate_limit_api_per_minute,
            "rate_limit_auth_per_minute": settings.rate_limit_auth_per_minute,
        },
        "job_queue": {
            "backend": settings.job_queue_backend,
            "stale_after_seconds": settings.job_stale_after_seconds,
            "max_attempts": settings.job_max_attempts,
        },
        "rate_limit": {
            "backend": settings.rate_limit_backend,
            "api_per_minute": settings.rate_limit_api_per_minute,
            "auth_per_minute": settings.rate_limit_auth_per_minute,
        },
        "ai": {
            "provider": "nvidia_nim",
            "configured": bool(settings.nim_api_key),
            "base_url": settings.nim_base_url,
            "model": settings.nim_model,
            "endpoints": {"chat": "/chat/completions", "models": "/models"},
        },
        "security": {
            "execution": current_profile_spec(settings),
            "resource_limits_supported": limits_supported(),
            "limits": {
                "sandbox_cpu_seconds": settings.sandbox_cpu_seconds,
                "sandbox_max_memory_mb": settings.sandbox_max_memory_mb,
                "sandbox_max_file_bytes": settings.sandbox_max_file_bytes,
                "outbound_allowed_hosts": settings.outbound_allowed_hosts,
            },
        },
    }
