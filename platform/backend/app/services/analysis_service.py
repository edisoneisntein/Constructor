"""Servicio de proyectos, ingesta y análisis (§5, §20)."""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.adapters.rea_adapter import build_rea_adapter
from app.core.config import Settings, get_settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnsafeArchiveError,
    ValidationAppError,
)
from app.core.ids import new_id, utcnow_iso
from app.core.logging import get_logger
from app.core.sandbox import subprocess_limits
from app.db import repositories as repo
from app.db.session import get_database
from app.engines.analysis.source_analysis import run_source_analysis
from app.engines.ingestion.artifact_store import store_artifact
from app.engines.ingestion.safe_zip import ExtractionLimits, safe_extract
from app.services.job_runner import get_job_runner
from app.services.usage_service import (
    enforce_concurrent_jobs_quota,
    enforce_project_quota,
    enforce_storage_quota,
)

_logger = get_logger("analysis_service")

PROGRESS_FORMULA = (
    "progress_percent = round(100 * files_analyzed / files_detected) durante la fase ANALYZING; "
    "100 tras construir el grafo. Se separa del estado de validación del resultado."
)


def create_project(conn: sqlite3.Connection, *, organization_id: str, user_id: str, name: str) -> dict:
    enforce_project_quota(conn, get_settings(), organization_id=organization_id)
    now = utcnow_iso()
    project = repo.create_project(
        conn, organization_id=organization_id, name=name, created_by=user_id, created_at=now
    )
    repo.record_audit(
        conn,
        action="project.create",
        created_at=now,
        organization_id=organization_id,
        user_id=user_id,
        target_type="project",
        target_id=project["id"],
    )
    return project


def ingest_source_zip(
    conn: sqlite3.Connection,
    *,
    settings: Settings,
    project: dict,
    user_id: str,
    filename: str,
    declared_mime: str | None,
    data: bytes,
) -> dict:
    if len(data) == 0:
        raise ValidationAppError("El archivo está vacío.")
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            "El archivo supera el límite de carga.",
            details={"size": len(data), "max": settings.max_upload_bytes},
        )
    enforce_storage_quota(
        conn, settings, organization_id=project["organization_id"], incoming_bytes=len(data)
    )
    stored = store_artifact(
        settings.storage_root,
        organization_id=project["organization_id"],
        filename=filename,
        data=data,
        declared_mime=declared_mime,
    )
    if stored.detected_mime != "application/zip":
        raise ValidationAppError(
            "En el MVP solo se aceptan archivos ZIP de código fuente.",
            details={"detected_mime": stored.detected_mime},
        )
    # Validación de seguridad antes de registrar (rechazo temprano de entradas peligrosas).
    limits = _limits(settings)
    from app.engines.ingestion.safe_zip import inspect_zip

    inspect_zip(Path(stored.storage_path), limits)
    now = utcnow_iso()
    artifact = repo.create_artifact(
        conn,
        project_id=project["id"],
        organization_id=project["organization_id"],
        kind=stored.kind,
        filename=stored.filename,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        detected_mime=stored.detected_mime,
        declared_mime=stored.declared_mime,
        storage_path=stored.storage_path,
        retention_policy="delete-after-analysis" if settings.workspace_retention_seconds <= 0 else "retain-1h",
        validation_state="VALID",
        created_at=now,
    )
    repo.record_audit(
        conn,
        action="artifact.ingest",
        created_at=now,
        organization_id=project["organization_id"],
        user_id=user_id,
        target_type="artifact",
        target_id=artifact["id"],
        metadata={"sha256": stored.sha256, "size": stored.size_bytes},
    )
    repo.record_usage(
        conn,
        organization_id=project["organization_id"],
        project_id=project["id"],
        metric="storage_bytes",
        quantity=stored.size_bytes,
        created_at=now,
    )
    return artifact


def _limits(settings: Settings) -> ExtractionLimits:
    return ExtractionLimits(
        max_entries=settings.max_archive_entries,
        max_total_bytes=settings.max_extracted_bytes,
        max_file_bytes=settings.max_single_file_bytes,
        max_compression_ratio=settings.max_compression_ratio,
        max_path_depth=settings.max_path_depth,
    )


