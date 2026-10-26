"""Analizador estático de Python basado en el AST estándar (§5.2/§5.3).

Usa ``ast`` (parser real del lenguaje), no expresiones regulares, para imports,
símbolos, variables de entorno, rutas, entry points y patrones inseguros.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.engines.analysis.facts import (
    CallRef,
    EnvVarRef,
    FileFacts,
    ImportRef,
    InsecurePattern,
    RouteRef,
    StringRef,
    SymbolRef,
)

_ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "route", "head", "options"}

# §5.2/§12: uso directo de SDK de proveedores de IA.
_PROVIDER_CALLS = {
    "genai.configure",
    "generativeai.configure",
    "google.generativeai.configure",
    "vertexai.init",
    "aiplatform.init",
    "genai.GenerativeModel",
    "openai.OpenAI",
    "openai.AzureOpenAI",
}
_PROVIDER_CALL_SUFFIXES = (".generate_content", ".generatecontent", ".getgenerativemodel")
_MODEL_RE = re.compile(r"(gemini|models/[a-z0-9._-]{3,}|gpt-[a-z0-9-]+|claude-[a-z0-9-]+)", re.IGNORECASE)
_SECRET_NAME_RE = re.compile(r"(api[_-]?key|secret|token|password|passwd|access[_-]?key|private[_-]?key)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(
    r"(reemplazar|change[_-]?me|your[_-]|placeholder|example|dummy|xxxx|todo|insecure)", re.IGNORECASE
)


def _looks_like_model(value: str) -> bool:
    return len(value) <= 80 and bool(_MODEL_RE.search(value))


def _looks_like_secret(value: str) -> bool:
    if len(value) < 16:
        return False
    if _PLACEHOLDER_RE.search(value):
        return False
    has_alpha = any(c.isalpha() for c in value)
    has_digit = any(c.isdigit() for c in value)
    return (has_alpha and has_digit) or len(value) >= 32
_INSECURE_FUNCTIONS = {
    "eval": ("EVAL", "HIGH", "Uso de eval() sobre datos potencialmente no confiables."),
    "exec": ("EXEC", "HIGH", "Uso de exec() sobre datos potencialmente no confiables."),
    "os.system": ("OS_SYSTEM", "HIGH", "Ejecución de comandos vía os.system()."),
    "pickle.loads": ("PICKLE_LOADS", "MEDIUM", "Deserialización insegura con pickle.loads()."),
    "yaml.load": ("YAML_LOAD", "MEDIUM", "yaml.load sin Loader seguro."),
}


def _dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    if isinstance(current, ast.Call):
        return None
    return None


def _constant_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.imports: list[ImportRef] = []
        self.functions: list[SymbolRef] = []
        self.classes: list[SymbolRef] = []
        self.env_vars: list[EnvVarRef] = []
        self.calls: list[CallRef] = []
        self.routes: list[RouteRef] = []
        self.insecure: list[InsecurePattern] = []
        self.provider_calls: list[CallRef] = []
        self.model_refs: list[StringRef] = []
        self.hardcoded_secrets: list[InsecurePattern] = []
        self.entry_point = False
        self._class_depth = 0

    # -- imports -----------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportRef(module=alias.name, names=[alias.asname or alias.name], line=node.lineno, kind="import"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = ("." * int(node.level or 0)) + (node.module or "")
        self.imports.append(
            ImportRef(
                module=node.module or "",
                names=[alias.name for alias in node.names],
                line=node.lineno,
                kind="from",
                level=int(node.level or 0),
            )
        )
        self.generic_visit(node)

    # -- symbols -----------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if self._class_depth > 0 else "function"
        self.functions.append(SymbolRef(name=node.name, line=node.lineno, kind=kind))
        self._scan_decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        kind = "method" if self._class_depth > 0 else "async_function"
        self.functions.append(SymbolRef(name=node.name, line=node.lineno, kind=kind, is_async=True))
        self._scan_decorators(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(SymbolRef(name=node.name, line=node.lineno, kind="class"))
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    # -- env vars ----------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        callee = _dotted_name(node.func)
        if callee:
            self.calls.append(CallRef(callee=callee, line=node.lineno, is_new=False))
            lowered = callee.lower()
            if callee in _PROVIDER_CALLS or lowered.endswith(_PROVIDER_CALL_SUFFIXES):
                self.provider_calls.append(CallRef(callee=callee, line=node.lineno))
            if callee in {"os.getenv", "os.environ.get"} and node.args:
                name = _constant_str(node.args[0])
                if name:
                    self.env_vars.append(EnvVarRef(name=name, line=node.lineno))
            if callee in {"subprocess.run", "subprocess.call", "subprocess.Popen"}:
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        self.insecure.append(
                            InsecurePattern(
                                rule="SUBPROCESS_SHELL_TRUE",
                                line=node.lineno,
                                snippet="subprocess con shell=True",
                                severity="HIGH",
                            )
                        )
            for rule_key, (rule, severity, message) in _INSECURE_FUNCTIONS.items():
                if callee == rule_key:
                    self.insecure.append(
                        InsecurePattern(rule=rule, line=node.lineno, snippet=message, severity=severity)
                    )
            for keyword in node.keywords:
                if keyword.arg and _SECRET_NAME_RE.search(keyword.arg):
                    value = _constant_str(keyword.value)
                    if value and _looks_like_secret(value):
                        self.hardcoded_secrets.append(
                            InsecurePattern(
                                rule="HARDCODED_SECRET",
                                line=node.lineno,
                                snippet=f"Posible secreto embebido en argumento {keyword.arg}",
                                severity="MEDIUM",
                            )
                        )
        self.generic_visit(node)

    # -- model refs / hardcoded secrets -----------------------------------
    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _looks_like_model(node.value):
            self.model_refs.append(StringRef(value=node.value, line=node.lineno))
        self.generic_visit(node)

    def _check_secret_assignment(self, name: str, value_node: ast.AST | None, line: int) -> None:
        if not _SECRET_NAME_RE.search(name) or value_node is None:
            return
        value = _constant_str(value_node)
        if value and _looks_like_secret(value):
            self.hardcoded_secrets.append(
                InsecurePattern(
                    rule="HARDCODED_SECRET",
                    line=line,
                    snippet=f"Posible secreto embebido en {name}",
                    severity="MEDIUM",
                )
            )

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._check_secret_assignment(target.id, node.value, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            self._check_secret_assignment(node.target.id, node.value, node.lineno)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        target = _dotted_name(node.value)
        if target == "os.environ":
            name = _constant_str(node.slice)
            if name:
                self.env_vars.append(EnvVarRef(name=name, line=node.lineno))
        self.generic_visit(node)

    # -- entry point / routes ---------------------------------------------
    def visit_If(self, node: ast.If) -> None:
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and test.comparators
            and _constant_str(test.comparators[0]) == "__main__"
        ):
            self.entry_point = True
        self.generic_visit(node)

    def _scan_decorators(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr.lower() not in _ROUTE_METHODS:
                continue
            path_value = _constant_str(decorator.args[0]) if decorator.args else None
            if path_value is None:
                continue
            framework = "fastapi-flask-like"
            self.routes.append(
                RouteRef(method=func.attr.upper(), path=path_value, line=decorator.lineno, framework=framework)
            )


def analyze_python_file(relative_path: str, source: str) -> FileFacts:
    facts = FileFacts(path=relative_path, language="python")
    name = Path(relative_path).name
    facts.has_tests = name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{relative_path}"
    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError as error:
        facts.syntax_error = f"{error.msg} (línea {error.lineno})"
        facts.error_line = error.lineno
        return facts
    docstring = ast.get_docstring(tree)
    facts.docstring = docstring[:280] if docstring else None
    visitor = _PythonVisitor(relative_path)
    visitor.visit(tree)
    facts.imports = visitor.imports
    facts.functions = visitor.functions
    facts.classes = visitor.classes
    facts.env_vars = visitor.env_vars
    facts.calls = visitor.calls
    facts.api_routes = visitor.routes
    facts.entry_point = visitor.entry_point
    facts.insecure_patterns = visitor.insecure
    facts.provider_calls = visitor.provider_calls
    facts.model_refs = visitor.model_refs
    facts.hardcoded_secrets = visitor.hardcoded_secrets
    if not facts.has_tests:
        facts.has_tests = any(fn.name.startswith("test_") for fn in facts.functions)
    return facts
