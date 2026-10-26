"""Motor de integridad, diffs y reversión (§15).

Lógica pura y verificable: normalización segura de rutas, clasificación de
cambios (añadido/modificado/eliminado), hashes SHA-256 y diff unificado.
No realiza efectos de E/S por sí mismo: recibe y devuelve bytes.
"""

from __future__ import annotations

import difflib
import posixpath
from dataclasses import dataclass

from app.core.errors import ValidationAppError
from app.engines.ingestion.artifact_store import sha256_bytes

CHANGE_TYPES = {"ADDED", "MODIFIED", "DELETED"}


@dataclass
class FileChange:
    path: str
    change_type: str
    base_sha256: str | None
    new_sha256: str | None
    unified_diff: str
    before: bytes | None
    after: bytes | None


def safe_relative_path(raw: str) -> str:
    """Normaliza una ruta relativa y rechaza escapes fuera del workspace."""
    if not raw or not raw.strip():
        raise ValidationAppError("Ruta de archivo vacía.")
    candidate = raw.replace("\\", "/").strip()
    if candidate.startswith("/") or candidate.startswith("~"):
        raise ValidationAppError(f"Ruta absoluta no permitida: {raw}")
    normalized = posixpath.normpath(candidate)
    if normalized in {".", ".."} or normalized.startswith("../") or "/../" in normalized:
        raise ValidationAppError(f"Ruta fuera del workspace: {raw}")
    if "\x00" in normalized:
        raise ValidationAppError("Ruta con bytes nulos no permitida.")
    return normalized


def _text(data: bytes | None) -> str:
    if data is None:
        return ""
    return data.decode("utf-8", errors="replace")


def unified_diff(path: str, before: bytes | None, after: bytes | None) -> str:
    before_lines = _text(before).splitlines(keepends=True)
    after_lines = _text(after).splitlines(keepends=True)
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    rendered = "".join(diff)
    if rendered and not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def classify_change(path: str, before: bytes | None, after: bytes | None) -> FileChange | None:
    """Clasifica un cambio. Devuelve ``None`` si no hay diferencia efectiva."""
    if before is None and after is None:
        raise ValidationAppError(f"El cambio de '{path}' no aporta contenido.")
    if before is None:
        change_type = "ADDED"
    elif after is None:
        change_type = "DELETED"
    else:
        if before == after:
            return None
        change_type = "MODIFIED"
    return FileChange(
        path=path,
        change_type=change_type,
        base_sha256=sha256_bytes(before) if before is not None else None,
        new_sha256=sha256_bytes(after) if after is not None else None,
        unified_diff=unified_diff(path, before, after),
        before=before,
        after=after,
    )


def looks_like_test(path: str) -> bool:
    name = posixpath.basename(path).lower()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
        or "/tests/" in f"/{path.lower()}"
    )