def start_analysis(
    conn: sqlite3.Connection,
    *,
    project: dict,
    user_id: str,
    artifact_id: str,
    deep_analysis: bool,
) -> dict:
    artifact = repo.get_artifact(conn, artifact_id, project["organization_id"])
    if artifact is None or artifact["project_id"] != project["id"]:
        raise ValidationAppError("El artefacto no pertenece al proyecto.")
    enforce_concurrent_jobs_quota(conn, get_settings(), organization_id=project["organization_id"])
    now = utcnow_iso()
    job = repo.create_job(
        conn,
        project_id=project["id"],
        organization_id=project["organization_id"],
        artifact_id=artifact_id,
        created_by=user_id,
        status="QUEUED",
        created_at=now,
    )
    repo.record_audit(
        conn,
        action="analysis.start",
        created_at=now,
        organization_id=project["organization_id"],
        user_id=user_id,
        target_type="analysis",
        target_id=job["id"],
    )
    repo.record_usage(
        conn,
        organization_id=project["organization_id"],
        project_id=project["id"],
        metric="analysis_runs",
        quantity=1,
        created_at=now,
    )
    settings = get_settings()
    if settings.job_queue_backend == "external":
        # El trabajo queda en QUEUED; lo reclama un proceso trabajador (§4.3/§21).
        return repo.get_job(conn, job["id"], project["organization_id"])  # type: ignore[return-value]
    get_job_runner().submit(
        job["id"],
        lambda is_cancelled: run_analysis_job(
            job_id=job["id"],
            project_id=project["id"],
            organization_id=project["organization_id"],
            artifact_id=artifact_id,
            deep_analysis=deep_analysis,
            is_cancelled=is_cancelled,
            settings=settings,
        ),
    )
    return repo.get_job(conn, job["id"], project["organization_id"])  # type: ignore[return-value]


