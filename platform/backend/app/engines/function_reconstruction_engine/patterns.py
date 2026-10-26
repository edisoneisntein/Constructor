"""Patrones para FunctionReconstructionEngine (§8).

Define expresiones regulares y lógicas para identificar y clasificar funciones
en el código Python. Cada patrón está diseñado para detectarse estáticamente
sin necesidad de ejecución en tiempo real.

Los patrones cubren:
- Definiciones de funciones (def func...)
- Parámetros y firma
- Retornos y anotaciones
- Decoradores
- Alcance de variables
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class FunctionInfo:
    """Información estructurada sobre una función detectada."""
    name: str
    line: int
    params: list[str]
    return_annotation: str | None
    decorators: list[str]
    is_async: bool
    location: str  # "top_level" | "method" | "nested"


@dataclass
class DependencyInfo:
    """Información sobre dependencias de una función."""
    name: str
    reads: list[str]  # variables/imports leídas
    writes: list[str]  # variables/imports escritas
    calls: list[str]  # nombres de funciones llamadas


FUNCTION_PATTERNS = [
    # Patrón básico de definición de función
    {"pattern": r"def\s+(\w+)\s*\(([^)]*)\)\s*(->\s*\w+)?\s*(:)", "info_key": "def"},
    # Patrón async
    {"pattern": r"async\s+def\s+(\w+)\s*\(([^)]*)\)", "info_key": "async_def"},
    # Patrón de decorador
    {"pattern": r"@(\w+)\s*\(\s*\)", "info_key": "decorator"},
]


def classify_function(code: str, tree: Optional[ast.AST] = None) -> FunctionInfo:
    """Analiza código y retorna información estructurada sobre funciones detectadas."""
    if tree is None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return FunctionInfo(
                name="",
                line=0,
                params=[],
                return_annotation=None,
                decorators=[],
                is_async=False,
                location="invalid",
            )
    
    functions = []
    for node in ast.walk(tree):
        # ``AsyncFunctionDef`` NO hereda de ``FunctionDef``: hay que incluir ambos
        # tipos explícitamente o las funciones ``async def`` nunca se detectan.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_async = isinstance(node, ast.AsyncFunctionDef)
            func_name = node.name
            
            # Extraer parámetros
            params = []
            for arg in node.args.args:
                params.append(arg.arg)
            for arg in node.args.posonlyargs:
                params.append(arg.arg)
            for arg in node.args.kwonlyargs:
                params.append(arg.arg)
            if node.args.vararg:
                params.append(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                params.append(f"**{node.args.kwarg.arg}")
            
            # Extraer retorno
            return_annotation = None
            if node.returns:
                return_annotation = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
            
            # Extraer decoradores
            decorators = []
            for d in node.decorator_list:
                if isinstance(d, ast.Name):
                    decorators.append(d.id)
                elif isinstance(d, ast.Attribute):
                    decorators.append(d.attr)
            
            # Extraer ubicación
            location = "top_level"
            
            func = FunctionInfo(
                name=func_name,
                line=node.lineno,
                params=params,
                return_annotation=return_annotation,
                decorators=decorators,
                is_async=is_async,
                location="top_level",
            )
            functions.append(func)
    
    return functions[0] if functions else FunctionInfo(
        name="",
        line=0,
        params=[],
        return_annotation=None,
        decorators=[],
        is_async=False,
        location="not_found",
    )


def extract_dependencies(code: str, func_info: FunctionInfo) -> DependencyInfo:
    """Extrae variables leídas, escritas y llamadas a otras funciones."""
    if func_info.name == "":
        return DependencyInfo(
            name="",
            reads=[],
            writes=[],
            calls=[],
        )
    
    reads = []
    writes = []
    calls = []
    
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return DependencyInfo(name=func_info.name, reads=[], writes=[], calls=[])
    
    for node in ast.walk(tree):
        # Leer nombres de variables simples
        if isinstance(node, ast.Name):
            if node.id == func_info.name:
                continue  # Saltar la propia función
            # Variables simples (no atributos ni subscripts)
            if isinstance(node.ctx, ast.Load):
                if node.id not in reads:
                    reads.append(node.id)
            elif isinstance(node.ctx, ast.Store):
                if node.id not in writes:
                    writes.append(node.id)
        
        # Llamadas a funciones
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in calls:
                    calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                func_name = f"{node.func.attr}"
                if func_name not in calls:
                    calls.append(func_name)
    
    return DependencyInfo(
        name=func_info.name,
        reads=sorted(reads),
        writes=sorted(writes),
        calls=sorted(calls),
    )


def reconstruct_function(code: str) -> dict:
    """Función principal: reconstruye una función y sus dependencias."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"error": "Syntax error in code", "function": None, "dependencies": None}
    
    # Encontrar la primera función (síncrona o asíncrona).
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node)
    
    if not functions:
        return {"error": "No functions found", "function": None, "dependencies": None}
    
    # Usar la primera función encontrada
    func_node = functions[0]
    func_info = FunctionInfo(
        name=func_node.name,
        line=func_node.lineno,
        params=[arg.arg for arg in func_node.args.args],
        return_annotation=ast.unparse(func_node.returns) if hasattr(ast, 'unparse') else None,
        decorators=[d.id if isinstance(d, ast.Name) else getattr(d, 'attr', '') for d in func_node.decorator_list],
        is_async=isinstance(func_node, ast.AsyncFunctionDef),
        location="top_level",
    )
    
    deps = extract_dependencies(code, func_info)
    
    return {
        "function": {
            "name": func_info.name,
            "line": func_info.line,
            "is_async": func_info.is_async,
            "parameters": func_info.params,
            "return_type": func_info.return_annotation,
            "decorators": func_info.decorators,
        },
        "dependencies": {
            "reads": deps.reads,
            "writes": deps.writes,
            "calls": deps.calls,
        },
    }


def _function_nodes(tree: ast.AST) -> list[ast.AST]:
    """Nodos de función del árbol (síncronas y asíncronas)."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def reconstruct_function_graph(code: str) -> dict:
    """Reconstruye el grafo de dependencias entre funciones del código (§8).

    Cada función se asocia con las llamadas que aparecen dentro de su propio
    cuerpo. Solo es análisis estático: no se ejecuta el código.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"error": "Syntax error", "functions": [], "dependencies": []}

    functions_info: list[dict] = []
    dependencies: list[dict] = []

    for node in _function_nodes(tree):
        decorators = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorators.append(decorator.id)
            elif isinstance(decorator, ast.Attribute):
                decorators.append(decorator.attr)

        functions_info.append(
            {
                "name": node.name,
                "line": node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "params": [arg.arg for arg in node.args.args],
                "decorators": decorators,
            }
        )

        called: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name) and child.func.id != node.name:
                    if child.func.id not in called:
                        called.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    if child.func.attr not in called:
                        called.append(child.func.attr)

        dependencies.append(
            {
                "function": node.name,
                "called_functions": [
                    {"called_function": name} for name in called
                ],
            }
        )

    return {
        "functions": functions_info,
        "dependencies": dependencies,
        "total_functions": len(functions_info),
    }