"""Aislamiento y límites de recursos para subprocesos (§14.2).

Proporciona ``preexec_fn`` para ``subprocess`` que limita CPU, tamaño de archivo
y descriptores del proceso hijo. Se aplica a la ejecución de herramientas
externas (REA, bridge Node). No asume que un contenedor proporcione aislamiento
perfecto: el llamador debe elegir un perfil adecuado al riesgo (§14.1).
"""

from __future__ import annotations

import os
from typing import Any, Callable

try:  # pragma: no cover - disponibilidad dependiente de plataforma
    import resource  # type: ignore
except ImportError:  # pragma: no cover
    resource = None  # type: ignore

POSIX = os.name == "posix"


def limits_supported() -> bool:
    return POSIX and resource is not None


def build_preexec(
    *,
    cpu_seconds: int = 0,
    max_file_bytes: int = 0,
    max_memory_mb: int = 0,
) -> Callable[[], None] | None:
    """Construye un ``preexec_fn`` con los límites indicados.

    ``max_memory_mb=0`` no aplica ``RLIMIT_AS`` por defecto: Node/V8 reservan
    grandes rangos de memoria virtual y un límite de AS puede romperlos. Solo se
    aplica si el llamador lo solicita explícitamente.
    """
    if not limits_supported():
        return None

    def _apply() -> None:
        if cpu_seconds > 0 and hasattr(resource, "RLIMIT_CPU"):
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        if max_file_bytes > 0 and hasattr(resource, "RLIMIT_FSIZE"):
            resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_bytes, max_file_bytes))
        if max_memory_mb > 0 and hasattr(resource, "RLIMIT_AS"):
            limit = max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        # Reduce descriptores disponibles para el hijo.
        if hasattr(resource, "RLIMIT_NOFILE"):
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(soft, 1024), hard))

    return _apply


def subprocess_limits(settings: Any) -> dict[str, Any]:
    """Devuelve los kwargs de ``subprocess`` con límites según configuración."""
    preexec = build_preexec(
        cpu_seconds=getattr(settings, "sandbox_cpu_seconds", 0),
        max_file_bytes=getattr(settings, "sandbox_max_file_bytes", 0),
        max_memory_mb=getattr(settings, "sandbox_max_memory_mb", 0),
    )
    if preexec is None:
        return {}
    return {"preexec_fn": preexec}
