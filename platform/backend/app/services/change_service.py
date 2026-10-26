"""Servicio de gestión de cambios (§15).

Ciclo de vida de un conjunto de cambios:

    PROPOSED → APPROVED → APPLIED → VALIDATED → ROLLED_BACK

Reglas verificadas por este servicio (§15):

- Toda modificación registra workspace, hashes (base y resultado), manifiesto de
  archivos, añadidos/modificados/eliminados, diff unificado, motivo, regla o
  tarea que lo produjo, pruebas asociadas, aprobaciones y resultado de validación.
- Antes de aplicar un parche se verifica que el archivo destino no haya cambiado
  respecto del hash base registrado; si cambió, se rechaza con ``change_conflict``.
- Se conserva un registro suficiente para comparar versiones y revertir
  modificaciones locales (reversión con verificación de hash aplicado).
- Los efectos sobre bases de datos o servicios externos se declaran como no
  revertibles (no se afirman reversibles, §15).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.adapters.rea_adapter import build_rea_adapter
from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.ids import new_id, utcnow_iso
from app.core.logging import get_logger
from app.core.sandbox import subprocess_limits
from app.db import repositories as repo
from app.engines.analysis.source_analysis import run_source_analysis
from app.engines.change_management.change_engine import (
    FileChange,
    classify_change,
    looks_like_test,
    safe_relative_path,
)
from app.engines.ingestion.artifact_store import sha256_bytes
from app.engines.ingestion.safe_zip import ExtractionLimits, safe_extract

_logger = get_logger("change_service")

REVERSIBLE_STATES = {"APPLIED", "VALIDATED"}
EXTERNAL_EFFECTS_NOTE = (
    "Los cambios afectan únicamente a archivos locales del workspace. No se "
    "modifican bases de datos ni servicios externos; por tanto no se requiere "
    "procedimiento de compensación externa (§15)."
)


@dataclass
class FileEdit:
    path: str
    new_content: str | None


def _limits(settings: Settings) -> ExtractionLimits:
    return ExtractionLimits(
        max_entries=settings.max_archive_entries,
        max_total_bytes=settings.max_extracted_bytes,
        max_file_bytes=settings.max_single_file_bytes,
        max_compression_ratio=settings.max_compression_ratio,
        max_path_depth=settings.max_path_depth,
    )


def _within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _write(root: Path, relative: str, data: bytes) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def _read_or_none(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _hash_or_none(data: bytes | None) -> str | None:
    return sha256_bytes(data) if data is not None else None


def create_change_set(
    conn: sqlite3.Connection,
    *,
    settings: Settings,
    job: dict,
    user_id: str,
    reason: str,
    produced_by_rule: str,
    edits: list[FileEdit],
) -> dict:
    if not reason.strip():
        raise ValidationAppError("El cambio debe declarar un motivo (§15).")
    if not produced_by_rule.strip():
        raise ValidationAppError("El cambio debe declarar la regla o tarea que lo produjo (§15).")
    if not edits:
        raise ValidationAppError("El conjunto de cambios no contiene archivos.")

    organization_id = job["organization_id"]
    artifact = repo.get_artifact(conn, job["artifact_id"], organization_id)
    if artifact is None:
        raise NotFoundError("Artefacto del análisis no encontrado.")

    change_set_id = new_id("chg")
    base = settings.storage_root / "change_sets" / change_set_id
    workspace = base / "workspace"
    before_root = base / "before"
    after_root = base / "after"
    workspace.mkdir(parents=True, exist_ok=True)
    safe_extract(Path(artifact["storage_path"]), workspace, _limits(settings))

    changes: list[FileChange] = []
    for edit in edits:
        relative = safe_relative_path(edit.path)
        target = workspace / relative
        if not _within(workspace, target):
            raise ValidationAppError(f"Ruta fuera del workspace: {edit.path}")
        before = _read_or_none(target)
        after = edit.new_content.encode("utf-8") if edit.new_content is not None else None
        change = classify_change(relative, before, after)
        if change is not None:
            changes.append(change)

    if not changes:
        raise ValidationAppError("El conjunto de cambios no produce diferencias efectivas.")

    for change in changes:
        if change.before is not None:
            _write(before_root, change.path, change.before)
        if change.after is not None:
            _write(after_root, change.path, change.after)

    associated_tests = [change.path for change in changes if looks_like_test(change.path)]
    now = utcnow_iso()
    change_set = repo.create_change_set(
        conn,
        change_set_id=change_set_id,
        analysis_id=job["id"],
        project_id=job["project_id"],
        organization_id=organization_id,
        workspace_path=str(workspace),
        before_root=str(before_root),
        after_root=str(after_root),
        base_artifact_sha256=artifact["sha256"],
        reason=reason.strip(),
        produced_by_rule=produced_by_rule.strip(),
        status="PROPOSED",
        reversible=True,
        external_effects=EXTERNAL_EFFECTS_NOTE,
        associated_tests=json.dumps(associated_tests, ensure_ascii=False),
        created_by=user_id,
        created_at=now,
    )
    repo.insert_change_files(
        conn,
        [
            {
                "id": new_id("chf"),
                "change_set_id": change_set_id,
                "path": change.path,
                "change_type": change.change_type,
                "base_sha256": change.base_sha256,
                "new_sha256": change.new_sha256,
                "unified_diff": change.unified_diff,
                "created_at": now,
            }
            for change in changes
        ],
    )
    repo.record_audit(
        conn,
        action="change.create",
        created_at=now,
        organization_id=organization_id,
        user_id=user_id,
        target_type="change_set",
        target_id=change_set_id,
        metadata={"files": len(changes)},
    )
    conn.commit()
    return change_set  # type: ignore[return-value]


def get_change_set_detail(conn: sqlite3.Connection, *, change_set_id: str, organization_id: str) -> dict:
    change_set = repo.get_change_set(conn, change_set_id, organization_id)
    if change_set is None:
        raise NotFoundError("Conjunto de cambios no encontrado.")
    payload = dict(change_set)
    payload["files"] = repo.list_change_files(conn, change_set_id)
    payload["approvals"] = repo.list_change_approvals(conn, change_set_id)
    return payload


def list_change_sets(conn: sqlite3.Connection, *, analysis_id: str, organization_id: str) -> list[dict]:
    return repo.list_change_sets(conn, analysis_id, organization_id)


def approve_change_set(
    conn: sqlite3.Connection,
    *,
    change_set_id: str,
    organization_id: str,
    user_id: str,
    decision: str,
    comment: str | None,
) -> dict:
    change_set = repo.get_change_set(conn, change_set_id, organization_id)
    if change_set is None:
        raise NotFoundError("Conjunto de cambios no encontrado.")
    if change_set["status"] != "PROPOSED":
        raise ConflictError(f"No se puede aprobar un cambio en estado {change_set['status']}.")
    if decision not in {"approved", "rejected"}:
        raise ValidationAppError("Decisión inválida (use 'approved' o 'rejected').")
    now = utcnow_iso()
    repo.add_change_approval(
        conn,
        change_set_id=change_set_id,
        user_id=user_id,
        decision=decision,
        comment=comment,
        created_at=now,
    )
    if decision == "approved":
        repo.update_change_set(
            conn,
            change_set_id,
            status="APPROVED",
            approved_by=user_id,
            approved_at=now,
            updated_at=now,
        )
    else:
        repo.update_change_set(conn, change_set_id, status="REJECTED", updated_at=now)
    repo.record_audit(
        conn,
        action=f"change.{decision}",
        created_at=now,
        organization_id=organization_id,
        user_id=user_id,
        target_type="change_set",
        target_id=change_set_id,
    )
    conn.commit()
    return get_change_set_detail(conn, change_set_id=change_set_id, organization_id=organization_id)


def apply_change_set(conn: sqlite3.Connection, *, change_set_id: str, organization_id: str, user_id: str) -> dict:
    change_set = repo.get_change_set(conn, change_set_id, organization_id)
    if change_set is None:
        raise NotFoundError("Conjunto de cambios no encontrado.")
    if change_set["status"] != "APPROVED":
        raise ConflictError(f"No se puede aplicar un cambio en estado {change_set['status']}.")
    files = repo.list_change_files(conn, change_set_id)
    workspace = Path(change_set["workspace_path"])
    after_root = Path(change_set["after_root"])

    # Verificación previa: ningún archivo destino cambió respecto del base (§15).
    for item in files:
        target = workspace / item["path"]
        current_sha = _hash_or_none(_read_or_none(target))
        if current_sha != item["base_sha256"]:
            raise ConflictError(
                f"El archivo '{item['path']}' cambió desde la generación del cambio.",
                code="change_conflict",
                details={"path": item["path"], "expected": item["base_sha256"], "found": current_sha},
            )

    for item in files:
        target = workspace / item["path"]
        if item["change_type"] == "DELETED":
            if target.exists():
                target.unlink()
            repo.set_change_file_applied(conn, item["id"], None)
        else:
            _write(workspace, item["path"], (after_root / item["path"]).read_bytes())
            repo.set_change_file_applied(conn, item["id"], item["new_sha256"])

    now = utcnow_iso()
    repo.update_change_set(conn, change_set_id, status="APPLIED", applied_at=now, updated_at=now)
    repo.record_audit(
        conn,
        action="change.apply",
        created_at=now,
        organization_id=organization_id,
        user_id=user_id,
        target_type="change_set",
        target_id=change_set_id,
    )
    conn.commit()
    return get_change_set_detail(conn, change_set_id=change_set_id, organization_id=organization_id)


def validate_change_set(
    conn: sqlite3.Connection, *, settings: Settings, change_set_id: str, organization_id: str, user_id: str
) -> dict:
    change_set = repo.get_change_set(conn, change_set_id, organization_id)
    if change_set is None:
        raise NotFoundError("Conjunto de cambios no encontrado.")
    if change_set["status"] != "APPLIED":
        raise ConflictError(f"No se puede validar un cambio en estado {change_set['status']}.")
    workspace = Path(change_set["workspace_path"])
    limits = subprocess_limits(settings)
    rea = build_rea_adapter(
        settings.rea_binary,
        enabled=settings.rea_enabled,
        timeout_seconds=settings.rea_timeout_seconds,
        limits=limits,
    )
    outcome = run_source_analysis(
        workspace,
        analysis_id=change_set_id,
        project_id=change_set["project_id"],
        organization_id=organization_id,
        created_at=utcnow_iso(),
        analysis_max_file_bytes=settings.analysis_max_file_bytes,
        js_timeout_seconds=settings.rea_timeout_seconds,
        rea=rea,
        deep_analysis=False,
        sandbox_limits=limits,
    )
    result = {
        "status": "COMPLETED_WITH_LIMITATIONS" if outcome.limitations else "COMPLETED",
        "findings_count": len(outcome.findings),
        "node_count": len(outcome.nodes),
        "edge_count": len(outcome.edges),
        "files_analyzed": int(outcome.summary.get("files_analyzed", 0)),
        "limitations": outcome.limitations,
    }
    now = utcnow_iso()
    repo.update_change_set(
        conn,
        change_set_id,
        status="VALIDATED",
        validation_result=json.dumps(result, ensure_ascii=False),
        validated_at=now,
        updated_at=now,
    )
    repo.record_audit(
        conn,
        action="change.validate",
        created_at=now,
        organization_id=organization_id,
        user_id=user_id,
        target_type="change_set",
        target_id=change_set_id,
        metadata=result,
    )
    conn.commit()
    return get_change_set_detail(conn, change_set_id=change_set_id, organization_id=organization_id)


def rollback_change_set(conn: sqlite3.Connection, *, change_set_id: str, organization_id: str, user_id: str) -> dict:
    change_set = repo.get_change_set(conn, change_set_id, organization_id)
    if change_set is None:
        raise NotFoundError("Conjunto de cambios no encontrado.")
    if change_set["status"] not in REVERSIBLE_STATES:
        raise ConflictError(f"No se puede revertir un cambio en estado {change_set['status']}.")
    files = repo.list_change_files(conn, change_set_id)
    workspace = Path(change_set["workspace_path"])
    before_root = Path(change_set["before_root"])

    # Verificación previa: ningún archivo aplicado cambió desde la aplicación.
    for item in files:
        target = workspace / item["path"]
        current_sha = _hash_or_none(_read_or_none(target))
        if current_sha != item["applied_sha256"]:
            raise ConflictError(
                f"El archivo '{item['path']}' cambió desde la aplicación del cambio.",
                code="change_conflict",
                details={"path": item["path"], "expected": item["applied_sha256"], "found": current_sha},
            )

    for item in files:
        target = workspace / item["path"]
        if item["change_type"] == "ADDED":
            if target.exists():
                target.unlink()
        else:
            _write(workspace, item["path"], (before_root / item["path"]).read_bytes())
        repo.set_change_file_applied(conn, item["id"], None)

    now = utcnow_iso()
    repo.update_change_set(conn, change_set_id, status="ROLLED_BACK", rolled_back_at=now, updated_at=now)
    repo.record_audit(
        conn,
        action="change.rollback",
        created_at=now,
        organization_id=organization_id,
        user_id=user_id,
        target_type="change_set",
        target_id=change_set_id,
    )
    conn.commit()
    return get_change_set_detail(conn, change_set_id=change_set_id, organization_id=organization_id)
