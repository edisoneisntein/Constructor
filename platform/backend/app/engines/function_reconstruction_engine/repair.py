"""Function repair operations (§8).

Provides safe repair operations for function-level issues detected by the
FunctionReconstructionEngine. All operations are statically analyzed and
do not execute arbitrary code.

Operations include:
- Adding type annotations
- Fixing parameter lists
- Adding docstrings
- Fixing async/await issues
"""

from __future__ import annotations

import ast  # ADD THIS
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class FunctionRepairResult:
    """Resultado de una reparación de función."""
    success: bool
    repaired_code: str
    explanation: str
    limitations: list[str]


def _find_function(tree: ast.AST, target_func: str | None):
    """Localiza la función objetivo (o la primera) en el árbol sintáctico."""
    fallback = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if target_func is None:
            if fallback is None:
                fallback = node
            continue
        if node.name == target_func:
            return node
    return fallback


def _signature_span(func_node) -> tuple[int, int]:
    """Devuelve (línea_inicio, línea_fin) de la firma de la función."""
    start = func_node.lineno - 1
    end = func_node.body[0].lineno - 1  # exclusivo: inicio del cuerpo
    for decorator in func_node.decorator_list:
        start = min(start, decorator.lineno - 1)
    return start, end


def _replace_signature(code: str, func_node, new_signature: str) -> str:
    """Sustituye la firma de la función conservando el cuerpo intacto."""
    lines = code.splitlines(keepends=True)
    start, end = _signature_span(func_node)
    prefix = "async def " if isinstance(func_node, ast.AsyncFunctionDef) else "def "
    replacement = prefix + new_signature
    if not replacement.endswith(":"):
        replacement += ":"
    if not replacement.endswith("\n"):
        replacement += "\n"
    # Conservar la indentación original de la línea de definición.
    original = lines[start] if start < len(lines) else ""
    indent = original[: len(original) - len(original.lstrip())]
    return "".join(lines[:start]) + indent + replacement + "".join(lines[end:])


def _repair_add_annotations(code: str, func_node) -> FunctionRepairResult:
    """Añade anotaciones de tipo a los parámetros sin anotar y al retorno."""
    args = func_node.args
    positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
    all_args = positional + list(args.kwonlyargs)

    steps: list[str] = []
    parts: list[str] = []
    for index, arg in enumerate(all_args):
        annotation = ast.unparse(arg.annotation) if arg.annotation is not None else "Any"
        if arg.annotation is None:
            steps.append(f"parámetro '{arg.arg}': Any")
        prefix = ""
        if args.posonlyargs and index == len(args.posonlyargs):
            prefix = "/, "
        parts.append(f"{prefix}{arg.arg}: {annotation}")

    if args.vararg is not None:
        annotation = ast.unparse(args.vararg.annotation) if args.vararg.annotation is not None else "Any"
        parts.append(f"*{args.vararg.arg}: {annotation}")
    elif args.kwonlyargs:
        parts.append("*")

    if args.kwarg is not None:
        annotation = ast.unparse(args.kwarg.annotation) if args.kwarg.annotation is not None else "Any"
        parts.append(f"**{args.kwarg.arg}: {annotation}")

    return_annotation = ast.unparse(func_node.returns) if func_node.returns is not None else "Any"
    if func_node.returns is None:
        steps.append("retorno: Any")

    signature = f"{func_node.name}({', '.join(parts)}) -> {return_annotation}"
    repaired = _replace_signature(code, func_node, signature)

    try:
        ast.parse(repaired)
    except SyntaxError:
        return FunctionRepairResult(
            success=False,
            repaired_code=code,
            explanation="La reparación de anotaciones produjo código inválido; se conserva el original.",
            limitations=["No se pudo aplicar la reparación de forma segura."],
        )

    return FunctionRepairResult(
        success=True,
        repaired_code=repaired,
        explanation=(
            "Reparación 'add_annotations' aplicada: " + ", ".join(steps)
            if steps
            else "Reparación 'add_annotations': la función ya tenía anotaciones completas."
        ),
        limitations=[
            "Las anotaciones inferidas usan 'Any': no hay análisis semántico de tipos.",
        ],
    )


def _repair_add_docstring(code: str, func_node) -> FunctionRepairResult:
    """Añade un docstring a la función si no tiene uno."""
    first = func_node.body[0]
    has_docstring = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )
    if has_docstring:
        return FunctionRepairResult(
            success=True,
            repaired_code=code,
            explanation="Reparación 'add_docstring': la función ya tenía docstring.",
            limitations=["No se modifica el código cuando el docstring ya existe."],
        )

    docstring = f"Documentación de {func_node.name} (pendiente de revisar)."
    lines = code.splitlines(keepends=True)
    body_start = func_node.body[0].lineno - 1
    insertion = f'    """{docstring}"""\n'
    repaired = "".join(lines[:body_start]) + insertion + "".join(lines[body_start:])

    try:
        ast.parse(repaired)
    except SyntaxError:
        return FunctionRepairResult(
            success=False,
            repaired_code=code,
            explanation="La inserción del docstring produjo código inválido; se conserva el original.",
            limitations=["No se pudo aplicar la reparación de forma segura."],
        )

    return FunctionRepairResult(
        success=True,
        repaired_code=repaired,
        explanation="Reparación 'add_docstring' aplicada: docstring insertado.",
        limitations=["El docstring generado es genérico y requiere revisión manual."],
    )


