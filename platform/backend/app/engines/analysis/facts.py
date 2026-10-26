"""Estructuras de hechos extraídos por el análisis estático (§5).

Separadas de la persistencia para poder probarlas de forma aislada.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportRef:
    module: str
    names: list[str]
    line: int
    kind: str  # import | from | require
    level: int = 0


@dataclass
class SymbolRef:
    name: str
    line: int
    kind: str  # function | async_function | class | method
    is_async: bool = False


@dataclass
class EnvVarRef:
    name: str
    line: int


@dataclass
class CallRef:
    callee: str
    line: int
    is_new: bool = False


@dataclass
class RouteRef:
    method: str
    path: str
    line: int
    framework: str


@dataclass
class InsecurePattern:
    rule: str
    line: int
    snippet: str
    severity: str


@dataclass
class StringRef:
    value: str
    line: int


@dataclass
class FileFacts:
    path: str
    language: str
    imports: list[ImportRef] = field(default_factory=list)
    functions: list[SymbolRef] = field(default_factory=list)
    classes: list[SymbolRef] = field(default_factory=list)
    env_vars: list[EnvVarRef] = field(default_factory=list)
    calls: list[CallRef] = field(default_factory=list)
    api_routes: list[RouteRef] = field(default_factory=list)
    entry_point: bool = False
    has_tests: bool = False
    syntax_error: str | None = None
    insecure_patterns: list[InsecurePattern] = field(default_factory=list)
    docstring: str | None = None
    error_line: int | None = None
    # §5.2/§12: uso real de SDK de proveedores y modelos referenciados.
    provider_calls: list[CallRef] = field(default_factory=list)
    model_refs: list[StringRef] = field(default_factory=list)
    hardcoded_secrets: list[InsecurePattern] = field(default_factory=list)

    @property
    def import_specifiers(self) -> list[str]:
        return [ref.module for ref in self.imports if ref.module]
