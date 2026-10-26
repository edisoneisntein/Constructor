"""FunctionReconstructionEngine engine (§8).

Provides function reconstruction and dependency analysis for the architecture
graph. Analyzes Python code to identify functions, their parameters, return
types, decorators, and dependencies between functions.

Does NOT execute arbitrary code: only performs static analysis using AST
and regular expression patterns.

La implementación vive en ``patterns.py`` (fuente única). Este módulo se
mantiene como fachada compatible con el contrato original:

* ``reconstruct_function(code)`` devuelve ``{"function": ..., "dependencies": ...}``.
* ``extract_dependencies(code, func_name)`` acepta el **nombre** de la función
  (no un ``FunctionInfo``) y devuelve ``reads``/``writes``/``calls``.
* ``classify_function(code, tree)`` devuelve el diccionario con ``functions``.

Las funciones ``async def`` se detectan correctamente: ``ast.AsyncFunctionDef``
NO hereda de ``ast.FunctionDef``, por lo que ambos tipos deben comprobarse.
"""

from __future__ import annotations

import ast

from app.engines.function_reconstruction_engine.patterns import (
    classify_function as _classify_function,
)
from app.engines.function_reconstruction_engine.patterns import (
    extract_dependencies as _extract_dependencies,
)
from app.engines.function_reconstruction_engine.patterns import (
    reconstruct_function as _reconstruct_function,
)


def reconstruct_function(code: str) -> dict:
    """Reconstruct a function and its dependencies from source code.

    Args:
        code: Python source code containing function definitions

    Returns:
        Dict with function info and dependencies, or an ``error`` entry when
        the source cannot be parsed or contains no function definitions.
    """
    return _reconstruct_function(code)


def extract_dependencies(code: str, func_name: str) -> dict:
    """Extract read/write/call dependencies for a specific function.

    Args:
        code: Python source code.
        func_name: Name of the function to analyse.
    """
    if not func_name:
        return {"reads": [], "writes": [], "calls": []}
    info = _classify_function(code)
    if info.name == "":
        return {"reads": [], "writes": [], "calls": []}
    deps = _extract_dependencies(code, info)
    return {"reads": deps.reads, "writes": deps.writes, "calls": deps.calls}


def classify_function(code: str, tree: ast.AST | None = None) -> dict:
    """Classify functions in code and return structured information.

    Args:
        code: Python source code
        tree: Pre-parsed AST (optional, will parse if not provided)

    Returns:
        Dict with classified function information
    """
    info = _classify_function(code, tree)
    return {
        "functions": [
            {
                "name": info.name,
                "line": info.line,
                "is_async": info.is_async,
                "parameters": info.params,
                "return_annotation": info.return_annotation,
                "decorators": info.decorators,
            }
        ]
        if info.name
        else []
    }