def _repair_fix_params(code: str, func_node) -> FunctionRepairResult:
    """Normaliza la firma eliminando parámetros duplicados.

    Es una normalización conservadora: solo actúa si detecta un problema real.
    """
    args = func_node.args
    positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
    all_args = positional + list(args.kwonlyargs)

    seen: set[str] = set()
    duplicates: list[str] = []
    for arg in all_args:
        if arg.arg in seen:
            duplicates.append(arg.arg)
        seen.add(arg.arg)

    if not duplicates:
        return FunctionRepairResult(
            success=True,
            repaired_code=code,
            explanation="Reparación 'fix_params': no se detectaron parámetros duplicados.",
            limitations=["Solo se detectan parámetros duplicados en la firma."],
        )

    kept = []
    seen = set()
    for arg in all_args:
        if arg.arg in seen:
            continue
        seen.add(arg.arg)
        kept.append(arg)

    parts = []
    for index, arg in enumerate(kept):
        annotation = f": {ast.unparse(arg.annotation)}" if arg.annotation is not None else ""
        prefix = ""
        if args.posonlyargs and index == len(args.posonlyargs):
            prefix = "/, "
        parts.append(f"{prefix}{arg.arg}{annotation}")

    if args.vararg is not None:
        annotation = f": {ast.unparse(args.vararg.annotation)}" if args.vararg.annotation is not None else ""
        parts.append(f"*{args.vararg.arg}{annotation}")
    elif args.kwonlyargs:
        parts.append("*")

    if args.kwarg is not None:
        annotation = f": {ast.unparse(args.kwarg.annotation)}" if args.kwarg.annotation is not None else ""
        parts.append(f"**{args.kwarg.arg}{annotation}")

    signature = f"{func_node.name}({', '.join(parts)})"
    if func_node.returns is not None:
        signature += f" -> {ast.unparse(func_node.returns)}"
    repaired = _replace_signature(code, func_node, signature)

    try:
        ast.parse(repaired)
    except SyntaxError:
        return FunctionRepairResult(
            success=False,
            repaired_code=code,
            explanation="La normalización de parámetros produjo código inválido; se conserva el original.",
            limitations=["No se pudo aplicar la reparación de forma segura."],
        )

    return FunctionRepairResult(
        success=True,
        repaired_code=repaired,
        explanation=(
            "Reparación 'fix_params' aplicada: parámetros duplicados eliminados ("
            + ", ".join(duplicates)
            + ")."
        ),
        limitations=["No se modifican los valores por defecto; solo se eliminan duplicados."],
    )


def apply_function_repair(code: str, repair_type: str, target_func: str | None = None) -> FunctionRepairResult:
    """Aplica un parche de reparación a una función en el código.

    Las reparaciones se aplican realmente sobre el texto fuente: el resultado
    ``repaired_code`` es el código modificado y verificable, no el original.

    Args:
        code: Código fuente completo
        repair_type: Tipo de reparación ('add_annotations', 'fix_params', 'add_docstring')
        target_func: Nombre de la función objetivo (None = primera función encontrada)

    Returns:
        FunctionRepairResult con el código reparado y metadatos
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return FunctionRepairResult(
            success=False,
            repaired_code=code,
            explanation="Error de sintaxis en el código proporcionado.",
            limitations=["No se pudo analizar el código fuente."],
        )

    func_node = _find_function(tree, target_func)
    if func_node is None:
        target = target_func or "(primera función)"
        return FunctionRepairResult(
            success=False,
            repaired_code=code,
            explanation=f"Función '{target}' no encontrada en el código.",
            limitations=["No se encontró la función objetivo en el código proporcionado."],
        )

    if repair_type == "add_annotations":
        return _repair_add_annotations(code, func_node)
    if repair_type == "add_docstring":
        return _repair_add_docstring(code, func_node)
    if repair_type == "fix_params":
        return _repair_fix_params(code, func_node)

    return FunctionRepairResult(
        success=False,
        repaired_code=code,
        explanation=f"Tipo de reparación desconocido: {repair_type}.",
        limitations=[
            "Tipos soportados: add_annotations, add_docstring, fix_params.",
        ],
    )


def reconstruct_function_graph(code: str) -> dict:
    """Reconstruye el grafo de dependencias de funciones en el código.

    Delegado en ``patterns.reconstruct_function_graph`` para evitar dos
    implementaciones divergentes del mismo análisis (§8).
    """
    from app.engines.function_reconstruction_engine.patterns import (
        reconstruct_function_graph as _reconstruct_graph,
    )

    return _reconstruct_graph(code)