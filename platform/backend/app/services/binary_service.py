"""Servicio de análisis de aplicaciones compiladas (§6.2)."""

from __future__ import annotations

import json
import sqlite3

from app.core.config import Settings
from app.core.errors import NotFoundError, PayloadTooLargeError, ValidationAppError
from app.core.ids import utcnow_iso
from app.db import repositories as repo
from app.engines.binary_analysis import BinaryLimits, analyze_binary, compare_binaries, detect_format
from app.engines.binary_analysis.formats import SUPPORTED_FORMATS
from app.engines.ingestion.artifact_store import store_artifact
from app.services.usage_service import enforce_storage_quota

KNOWN_FORMATS = SUPPORTED_FORMATS


def ingest_binary(
    conn: sqlite3.Connection,
    *,
    settings: Settings,
    project: dict,
    user_id: str,
    filename: str,
    declared_mime: str | None,
    data: bytes,
) -> dict:
    """Almacena un binario tras identificar su formato (§6.1/§6.2)."""
    if len(data) == 0:
        raise ValidationAppError("El archivo está vacío.")
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            "El archivo supera el límite de carga.",
            details={"size": len(data), "max": settings.max_upload_bytes},
        )
    detected = detect_format(data)
    if detected not in KNOWN_FORMATS:
        raise ValidationAppError(
            "Formato binario no soportado todavía (§6.1).",
            details={"detected_format": detected, "supported": sorted(KNOWN_FORMATS)},
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
    now = utcnow_iso()
    artifact = repo.create_artifact(
        conn,
        project_id=project["id"],
        organization_id=project["organization_id"],
        kind="BINARY",
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
        action="binary.ingest",
        created_at=now,
        organization_id=project["organization_id"],
        user_id=user_id,
        target_type="artifact",
        target_id=artifact["id"],
        metadata={"format": detected, "size": stored.size_bytes},
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


def analyze_binary_artifact(
    conn: sqlite3.Connection,
    *,
    settings: Settings,
    project: dict,
    artifact_id: str,
    user_id: str,
) -> dict:
    """Ejecuta el análisis estático del binario y persiste los hechos (§6.2)."""
    artifact = repo.get_artifact(conn, artifact_id, project["organization_id"])
    if artifact is None or artifact["project_id"] != project["id"]:
        raise NotFoundError("Artefacto no encontrado en el proyecto.")
    if artifact["kind"] != "BINARY":
        raise ValidationAppError("El artefacto no es un binario analizable.")

    limits = BinaryLimits(max_bytes=settings.binary_analysis_max_bytes)
    facts = analyze_binary(_artifact_path(artifact), limits)
    now = utcnow_iso()
    record = repo.create_binary_analysis(
        conn,
        artifact_id=artifact["id"],
        project_id=project["id"],
        organization_id=project["organization_id"],
        format=facts.format,
        architecture=facts.architecture,
        bits=facts.bits,
        file_type=facts.file_type,
        size_bytes=facts.size_bytes,
        sha256=facts.sha256,
        facts_json=json.dumps(facts.to_dict(), ensure_ascii=False),
        created_by=user_id,
        created_at=now,
    )
    repo.record_audit(
        conn,
        action="binary.analyze",
        created_at=now,
        organization_id=project["organization_id"],
        user_id=user_id,
        target_type="binary_analysis",
        target_id=record["id"],
        metadata={"format": facts.format},
    )
    repo.record_usage(
        conn,
        organization_id=project["organization_id"],
        project_id=project["id"],
        metric="binary_analyses",
        quantity=1,
        created_at=now,
    )
    return _public(record)


def get_binary_analysis(conn: sqlite3.Connection, *, analysis_id: str, organization_id: str) -> dict:
    record = repo.get_binary_analysis(conn, analysis_id, organization_id)
    if record is None:
        raise NotFoundError("Análisis binario no encontrado.")
    return _public(record)


def list_binary_analyses(conn: sqlite3.Connection, *, project_id: str, organization_id: str) -> list[dict]:
    return [_public(record) for record in repo.list_binary_analyses(conn, project_id, organization_id)]


def compare_analyses(
    conn: sqlite3.Connection, *, left_id: str, right_id: str, organization_id: str
) -> dict:
    left = repo.get_binary_analysis(conn, left_id, organization_id)
    right = repo.get_binary_analysis(conn, right_id, organization_id)
    if left is None or right is None:
        raise NotFoundError("Análisis binario no encontrado.")
    from app.engines.binary_analysis.models import BinaryFacts

    def to_facts(record: dict) -> BinaryFacts:
        payload = json.loads(record["facts_json"])
        from app.engines.binary_analysis.models import Section

        facts = BinaryFacts(
            path=payload["path"],
            size_bytes=payload["size_bytes"],
            sha256=payload["sha256"],
            sha1=payload["sha1"],
            md5=payload["md5"],
            format=payload["format"],
            architecture=payload.get("architecture"),
            bits=payload.get("bits"),
            file_type=payload.get("file_type"),
            imported_symbols=payload.get("imported_symbols", []),
            exported_symbols=payload.get("exported_symbols", []),
            linked_libraries=payload.get("linked_libraries", []),
        )
        facts.sections = [Section(**s) for s in payload.get("sections", [])]
        return facts

    return compare_binaries(to_facts(left), to_facts(right))


def _artifact_path(artifact: dict):
    from pathlib import Path

    return Path(artifact["storage_path"])


def _public(record: dict) -> dict:
    payload = dict(record)
    payload["facts"] = json.loads(record["facts_json"])
    payload.pop("facts_json", None)
    return payload
