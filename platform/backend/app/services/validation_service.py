"""Servicio del Implementation Validator.

Orquesta el registro de requisitos, la ejecución de comprobaciones con evidencia
y el informe de conformidad. Es **independiente** del agente que modifica el
código: no reutiliza resultados antiguos como prueba de la versión actual (cada
ejecución registra el hash del código validado).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.ids import new_id, utcnow_iso
from app.core.logging import get_logger
from app.db import repositories as repo
from app.engines.validation import registry as registry_module
from app.engines.validation.engine import (
    STATUS_BLOCKED,
    STATUS_FAIL,
    STATUS_NOT_RUN,
    STATUS_PARTIAL,
    STATUS_PASS,
    compute_code_hash,
    evaluate_requirement,
)

_logger = get_logger("validation_service")

TERMINAL_STATUSES = {STATUS_PASS, STATUS_FAIL, STATUS_PARTIAL, STATUS_BLOCKED, STATUS_NOT_RUN}


def sync_registry(conn: sqlite3.Connection, *, registry_path: Path | None = None) -> int:
    requirements = registry_module.load_requirements(registry_path)
    now = utcnow_iso()
    for requirement in requirements:
        source = requirement.get("source") or {}
        repo.upsert_validation_requirement(
            conn,
            requirement_id=requirement["id"],
            title=requirement["title"],
            description=requirement["description"],
            source_document=source.get("document"),
            source_section=source.get("section"),
            source_page=source.get("page"),
            acceptance_criteria=json.dumps(requirement["acceptance_criteria"], ensure_ascii=False),
            checks=json.dumps(requirement["checks"], ensure_ascii=False),
            dependencies=json.dumps(requirement.get("dependencies", []), ensure_ascii=False),
            related_files=json.dumps(requirement.get("related_files", []), ensure_ascii=False),
            updated_at=now,
        )
    conn.commit()
    return len(requirements)


def list_requirements(conn: sqlite3.Connection) -> list[dict]:
    sync_registry(conn)
    return repo.list_validation_requirements(conn)


def get_requirement(conn: sqlite3.Connection, requirement_id: str) -> dict:
    sync_registry(conn)
    requirement = repo.get_validation_requirement(conn, requirement_id)
    if requirement is None:
        raise NotFoundError(f"Requisito no encontrado: {requirement_id}")
    return requirement


def run_validation(
    conn: sqlite3.Connection,
    *,
    settings: Settings,
    user_id: str | None,
    requirement_ids: list[str] | None = None,
    workspace: Path | None = None,
    registry_path: Path | None = None,
) -> dict:
    sync_registry(conn, registry_path=registry_path)
    all_requirements = repo.list_validation_requirements(conn)
    if not all_requirements:
        raise ValidationAppError("El registro de requisitos está vacío.")

    if requirement_ids:
        selected = [r for r in all_requirements if r["id"] in set(requirement_ids)]
        missing = set(requirement_ids) - {r["id"] for r in selected}
        if missing:
            raise ValidationAppError(f"Requisitos no encontrados: {sorted(missing)}")
    else:
        selected = all_requirements

    root = workspace or registry_module.workspace_root()
    code_hash = compute_code_hash(root)
    scope = "all" if not requirement_ids else ",".join(sorted(requirement_ids))

    run_id = new_id("vrun")
    started_at = utcnow_iso()
    started_monotonic = time.monotonic()
    repo.create_validation_run(
        conn,
        run_id=run_id,
        scope=scope,
        status="RUNNING",
        code_hash=code_hash,
        environment=settings.environment,
        requested_by=user_id,
        started_at=started_at,
    )
    conn.commit()

    summary = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_PARTIAL: 0, STATUS_BLOCKED: 0, STATUS_NOT_RUN: 0}
    result_rows: list[dict] = []
    evidence_rows: list[dict] = []

    for requirement in selected:
        outcome = evaluate_requirement(requirement, root, settings)
        if outcome.status not in TERMINAL_STATUSES:  # defensivo
            outcome.status = STATUS_NOT_RUN
        summary[outcome.status] = summary.get(outcome.status, 0) + 1

        result_id = new_id("vres")
        result_rows.append(
            {
                "id": result_id,
                "run_id": run_id,
                "requirement_id": requirement["id"],
                "status": outcome.status,
                "checks_total": outcome.checks_total,
                "checks_passed": outcome.checks_passed,
                "checks_failed": outcome.checks_failed,
                "checks_skipped": outcome.checks_skipped,
                "criteria_met": json.dumps(outcome.criteria_met, ensure_ascii=False),
                "limitations": json.dumps(outcome.limitations, ensure_ascii=False),
                "created_at": utcnow_iso(),
            }
        )
        for result in outcome.results:
            evidence_rows.append(
                {
                    "id": new_id("vevd"),
                    "run_id": run_id,
                    "result_id": result_id,
                    "requirement_id": requirement["id"],
                    "check_id": result.check_id,
                    "check_type": result.check_type,
                    "criterion": result.criterion,
                    "target": result.target,
                    "status": result.status,
                    "passed": 1 if result.passed else 0,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                    "command": result.command,
                    "output": result.output,
                    "limitations": json.dumps(result.limitations, ensure_ascii=False),
                    "created_at": utcnow_iso(),
                }
            )

    repo.insert_validation_results(conn, result_rows)
    repo.insert_validation_evidence(conn, evidence_rows)

    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    run_status = "COMPLETED"
    limitations = []
    if summary[STATUS_BLOCKED]:
        limitations.append(f"{summary[STATUS_BLOCKED]} requisito(s) bloqueado(s): no se pudo comprobar.")
    repo.finish_validation_run(
        conn,
        run_id,
        status=run_status,
        summary=json.dumps(summary, ensure_ascii=False),
        finished_at=utcnow_iso(),
        duration_ms=duration_ms,
        limitations=json.dumps(limitations, ensure_ascii=False),
    )
    repo.record_audit(
        conn,
        action="validation.run",
        created_at=utcnow_iso(),
        organization_id=None,
        user_id=user_id,
        target_type="validation_run",
        target_id=run_id,
        metadata={"summary": summary, "code_hash": code_hash[:12]},
    )
    conn.commit()
    _logger.info("validation_run_completed", extra={"run_id": run_id, "summary": summary})
    return get_run_detail(conn, run_id)


def get_run_detail(conn: sqlite3.Connection, run_id: str) -> dict:
    run = repo.get_validation_run(conn, run_id)
    if run is None:
        raise NotFoundError("Ejecución de validación no encontrada.")
    results = repo.list_validation_results(conn, run_id)
    evidence = repo.list_validation_evidence(conn, run_id)
    evidence_by_req: dict[str, list[dict]] = {}
    for item in evidence:
        evidence_by_req.setdefault(item["requirement_id"], []).append(item)
    for result in results:
        result["evidence"] = evidence_by_req.get(result["requirement_id"], [])
    run["results"] = results
    return run


def list_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return repo.list_validation_runs(conn, limit=limit)


def conformance_report(conn: sqlite3.Connection) -> dict:
    sync_registry(conn)
    requirements = repo.list_validation_requirements(conn)
    latest = repo.latest_result_per_requirement(conn)

    counts = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_PARTIAL: 0, STATUS_BLOCKED: 0, STATUS_NOT_RUN: 0}
    items = []
    for requirement in requirements:
        result = latest.get(requirement["id"])
        status = result["status"] if result else STATUS_NOT_RUN
        counts[status] = counts.get(status, 0) + 1
        items.append(
            {
                "id": requirement["id"],
                "title": requirement["title"],
                "source_section": requirement.get("source_section"),
                "status": status,
                "checks_total": result["checks_total"] if result else len(requirement["checks"]),
                "checks_passed": result["checks_passed"] if result else 0,
                "checks_failed": result["checks_failed"] if result else 0,
                "checks_skipped": result["checks_skipped"] if result else 0,
                "validated_at": result["created_at"] if result else None,
                "run_id": result["run_id"] if result else None,
            }
        )

    total = len(items)
    verified = counts[STATUS_PASS]
    return {
        "total": total,
        "verified": verified,
        "failed": counts[STATUS_FAIL],
        "partial": counts[STATUS_PARTIAL],
        "blocked": counts[STATUS_BLOCKED],
        "not_run": counts[STATUS_NOT_RUN],
        "conformance_ratio": round(verified / total, 4) if total else 0.0,
        "items": items,
    }