def run_analysis_job(
    *,
    job_id: str,
    project_id: str,
    organization_id: str,
    artifact_id: str,
    deep_analysis: bool,
    is_cancelled,
    settings: Settings,
    worker_id: str | None = None,
) -> None:
    database = get_database()
    conn = database.connect()

    def _heartbeat() -> None:
        if worker_id:
            repo.heartbeat_job(conn, job_id, worker_id=worker_id, now=utcnow_iso())
            conn.commit()

    workspace = settings.storage_root / "workspaces" / job_id
    try:
        repo.update_job(conn, job_id, status="ANALYZING", phase="extracting", started_at=utcnow_iso())
        _heartbeat()
        artifact = repo.get_artifact(conn, artifact_id, organization_id)
        if artifact is None:
            repo.update_job(conn, job_id, status="FAILED", error_code="artifact_missing", error_message="Artefacto no encontrado.", finished_at=utcnow_iso())
            conn.commit()
            return

        report = safe_extract(Path(artifact["storage_path"]), workspace, _limits(settings))

        def progress(phase: str, completed: int, total: int) -> None:
            repo.update_job(conn, job_id, phase=phase, progress_completed=completed, progress_total=total)
            _heartbeat()
            conn.commit()

        limits = subprocess_limits(settings)
        rea = build_rea_adapter(
            settings.rea_binary,
            enabled=settings.rea_enabled,
            timeout_seconds=settings.rea_timeout_seconds,
            limits=limits,
        )
        created_at = utcnow_iso()
        try:
            outcome = run_source_analysis(
                workspace,
                analysis_id=job_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                analysis_max_file_bytes=settings.analysis_max_file_bytes,
                js_timeout_seconds=settings.rea_timeout_seconds,
                rea=rea,
                deep_analysis=deep_analysis,
                is_cancelled=is_cancelled,
                progress=progress,
                sandbox_limits=limits,
            )
        except KeyboardInterrupt:
            repo.update_job(conn, job_id, status="CANCELLED", phase="cancelled", finished_at=utcnow_iso())
            conn.commit()
            repo.record_audit(conn, action="analysis.cancelled", created_at=utcnow_iso(), organization_id=organization_id, target_type="analysis", target_id=job_id)
            conn.commit()
            return

        if is_cancelled():
            repo.update_job(conn, job_id, status="CANCELLED", phase="cancelled", finished_at=utcnow_iso())
            conn.commit()
            return

        repo.update_job(conn, job_id, status="GRAPH_BUILDING", phase="persisting")
        conn.commit()
        with conn:
            if outcome.findings:
                repo.insert_findings(conn, outcome.findings)
            if outcome.nodes:
                repo.insert_nodes(conn, outcome.nodes)
            if outcome.edges:
                repo.insert_edges(conn, outcome.edges)
            if outcome.dependencies:
                repo.insert_dependencies(conn, outcome.dependencies)

        summary = dict(outcome.summary)
        summary["limitations"] = outcome.limitations
        summary["progress_formula"] = PROGRESS_FORMULA
        final_status = "COMPLETED_WITH_LIMITATIONS" if outcome.limitations else "COMPLETED"
        repo.update_job(
            conn,
            job_id,
            status=final_status,
            phase="done",
            result_summary=json.dumps(summary, ensure_ascii=False),
            finished_at=utcnow_iso(),
        )
        repo.record_usage(
            conn,
            organization_id=organization_id,
            project_id=project_id,
            metric="files_analyzed",
            quantity=int(summary.get("files_analyzed", 0)),
            created_at=utcnow_iso(),
        )
        repo.record_audit(
            conn,
            action="analysis.complete",
            created_at=utcnow_iso(),
            organization_id=organization_id,
            target_type="analysis",
            target_id=job_id,
            metadata={"status": final_status},
        )
        conn.commit()
    except UnsafeArchiveError as error:
        repo.update_job(
            conn,
            job_id,
            status="FAILED",
            error_code=error.code,
            error_message=error.message,
            finished_at=utcnow_iso(),
        )
        conn.commit()
    except Exception as error:  # noqa: BLE001
        _logger.exception("analysis_failed", extra={"job_id": job_id})
        repo.update_job(
            conn,
            job_id,
            status="FAILED",
            error_code="internal_error",
            error_message=str(error)[:500],
            finished_at=utcnow_iso(),
        )
        conn.commit()
    finally:
        # Limpieza de temporales (§20.15).
        try:
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
        finally:
            if not database.is_ephemeral:
                conn.close()


def cancel_analysis(conn: sqlite3.Connection, *, job: dict, organization_id: str) -> dict:
    if job["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS", "FAILED", "CANCELLED"}:
        return job
    repo.request_cancel(conn, job["id"], organization_id)
    if job["status"] in {"QUEUED"} and get_settings().job_queue_backend == "external":
        # Aún no reclamado: se cancela de inmediato sin worker.
        repo.update_job(conn, job["id"], status="CANCELLED", phase="cancelled", finished_at=utcnow_iso())
    elif job["status"] in {"QUEUED", "ANALYZING", "GRAPH_BUILDING"}:
        get_job_runner().request_cancel(job["id"])
        repo.update_job(conn, job["id"], status="CANCELLED", phase="cancelled", finished_at=utcnow_iso())
    # Si está RUNNING bajo un worker externo, la cooperación la observa el worker
    # mediante `cancel_requested`; no se sobreescribe el estado aquí.
    return repo.get_job(conn, job["id"], organization_id)  # type: ignore[return-value]


def build_analysis_summary(conn: sqlite3.Connection, *, analysis_id: str, organization_id: str) -> dict:
    job = repo.get_job(conn, analysis_id, organization_id)
    if job is None:
        raise ValidationAppError("Análisis no encontrado.", status_code=404)
    findings_total, _ = repo.list_findings(conn, analysis_id=analysis_id, organization_id=organization_id, limit=1)
    by_severity = repo.count_findings_by(conn, analysis_id=analysis_id, organization_id=organization_id, column="severity")
    by_category = repo.count_findings_by(conn, analysis_id=analysis_id, organization_id=organization_id, column="category")
    nodes = repo.list_nodes(conn, analysis_id, organization_id)
    edges = repo.list_edges(conn, analysis_id, organization_id)
    deps = repo.list_dependencies(conn, analysis_id, organization_id)
    summary = json.loads(job["result_summary"]) if job.get("result_summary") else {}
    languages = list((summary.get("languages") or {}).keys())
    finding_count = sum(by_severity.values())
    return {
        "job": job_public(job),
        "finding_count": finding_count,
        "findings_by_severity": by_severity,
        "findings_by_category": by_category,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "dependency_count": len(deps),
        "languages": languages,
        "files_analyzed": int(summary.get("files_analyzed", 0)),
        "progress_formula": PROGRESS_FORMULA,
    }


