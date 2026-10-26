"""Servicio de generación/reparación de código asistida por NIM (§10/§15).

Flujo verificado:

1. Se extrae el artefacto del análisis a un workspace de contexto de solo lectura.
2. Se construye un prompt acotado (árbol de archivos, archivo objetivo y hallazgos).
3. Se consulta NVIDIA NIM (único proveedor de IA).
4. Se verifica cada archivo propuesto: ruta segura, contenido no vacío y sintaxis
   comprobable. Si la verificación falla, **no se persiste** ningún cambio.
5. Los archivos válidos se registran como un conjunto de cambios ``PROPOSED``
   reutilizando el ciclo de vida de §15 (aprobar → aplicar → validar → revertir).

La verificación de sintaxis es honesta: los lenguajes sin comprobador disponible
se marcan como no verificados en lugar de afirmar una validez no comprobada.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from app.core.config import Settings
from app.core.errors import CapabilityUnavailableError, NotFoundError, ValidationAppError
from app.core.ids import new_id, utcnow_iso
from app.core.logging import get_logger
from app.db import repositories as repo
from app.engines.change_management.change_engine import looks_like_test
from app.engines.features import nim_codegen
from app.engines.features.nim_codegen import CodegenRequest
from app.engines.ingestion.safe_paths import PathLimits, assert_within, validate_relative_path
from app.engines.ingestion.safe_zip import ExtractionLimits, safe_extract
from app.services import change_service
from app.services.change_service import FileEdit
from app.services.migration_service import build_nim_client

_logger = get_logger("generation_service")

MAX_OUTPUT_TOKENS = 16384
TEMPERATURE = 0.1
MAX_INSTRUCTION_LEN = 4000


def _limits(settings: Settings) -> ExtractionLimits:
    return ExtractionLimits(
        max_entries=settings.max_archive_entries,
        max_total_bytes=settings.max_extracted_bytes,
        max_file_bytes=settings.max_single_file_bytes,
        max_compression_ratio=settings.max_compression_ratio,
        max_path_depth=settings.max_path_depth,
    )


def _read_text(path: Path, limit: int) -> str | None:
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        return data[:limit].decode("utf-8", errors="replace") + "\n... (truncado)"
    return data.decode("utf-8", errors="replace")


def _build_context(
    settings: Settings,
    *,
    artifact: dict,
    target_path: str | None,
    context_root: Path,
) -> tuple[list[str], str | None, list[tuple[str, str]]]:
    """Extrae el artefacto y devuelve ``(índice, contenido_objetivo, contexto)``."""
    workspace = context_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    safe_extract(Path(artifact["storage_path"]), workspace, _limits(settings))

    index: list[str] = []
    for file in sorted(workspace.rglob("*")):
        if file.is_file():
            index.append(file.relative_to(workspace).as_posix())
        if len(index) >= 400:
            break

    target_content = None
    target_relative: str | None = None
    if target_path:
        relative = validate_relative_path(target_path, PathLimits())
        target_relative = relative.as_posix()
        target_file = assert_within(workspace, workspace / relative)
        target_content = _read_text(target_file, nim_codegen.MAX_TARGET_FILE_BYTES)

    if target_content is not None and target_relative is not None:
        index = [path for path in index if path != target_relative]

    context: list[tuple[str, str]] = []
    total = 0
    for path in index:
        if len(context) >= nim_codegen.MAX_CONTEXT_FILES:
            break
        content = _read_text(workspace / path, nim_codegen.MAX_CONTEXT_FILE_BYTES)
        if content is None:
            continue
        if total + len(content) > nim_codegen.MAX_CONTEXT_TOTAL_BYTES:
            break
        total += len(content)
        context.append((path, content))

    return index, target_content, context


def _diff_stats(unified_diff: str | None) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in (unified_diff or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions


def create_generation(
    conn: sqlite3.Connection,
    *,
    settings: Settings,
    job: dict,
    user_id: str,
    instruction: str,
    target_path: str | None,
    mode: str,
    ai_consent: bool,
    transport=None,
) -> dict:
    if mode not in nim_codegen.MODES:
        raise ValidationAppError(f"Modo inválido: '{mode}'. Use 'feature' o 'repair'.")
    if not instruction or not instruction.strip():
        raise ValidationAppError("La instrucción de la tarea no puede estar vacía.")
    if len(instruction) > MAX_INSTRUCTION_LEN:
        raise ValidationAppError(f"La instrucción supera {MAX_INSTRUCTION_LEN} caracteres.")
    if mode == "repair" and not target_path:
        raise ValidationAppError("El modo 'repair' requiere 'target_path'.")

    organization_id = job["organization_id"]
    artifact = repo.get_artifact(conn, job["artifact_id"], organization_id)
    if artifact is None:
        raise NotFoundError("Artefacto del análisis no encontrado.")

    granted = ai_consent or settings.ai_transmission_consent_default
    if not granted:
        raise ValidationAppError(
            "La generación envía fragmentos de código a NVIDIA NIM. Confirme el "
            "consentimiento de transmisión (§14) con 'ai_consent': true.",
            code="ai_consent_required",
            status_code=409,
        )

    client = build_nim_client(settings, transport=transport)
    if not client.configured:
        raise CapabilityUnavailableError(
            "NVIDIA NIM no está configurado (falta SIREP_NIM_API_KEY)."
        )

    generation_id = new_id("gen")
    context_root = settings.storage_root / "generations" / generation_id
    try:
        index, target_content, context = _build_context(
            settings, artifact=artifact, target_path=target_path, context_root=context_root
        )

        findings: list[dict] = []
        if mode == "repair" and target_path:
            all_findings, _ = repo.list_findings(
                conn, analysis_id=job["id"], organization_id=organization_id, limit=200
            )
            findings = [f for f in all_findings if f.get("file_path") == target_path]

        request = CodegenRequest(
            instruction=instruction.strip(),
            mode=mode,
            target_path=target_path,
            target_content=target_content,
            file_index=index,
            context_files=context,
            findings=findings,
            language_hint=nim_codegen.language_for_path(target_path) if target_path else None,
        )
        messages = nim_codegen.build_messages(request)

        try:
            result = client.chat(
                messages, model=settings.nim_model, max_tokens=MAX_OUTPUT_TOKENS, temperature=TEMPERATURE
            )
        except Exception as exc:  # noqa: BLE001 - se traduce a error de capacidad
            _logger.warning("generation.nim_error", extra={"error": str(exc)})
            raise CapabilityUnavailableError(
                "No se pudo completar la generación con NVIDIA NIM.", details={"error": str(exc)}
            ) from exc

        files, summary, notes, errors = nim_codegen.parse_response(result.content)
        if errors:
            raise ValidationAppError(
                "La verificación del código generado falló; no se registró ningún cambio.",
                code="generation_verification_failed",
                details={"errors": errors},
            )
        if not files:
            raise ValidationAppError(
                "El modelo no propuso archivos.",
                code="generation_empty",
                details={"notes": notes},
            )

        produced_by_rule = "NIM-REPAIR" if mode == "repair" else "NIM-GENERATE"
        reason = f"[{produced_by_rule}] {instruction.strip()}"
        change_set = change_service.create_change_set(
            conn,
            settings=settings,
            job=job,
            user_id=user_id,
            reason=reason,
            produced_by_rule=produced_by_rule,
            edits=[FileEdit(path=file.path, new_content=file.content) for file in files],
        )
        detail = change_service.get_change_set_detail(
            conn, change_set_id=change_set["id"], organization_id=organization_id
        )
    finally:
        shutil.rmtree(context_root, ignore_errors=True)

    files_by_path = {file.path: file for file in files}
    verification = []
    limitations: list[str] = []
    for item in detail["files"]:
        generated = files_by_path.get(item["path"])
        additions, deletions = _diff_stats(item.get("unified_diff"))
        language = generated.language if generated else nim_codegen.language_for_path(item["path"])
        syntax_checked = generated.syntax_checked if generated else False
        syntax_ok = generated.syntax_ok if generated else None
        note = None
        if not syntax_checked:
            note = f"Sintaxis de '{language}' no verificada por este entorno."
            limitations.append(f"{item['path']}: sintaxis de '{language}' no verificada.")
        verification.append(
            {
                "path": item["path"],
                "language": language,
                "change_type": item["change_type"],
                "syntax_checked": syntax_checked,
                "syntax_ok": syntax_ok,
                "additions": additions,
                "deletions": deletions,
                "note": note,
            }
        )

    if any(looks_like_test(item["path"]) for item in detail["files"]):
        limitations.append("El cambio incluye archivos de prueba; revísalos antes de aplicar.")

    now = utcnow_iso()
    repo.record_audit(
        conn,
        action="generation.create",
        created_at=now,
        organization_id=organization_id,
        user_id=user_id,
        target_type="change_set",
        target_id=change_set["id"],
        metadata={
            "mode": mode,
            "model": result.model,
            "files": len(detail["files"]),
            "syntax_checked": sum(1 for v in verification if v["syntax_checked"]),
        },
    )
    conn.commit()

    return {
        "change_set": detail,
        "verification": verification,
        "summary": summary or None,
        "notes": notes or None,
        "model": result.model,
        "mode": mode,
        "usage": result.usage or None,
        "latency_ms": result.latency_ms,
        "limitations": limitations,
    }
