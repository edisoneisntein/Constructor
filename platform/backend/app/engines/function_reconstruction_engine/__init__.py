"""FunctionReconstructionEngine (§8).

Motor de reconstrucción de funciones y relaciones de dependencia para el grafo
de arquitectura. Analiza definiciones de funciones, parámetros, retornos y
estructuras de control para construir un grafo de dependencias direccional.

Sigue el patrón de otros engines del proyecto (change_management, repair_engine)
y produce resultados estructurados para el validador.

No ejecuta código arbitrario: solo realiza análisis estático sobre el código
fuente usando expresiones regulares y análisis de AST ligero.
"""
from __future__ import annotations

from app.engines.function_reconstruction_engine.engine import (
    reconstruct_function,
)
from app.engines.function_reconstruction_engine.patterns import (
    FUNCTION_PATTERNS,
    classify_function,
    extract_dependencies,
)
from app.engines.function_reconstruction_engine.repair import (
    apply_function_repair,
    FunctionRepairResult,
)

__all__ = [
    "reconstruct_function",
    "classify_function",
    "extract_dependencies",
    "apply_function_repair",
    "FunctionRepairResult",
]