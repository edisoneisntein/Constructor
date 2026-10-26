"""Servicio de migración Gemini → NVIDIA NIM (§11, §12)."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.ids import new_id, utcnow_iso
from app.db import repositories as repo
from app.engines.ingestion.safe_zip import ExtractionLimits, safe_extract
from app.engines.migration import planner
from app.engines.migration.gemini_detector import detect_gemini_operations
from app.engines.migration.nim_client import NimClient, NimError
from app.engines.migration.nim_compat import assess_operations, matrix_summary

_MANIFEST_HINTS = ("requirements.txt", "requirements-dev.txt", "package.json", ".env.example")


def _limits(settings: Settings) -> ExtractionLimits:
    return ExtractionLimits(
        max_entries=settings.max_archive_entries,
        max_total_bytes=settings.max_extracted_bytes,
        max_file_bytes=settings.max_single_file_bytes,
        max_compression_ratio=settings.max_compression_ratio,
        max_path_depth=settings.max_path_depth,
    )


def create_migration_plan(
    conn: sqlite3.Connection,
    *,
    settings: Settings,
    project: dict,
    analysis: dict,
    user_id: str,
) -> dict:
    organization_id = project["organization_id"]
    artifact = repo.get_artifact(conn, analysis["artifact_id"], organization_id)
    if artifact is None:
        raise NotFoundError("Artefacto del análisis no encontrado.")

    plan_id = new_id("mig")
    workspace = settings.storage_root / "migrations" / plan_id / "workspace"
    try:
        safe_extract(Path(artifact["storage_path"]), workspace, _limits(settings))

        operations, limitations = detect_gemini_operations(
            workspace, max_file_bytes=settings.analysis_max_file_bytes
        )
        assessments = assess_operations(operations, settings)

        dependencies = repo.list_dependencies(conn, analysis["id"], organization_id)
        candidate_paths = {
            dep["source_file"] for dep in dependencies if dep.get("source_file")
        } | set(_MANIFEST_HINTS)
        existing = [rel for rel in candidate_paths if (workspace / rel).is_file()]
        file_contents = planner.load_file_contents(workspace, sorted(existing))

        plan = planner.build_plan(
            operations=operations,
            limitations=limitations,
            settings=settings,
            assessments=assessments,
            dependencies=dependencies,
            file_contents=file_contents,
        )
        if not operations:
            plan["limitations"].append(
                "No se detectaron integraciones ejecutables de Google Gemini en el código analizado."
            )
        summary = matrix_summary(assessments)

        now = utcnow_iso()
        created = repo.create_migration_plan(
            conn,
            plan_id=plan_id,
            project_id=project["id"],
            analysis_id=analysis["id"],
            organization_id=organization_id,
            source_provider=plan["source_provider"],
            target_provider=plan["target_provider"],
            status="COMPLETED",
            target_base_url=plan["target_base_url"],
            target_model=plan["target_model"],
            operation_count=len(operations),
            matrix_summary=json.dumps(summary, ensure_ascii=False),
            plan=json.dumps(plan, ensure_ascii=False),
            limitations=json.dumps(plan["limitations"], ensure_ascii=False),
            sources=json.dumps(plan["sources"], ensure_ascii=False),
            verified_at=plan["verified_at"],
            created_by=user_id,
            created_at=now,
        )
        repo.insert_migration_changes(
            conn,
            [
                {
                    "id": new_id("mgc"),
                    "plan_id": plan_id,
                    "change_ref": change["change_id"],
                    "kind": change["kind"],
                    "path": change["path"],
                    "action": change["action"],
                    "description": change["description"],
                    "diff": change["diff"],
                    "reversible": 1 if change["reversible"] else 0,
                    "rule_id": change["rule_id"],
                }
                for change in plan["changes"]
            ],
        )
        repo.record_audit(
            conn,
            action="migration.plan.create",
            created_at=now,
            organization_id=organization_id,
            user_id=user_id,
            target_type="migration_plan",
            target_id=plan_id,
            metadata={"operations": len(operations)},
        )
        conn.commit()
        return created  # type: ignore[return-value]
    finally:
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)


def get_migration_plan_detail(conn: sqlite3.Connection, *, plan_id: str, organization_id: str) -> dict:
    plan = repo.get_migration_plan(conn, plan_id, organization_id)
    if plan is None:
        raise NotFoundError("Plan de migración no encontrado.")
    payload = dict(plan)
    payload["changes"] = repo.list_migration_changes(conn, plan_id)
    return payload


def list_migration_plans(conn: sqlite3.Connection, *, project_id: str, organization_id: str) -> list[dict]:
    return repo.list_migration_plans(conn, project_id, organization_id)


def build_nim_client(settings: Settings, *, transport=None) -> NimClient:
    return NimClient(
        base_url=settings.nim_base_url,
        api_key=settings.nim_api_key,
        timeout_seconds=settings.nim_timeout_seconds,
        transport=transport,
        outbound_allowed_hosts=list(settings.outbound_allowed_hosts),
    )


def verify_nim_connection(settings: Settings, *, transport=None, probe_completion: bool = True) -> dict:
    """Comprueba credenciales y disponibilidad del modelo configurado en NIM (§12/§13).

    No registra la clave ni el contenido de la respuesta; solo metadatos.
    """

    report: dict = {
        "provider": "nvidia_nim",
        "configured": False,
        "base_url": settings.nim_base_url,
        "model": settings.nim_model,
        "reachable": False,
        "model_available": False,
        "models_count": 0,
        "sample_models": [],
        "completion_ok": False,
        "latency_ms": None,
        "error": None,
    }
    client = build_nim_client(settings, transport=transport)
    if not client.configured:
        report["error"] = "missing_api_key"
        return report
    report["configured"] = True
    try:
        models = client.list_models()
    except NimError as error:
        report["error"] = str(error)
        return report
    report["reachable"] = True
    report["models_count"] = len(models)
    report["model_available"] = settings.nim_model in models
    report["sample_models"] = models[:20]
    if probe_completion and report["model_available"]:
        try:
            result = client.chat(
                [{"role": "user", "content": "Respond with the single word: OK"}],
                model=settings.nim_model,
                max_tokens=256,
                temperature=0.0,
            )
            report["completion_ok"] = bool(result.content.strip())
            report["latency_ms"] = result.latency_ms
            report["usage"] = result.usage
        except NimError as error:
            report["error"] = str(error)
    return report


def require_analysis(conn: sqlite3.Connection, analysis_id: str, organization_id: str) -> dict:
    analysis = repo.get_job(conn, analysis_id, organization_id)
    if analysis is None:
        raise ValidationAppError("Análisis no encontrado.", status_code=404)
    return analysis