def job_public(job: dict) -> dict:
    payload = dict(job)
    payload["result_summary"] = json.loads(job["result_summary"]) if job.get("result_summary") else None
    payload.pop("cancel_requested", None)
    payload.pop("organization_id", None)
    payload.pop("created_by", None)
    return payload


def export_report(conn: sqlite3.Connection, *, analysis_id: str, organization_id: str, fmt: str) -> tuple[str, str]:
    summary = build_analysis_summary(conn, analysis_id=analysis_id, organization_id=organization_id)
    findings, _ = repo.list_findings(conn, analysis_id=analysis_id, organization_id=organization_id, limit=1000)
    nodes = repo.list_nodes(conn, analysis_id, organization_id)
    edges = repo.list_edges(conn, analysis_id, organization_id)
    dependencies = repo.list_dependencies(conn, analysis_id, organization_id)
    if fmt == "json":
        return "application/json", json.dumps(
            {
                "summary": summary,
                "findings": findings,
                "nodes": nodes,
                "edges": edges,
                "dependencies": dependencies,
            },
            ensure_ascii=False,
            indent=2,
        )
    if fmt != "markdown":
        raise ValidationAppError("Formato de exportación no soportado (use json o markdown).")
    lines: list[str] = []
    job = summary["job"]
    lines.append(f"# Informe de análisis {analysis_id}")
    lines.append("")
    lines.append(f"- Estado: {job['status']}")
    lines.append(f"- Archivos analizados: {summary['files_analyzed']}")
    lines.append(f"- Lenguajes: {', '.join(summary['languages']) or 'ninguno'}")
    lines.append(f"- Hallazgos: {summary['finding_count']}")
    lines.append(f"- Nodos: {summary['node_count']} · Aristas: {summary['edge_count']} · Dependencias: {summary['dependency_count']}")
    lines.append("")
    lines.append(f"_{summary['progress_formula']}_")
    lines.append("")
    lines.append("## Hallazgos")
    for finding in findings:
        location = finding.get("file_path") or "(sin archivo)"
        line = finding.get("line_start")
        where = f"{location}:{line}" if line else location
        lines.append(
            f"- [{finding['severity']}] ({finding['category']}) {finding['message']} — {where} "
            f"[evidencia: {finding['evidence_level']}]"
        )
    lines.append("")
    lines.append("## Limitaciones")
    for limitation in (job.get("result_summary") or {}).get("limitations", []):
        lines.append(f"- {limitation}")
    return "text/markdown", "\n".join(lines)


def _remove_storage_files(storage_path: str) -> bool:
    """Elimina los bytes del artefacto del almacenamiento dedicado."""
    target = Path(storage_path)
    removed = False
    if target.exists():
        target.unlink()
        removed = True
    parent = target.parent
    try:
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:  # pragma: no cover - carrera con otros procesos
        pass
    return removed


def _remove_storage_dir(root: Path, target: Path) -> bool:
    """Elimina un directorio temporal solo si está dentro de la raíz permitida."""
    try:
        resolved = target.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    if resolved.exists():
        shutil.rmtree(resolved, ignore_errors=True)
        return True
    return False


