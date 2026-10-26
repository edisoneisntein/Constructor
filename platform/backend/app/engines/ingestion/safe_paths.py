"""Validación de rutas relativas para ingesta (§14.3, §4.5).

La validación es la **autoritativa** del servidor: se aplica con la misma
severidad a entradas de ZIP (``safe_zip``) y a la ingesta de carpetas por
multipart. La ruta enviada por el cliente solo se usa para *rechazar*; nunca
para decidir la ubicación en disco (esa se re-deriva de la ruta normalizada).

Defensas implementadas:

  * Rechazo de rutas absolutas, ``..``, ``.``, segmentos vacíos y separadores
    ``\\`` o unidades Windows.
  * Rechazo de bytes nulos y caracteres de control.
  * Nombres reservados de Windows (``CON``, ``NUL``, ``COM1``…) y segmentos con
    punto o espacio final.
  * Límite de profundidad, longitud total y longitud por segmento.
  * Comprobación de contención tras resolver contra la raíz de destino.

Falla en cerrado con ``UnsafeArchiveError`` (código estable ``unsafe_archive``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.core.errors import UnsafeArchiveError

MAX_SEGMENT_LENGTH = 255

_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


@dataclass(frozen=True)
class PathLimits:
    max_depth: int = 64
    max_length: int = 4096


def validate_relative_path(name: str, limits: PathLimits) -> PurePosixPath:
    """Normaliza y valida una ruta relativa; lanza ``UnsafeArchiveError`` si es insegura."""
    if name is None or name == "":
        raise UnsafeArchiveError("Ruta de entrada vacía.")
    if "\x00" in name:
        raise UnsafeArchiveError("Ruta con byte nulo.", details={"name": repr(name)})
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in name):
        raise UnsafeArchiveError("Ruta con caracteres de control.", details={"name": repr(name)})
    if "\\" in name:
        raise UnsafeArchiveError("Ruta con separador Windows.", details={"name": name})
    if len(name) > limits.max_length:
        raise UnsafeArchiveError(
            "Ruta demasiado larga.", details={"length": len(name), "max": limits.max_length}
        )

    candidate = PurePosixPath(name)
    if candidate.is_absolute():
        raise UnsafeArchiveError("Ruta absoluta.", details={"name": name})
    parts = candidate.parts
    if any(part in {"..", ".", ""} for part in parts):
        raise UnsafeArchiveError("Ruta con segmentos no permitidos.", details={"name": name})
    if any(len(part) >= 2 and part[1] == ":" for part in parts):
        raise UnsafeArchiveError("Ruta con unidad Windows.", details={"name": name})
    if len(parts) > limits.max_depth:
        raise UnsafeArchiveError(
            "Ruta demasiado profunda.", details={"name": name, "depth": len(parts)}
        )
    for part in parts:
        if len(part) > MAX_SEGMENT_LENGTH:
            raise UnsafeArchiveError(
                "Segmento de ruta demasiado largo.", details={"name": name}
            )
        if part != part.rstrip(". "):
            raise UnsafeArchiveError(
                "Segmento con punto o espacio final.", details={"name": name}
            )
        stem = part.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            raise UnsafeArchiveError("Nombre reservado por el sistema.", details={"name": name})
    return candidate


def normalize_relative_path(name: str, limits: PathLimits) -> str:
    """Devuelve la ruta canónica en formato POSIX (``a/b/c``)."""
    return validate_relative_path(name, limits).as_posix()


def assert_within(root: Path, target: Path) -> Path:
    """Resuelve ``target`` y comprueba que queda dentro de ``root``; si no, falla."""
    resolved_root = root.resolve()
    resolved = target.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise UnsafeArchiveError(
            "La ruta resuelta queda fuera del destino.",
            details={"target": str(target)},
        )
    return resolved
