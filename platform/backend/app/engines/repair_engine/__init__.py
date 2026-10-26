"""Motor de reparación de código (§9).

Proporciona capacidades de análisis y reparación de código Python dentro de un
entorno aislado (perfil ISOLATED_TEST_EXECUTION). No ejecuta código arbitrario:
solo aplica transformaciones seguras sobre código fuente verificado.

Sigue el mismo patrón que ``change_management``: lógica pura, sin efectos de E/S
por sí mismo, y devuelve resultados estructurados para que el validador decida
si aplicar los cambios.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Any

from app.core.errors import ValidationAppError
from app.engines.repair_engine.patterns import COMMON_PYTHON_PATTERNS
from app.engines.repair_engine.repair import apply_repair, RepairResult


__all__ = [
    "apply_repair",
    "RepairResult",
    "ClassifyRepair",
    "safe_relative_path",
    "classify_repair",
]