def delete_project(
    conn: sqlite3.Connection,
    *,
    project: dict,
    user_id: str,
    settings: Settings,
) -> dict:
    """Elimina un proyecto y todos sus datos asociados (§14.6).

    Se rechaza si hay análisis en curso para no competir con un trabajador
    activo. La base de datos se confirma antes de borrar bytes, de modo que un
    fallo de disco no deje registros apuntando a archivos inexistentes; los
    restos se registran en el log para purga posterior.
    """

    project_id = project["id"]
    organization_id = project["organization_id"]
    active_jobs = repo.count_active_jobs_for_project(conn, project_id, organization_id)
    if active_jobs:
        raise ConflictError(
            "El proyecto tiene análisis activos; cancélelos antes de eliminarlo.",
            code="project_has_active_jobs",
            details={"active_jobs": active_jobs},
        )

    artifacts = repo.list_project_artifacts_all(conn, project_id, organization_id)
    jobs = repo.list_jobs(conn, project_id, organization_id)
    change_sets = repo.list_project_change_sets(conn, project_id, organization_id)

    repo.record_audit(
        conn,
        action="project.delete",
        created_at=utcnow_iso(),
        organization_id=organization_id,
        user_id=user_id,
        target_type="project",
        target_id=project_id,
        metadata={
            "artifacts": len(artifacts),
            "analyses": len(jobs),
            "change_sets": len(change_sets),
        },
    )
    if not repo.delete_project(conn, project_id, organization_id):
        raise NotFoundError("Proyecto no encontrado.")
    conn.commit()

    for artifact in artifacts:
        try:
            _remove_storage_files(artifact["storage_path"])
        except OSError:
            # La fila ya no existe; el archivo huérfano se registra para purga.
            _logger.warning(
                "project_delete_storage_failed project_id=%s path=%s",
                project_id,
                artifact["storage_path"],
            )
    change_sets_root = settings.storage_root / "change_sets"
    for change_set in change_sets:
        _remove_storage_dir(change_sets_root, Path(change_set["workspace_path"]).parent)
    workspaces_root = settings.storage_root / "workspaces"
    for job in jobs:
        _remove_storage_dir(workspaces_root, workspaces_root / job["id"])

    _logger.info(
        "project_deleted project_id=%s artifacts=%s analyses=%s change_sets=%s",
        project_id,
        len(artifacts),
        len(jobs),
        len(change_sets),
    )
    return project


def delete_artifact(
    conn: sqlite3.Connection, *, artifact_id: str, organization_id: str, user_id: str
) -> dict:
    """Elimina un artefacto de forma explícita (§14.6): borra bytes y marca baja lógica."""
    artifact = repo.get_artifact(conn, artifact_id, organization_id)
    if artifact is None or artifact.get("deleted_at"):
        raise ValidationAppError("Artefacto no encontrado.")
    removed = _remove_storage_files(artifact["storage_path"])
    repo.mark_artifact_deleted(conn, artifact_id, organization_id, utcnow_iso())
    repo.record_audit(
        conn,
        action="artifact.delete",
        created_at=utcnow_iso(),
        organization_id=organization_id,
        user_id=user_id,
        target_type="artifact",
        target_id=artifact_id,
    )
    _logger.info("artifact_deleted artifact_id=%s bytes_removed=%s", artifact_id, removed)
    updated = repo.get_artifact(conn, artifact_id, organization_id)
    return updated or artifact


def purge_expired_artifacts(
    conn: sqlite3.Connection, settings: Settings, *, now: str | None = None
) -> list[str]:
    """Aplica la política de retención (§14.6) eliminando artefactos caducados.

    La caducidad se calcula con ``workspace_retention_seconds``; un valor <= 0
    desactiva la purga automática (los artefactos con política
    ``delete-after-analysis`` se eliminan en el momento de la baja explícita).
    """
    retention = settings.workspace_retention_seconds
    if retention <= 0:
        return []
    reference = _parse_iso(now or utcnow_iso())
    purged: list[str] = []
    for artifact in repo.list_retained_artifacts(conn):
        created = _parse_iso(artifact["created_at"])
        if (reference - created).total_seconds() < retention:
            continue
        _remove_storage_files(artifact["storage_path"])
        repo.mark_artifact_deleted(conn, artifact["id"], artifact["organization_id"], utcnow_iso())
        repo.record_audit(
            conn,
            action="artifact.retention_purge",
            created_at=utcnow_iso(),
            organization_id=artifact["organization_id"],
            target_type="artifact",
            target_id=artifact["id"],
        )
        purged.append(artifact["id"])
    return purged


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
