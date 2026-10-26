"""Orquestador del análisis estático de código fuente (§5, §7, §20).

Flujo: recorrido acotado → detección de lenguaje → manifiestos/dependencias →
análisis AST (Python y JS/TS) → hallazgos con evidencia → grafo de arquitectura.

Fase 3: más relaciones de grafo (símbolos, variables de entorno, integraciones,
rutas, entrypoints, tests y dependencias declaradas) y más reglas (pruebas,
secretos embebidos, referencias a modelos de proveedores).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.ids import new_id
from app.engines.analysis import integrations
from app.engines.analysis.facts import FileFacts
from app.engines.analysis.js_analyzer import run_js_bridge
from app.engines.analysis.language_detect import (
    is_manifest,
    known_unsupported_language,
    language_for_path,
    should_skip_dir,
)
from app.engines.analysis.manifest_parser import parse_manifest
from app.engines.analysis.python_analyzer import analyze_python_file
from app.engines.graph.architecture_graph import GraphBuilder

ProgressCallback = Callable[[str, int, int], None]
CancelCheck = Callable[[], bool]

MAX_FILES_DEFAULT = 20_000
MAX_SYMBOL_NODES_PER_FILE = 500
_MODEL_SCAN_LIMIT = 200_000

_MODEL_TEXT_RE = re.compile(r"""["']([A-Za-z0-9@/._-]*gemini[A-Za-z0-9@/._-]*)["']""", re.IGNORECASE)

# Pistas de variable de entorno por proveedor para relaciones inferidas (§7).
_PROVIDER_ENV_HINTS: dict[str, tuple[str, ...]] = {
    "google_gemini": ("gemini", "genai", "vertex", "google"),
    "nvidia_nim": ("nim", "nvidia"),
    "openai": ("openai",),
    "anthropic": ("anthropic", "claude"),
}


@dataclass
class AnalysisOutput:
    findings: list[dict[str, Any]] = field(default_factory=list)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


@dataclass
class _FileEntry:
    absolute: Path
    relative: str
    language: str


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name.strip().lower())


def _resolve_declared_dependency(specifier: str, dep_name_map: dict[str, str]) -> str | None:
    parts = _normalize_name(specifier).split("_")
    for index in range(len(parts), 0, -1):
        candidate = "_".join(parts[:index])
        if candidate in dep_name_map:
            return dep_name_map[candidate]
    return None


def _guess_provider_from_call(callee: str) -> str | None:
    low = callee.lower()
    if "generativeai" in low or "genai" in low or "vertexai" in low or "aiplatform" in low:
        return "google_gemini"
    if "openai" in low:
        return "openai"
    if "anthropic" in low or "claude" in low:
        return "anthropic"
    return None


def _scan_model_strings(source: str) -> list[tuple[str, int]]:
    text = source[:_MODEL_SCAN_LIMIT]
    results: list[tuple[str, int]] = []
    line = 1
    cursor = 0
    for match in _MODEL_TEXT_RE.finditer(text):
        line += text.count("\n", cursor, match.start())
        cursor = match.start()
        results.append((match.group(1), line))
    return results


def _walk(root: Path, max_files: int) -> tuple[list[_FileEntry], list[str], list[str]]:
    source_files: list[_FileEntry] = []
    manifests: list[str] = []
    unsupported: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for filename in filenames:
            if len(source_files) + len(manifests) >= max_files:
                return source_files, manifests, unsupported
            absolute = Path(dirpath) / filename
            relative = absolute.relative_to(root).as_posix()
            if is_manifest(absolute):
                manifests.append(relative)
                continue
            language = language_for_path(absolute)
            if language:
                source_files.append(_FileEntry(absolute, relative, language))
            elif known_unsupported_language(absolute):
                unsupported.append(relative)
    return source_files, manifests, unsupported


def _python_module_candidates(importer_relative: str, module: str, level: int) -> list[str]:
    module_path = module.replace(".", "/") if module else ""
    if level and level > 0:
        base = Path(importer_relative).parent
        for _ in range(level - 1):
            base = base.parent
        candidates = []
        if module_path:
            candidates.append((base / module_path).as_posix())
        else:
            candidates.append(base.as_posix())
        return candidates
    return [module_path, Path(module_path).as_posix()] if module_path else []


def _resolve_internal_python(importer: str, module: str, level: int, known: set[str]) -> str | None:
    for base in _python_module_candidates(importer, module, level):
        if not base:
            continue
        for suffix in (".py", ".pyi", "/__init__.py"):
            candidate = f"{base}{suffix}"
            if candidate in known:
                return candidate
    return None


_JS_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", "/index.ts", "/index.tsx", "/index.js", "/index.jsx"]


def _resolve_internal_js(importer: str, specifier: str, known: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    base = (Path(importer).parent / specifier).as_posix()
    base = str(Path(base))  # normaliza "./" y ".."
    base = base.replace(os.sep, "/")
    import posixpath

    base = posixpath.normpath(base)
    if base in known:
        return base
    for suffix in _JS_EXTENSIONS:
        candidate = f"{base}{suffix}"
        if candidate in known:
            return candidate
    return None


def _finding(
    *,
    analysis_id: str,
    project_id: str,
    organization_id: str,
    created_at: str,
    category: str,
    severity: str,
    message: str,
    evidence_level: str,
    detection_method: str,
    tool: str,
    file_path: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    symbol: str | None = None,
    language: str | None = None,
    snippet: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": new_id("fnd"),
        "analysis_id": analysis_id,
        "project_id": project_id,
        "organization_id": organization_id,
        "category": category,
        "severity": severity,
        "language": language,
        "file_path": file_path,
        "line_start": line_start,
        "line_end": line_end,
        "symbol": symbol,
        "evidence_level": evidence_level,
        "detection_method": detection_method,
        "tool": tool,
        "tool_version": None,
        "snippet": snippet,
        "message": message,
        "metadata": json.dumps(metadata or {}, ensure_ascii=False) if metadata else None,
        "created_at": created_at,
    }


def run_source_analysis(
    root: Path,
    *,
    analysis_id: str,
    project_id: str,
    organization_id: str,
    created_at: str,
    analysis_max_file_bytes: int,
    js_timeout_seconds: int,
    rea=None,
    deep_analysis: bool = False,
    is_cancelled: CancelCheck | None = None,
    progress: ProgressCallback | None = None,
    sandbox_limits: dict[str, Any] | None = None,
) -> AnalysisOutput:
    def report(phase: str, completed: int, total: int) -> None:
        if progress:
            progress(phase, completed, total)

    def cancelled() -> bool:
        return bool(is_cancelled and is_cancelled())

    output = AnalysisOutput()
    source_files, manifests, unsupported = _walk(root, MAX_FILES_DEFAULT)
    if unsupported:
        output.limitations.append(
            f"{len(unsupported)} archivos con lenguajes reconocidos pero no analizados con AST en el MVP."
        )

    known = {entry.relative for entry in source_files}
    graph = GraphBuilder()
    languages: dict[str, int] = {}

    # 1) Manifiestos primero: los nodos de dependencia se requieren para enlazar imports.
    report("manifests", 0, len(manifests))
    dep_name_map: dict[str, str] = {}
    for index, relative in enumerate(manifests, start=1):
        if cancelled():
            raise KeyboardInterrupt
        manifest_path = root / relative
        declarations = parse_manifest(manifest_path, relative)
        if declarations or manifest_path.name == "package.json":
            manifest_node = graph.add_manifest_node(relative, filename=manifest_path.name)
            for decl in declarations:
                dep_node = graph.add_dependency_node(
                    decl.ecosystem,
                    decl.name,
                    version=decl.version,
                    evidence_level="DIRECT_EVIDENCE",
                    detection_method="declared_dependency",
                )
                dep_name_map.setdefault(_normalize_name(decl.name), dep_node)
                graph.add_edge(
                    manifest_node,
                    edge_type="declares_dependency",
                    evidence_level="DIRECT_EVIDENCE",
                    detection_method="manifest_parse",
                    target_node_id=dep_node,
                    metadata={"source_file": relative, "version": decl.version},
                )
                output.dependencies.append(
                    {
                        "id": new_id("dep"),
                        "analysis_id": analysis_id,
                        "project_id": project_id,
                        "organization_id": organization_id,
                        "ecosystem": decl.ecosystem,
                        "name": decl.name,
                        "version": decl.version,
                        "source_file": relative,
                        "evidence_level": "DIRECT_EVIDENCE",
                        "created_at": created_at,
                    }
                )
        report("manifests", index, len(manifests))

    # 2) Análisis TS/JS por bridge (Node + @babel/parser).
    report("analyze", 0, len(source_files))
    js_entries = [e for e in source_files if e.language in {"javascript", "typescript"}]
    ts_js_facts: dict[str, FileFacts] = {}
    if js_entries:
        report("analyze_ts_js", 0, 1)
        if cancelled():
            raise KeyboardInterrupt
        bridge = run_js_bridge(
            root,
            timeout_seconds=js_timeout_seconds,
            max_file_bytes=analysis_max_file_bytes,
            max_files=MAX_FILES_DEFAULT,
            limits=sandbox_limits,
        )
        if bridge.blocked_reason:
            output.limitations.append(bridge.blocked_reason)
        for facts in bridge.files:
            ts_js_facts[facts.path] = facts

    # 3) Análisis AST por archivo.
    analyzed_count = 0
    env_usage: list[tuple[str, int]] = []
    providers_seen: set[str] = set()
    for index, entry in enumerate(source_files, start=1):
        if cancelled():
            raise KeyboardInterrupt
        languages[entry.language] = languages.get(entry.language, 0) + 1
        try:
            size = entry.absolute.stat().st_size
        except OSError:
            continue
        if size > analysis_max_file_bytes:
            output.limitations.append(f"Archivo omitido por tamaño: {entry.relative}")
            report("analyze", index, len(source_files))
            continue
        try:
            source = entry.absolute.read_text(encoding="utf-8", errors="replace")
        except OSError:
            report("analyze", index, len(source_files))
            continue

        if entry.language == "python":
            facts = analyze_python_file(entry.relative, source)
        else:
            facts = ts_js_facts.get(entry.relative)
            if facts is None:
                report("analyze", index, len(source_files))
                continue
        analyzed_count += 1
        _emit_file(
            facts,
            source=source,
            graph=graph,
            output=output,
            known=known,
            dep_name_map=dep_name_map,
            env_usage=env_usage,
            providers_seen=providers_seen,
            analysis_id=analysis_id,
            project_id=project_id,
            organization_id=organization_id,
            created_at=created_at,
        )
        report("analyze", index, len(source_files))

    # 4) Relaciones inferidas: SDK de IA importado + variable de entorno que lo configura (§7).
    for provider in sorted(providers_seen):
        hints = _PROVIDER_ENV_HINTS.get(provider)
        if not hints:
            continue
        integ_node = GraphBuilder.integration_node_id(provider)
        for env_name, line in env_usage:
            low = env_name.lower()
            if any(hint in low for hint in hints):
                graph.add_edge(
                    GraphBuilder.env_node_id(env_name),
                    edge_type="configures",
                    evidence_level="STATIC_INFERENCE",
                    detection_method="provider_env_name_heuristic",
                    target_node_id=integ_node,
                    metadata={"provider": provider, "env": env_name},
                )
                output.findings.append(
                    _finding(
                        analysis_id=analysis_id,
                        project_id=project_id,
                        organization_id=organization_id,
                        created_at=created_at,
                        category="AI_INTEGRATION",
                        severity="INFO",
                        message=f"La variable {env_name} parece configurar la integración {provider} (inferido).",
                        evidence_level="STATIC_INFERENCE",
                        detection_method="provider_env_name_heuristic",
                        tool="sirep-source-analysis",
                        symbol=env_name,
                        metadata={"provider": provider, "env": env_name, "line": line},
                    )
                )

    # 5) Un hallazgo de lenguaje por lenguaje real detectado (§20.6).
    for language, count in sorted(languages.items()):
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="LANGUAGE",
                severity="INFO",
                message=f"Se detectó código {language} en {count} archivo(s).",
                evidence_level="DIRECT_EVIDENCE",
                detection_method="extension_and_ast_parse",
                tool="sirep-source-analysis",
                language=language,
                metadata={"files": count},
            )
        )

    # 6) Análisis profundo opcional vía REA (§3.3).
    if deep_analysis and rea is not None:
        report("rea_deep_analysis", 0, 1)
        rea_outcome = rea.analyze_javascript_application(root)
        if rea_outcome.available:
            output.findings.append(
                _finding(
                    analysis_id=analysis_id,
                    project_id=project_id,
                    organization_id=organization_id,
                    created_at=created_at,
                    category="ARCHITECTURE",
                    severity="INFO",
                    message="Análisis profundo JS/Electron completado con REA.",
                    evidence_level="DIRECT_EVIDENCE",
                    detection_method="rea_analyze_javascript_application",
                    tool="rea",
                    metadata={"evidence_id": rea_outcome.evidence_id, "subject_sha256": rea_outcome.subject_sha256},
                )
            )
        else:
            output.limitations.append(f"REA no disponible: {rea_outcome.reason}")
        report("rea_deep_analysis", 1, 1)

    output.nodes = graph.node_records(
        analysis_id=analysis_id, project_id=project_id, organization_id=organization_id, created_at=created_at
    )
    output.edges = graph.edge_records(
        analysis_id=analysis_id, project_id=project_id, organization_id=organization_id, created_at=created_at
    )
    output.summary = {
        "files_analyzed": analyzed_count,
        "files_detected": len(source_files),
        "manifests": len(manifests),
        "languages": languages,
        "node_count": graph.node_count,
        "edge_count": graph.edge_count,
        "confirmed_edge_count": graph.confirmed_edge_count(),
        "inferred_edge_count": graph.inferred_edge_count(),
        "node_type_counts": graph.node_type_counts(),
        "edge_type_counts": graph.edge_type_counts(),
        "dependency_count": len(output.dependencies),
        "finding_count": len(output.findings),
        "unsupported_files": len(unsupported),
    }
    return output


def _emit_file(
    facts: FileFacts,
    *,
    source: str,
    graph: GraphBuilder,
    output: AnalysisOutput,
    known: set[str],
    dep_name_map: dict[str, str],
    env_usage: list[tuple[str, int]],
    providers_seen: set[str],
    analysis_id: str,
    project_id: str,
    organization_id: str,
    created_at: str,
) -> None:
    file_node = graph.add_file_node(
        facts.path,
        language=facts.language,
        evidence_level="DIRECT_EVIDENCE",
        detection_method="ast_parse",
        metadata={"functions": len(facts.functions), "classes": len(facts.classes)},
    )
    if facts.syntax_error:
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="SYNTAX_ERROR",
                severity="MEDIUM",
                message=f"Error de sintaxis: {facts.syntax_error}",
                evidence_level="STATIC_INFERENCE",
                detection_method="ast_parse_failure",
                tool="sirep-source-analysis",
                file_path=facts.path,
                line_start=facts.error_line,
                language=facts.language,
            )
        )
        return

    # Imports → integraciones de IA y relaciones internas/externas.
    for ref in facts.imports:
        specifier = ref.module
        if not specifier:
            continue
        candidates = [specifier]
        if ref.kind == "from":
            candidates.extend(f"{specifier}.{name}" for name in ref.names if name)
        match = None
        matched_specifier = specifier
        for candidate in candidates:
            match = integrations.classify_integration(candidate)
            if match:
                matched_specifier = candidate
                break
        if match:
            providers_seen.add(match.provider)
            integ_node = graph.add_integration_node(match.provider, package_hint=matched_specifier)
            graph.add_edge(
                file_node,
                edge_type="uses",
                evidence_level="DIRECT_EVIDENCE",
                detection_method=match.detection_method,
                target_node_id=integ_node,
                metadata={"specifier": matched_specifier, "line": ref.line},
            )
            output.findings.append(
                _finding(
                    analysis_id=analysis_id,
                    project_id=project_id,
                    organization_id=organization_id,
                    created_at=created_at,
                    category="AI_INTEGRATION",
                    severity="INFO",
                    message=f"Import de integración de IA ({match.provider}): {matched_specifier}",
                    evidence_level="DIRECT_EVIDENCE",
                    detection_method=match.detection_method,
                    tool="sirep-source-analysis",
                    file_path=facts.path,
                    line_start=ref.line,
                    language=facts.language,
                    snippet=matched_specifier,
                    metadata={"provider": match.provider, "package_hint": match.package_hint},
                )
            )
        resolved = None
        if facts.language == "python":
            resolved = _resolve_internal_python(facts.path, specifier, ref.level, known)
        elif facts.language in {"javascript", "typescript"}:
            resolved = _resolve_internal_js(facts.path, specifier, known)
        if resolved:
            graph.add_edge(
                file_node,
                edge_type="imports",
                evidence_level="STATIC_INFERENCE",
                detection_method="ast_import_resolution",
                target_node_id=GraphBuilder.file_node_id(resolved),
                metadata={"specifier": specifier, "line": ref.line},
            )
        else:
            graph.add_edge(
                file_node,
                edge_type="imports_external",
                evidence_level="DIRECT_EVIDENCE",
                detection_method="ast_import_statement",
                target_ref=specifier,
                metadata={"line": ref.line},
            )
            dep_node = _resolve_declared_dependency(specifier, dep_name_map)
            if dep_node:
                graph.add_edge(
                    file_node,
                    edge_type="depends_on",
                    evidence_level="STATIC_INFERENCE",
                    detection_method="import_to_declared_dependency",
                    target_node_id=dep_node,
                    metadata={"specifier": specifier, "line": ref.line},
                )

    # Símbolos (funciones y clases) → nodos + aristas "defines".
    symbols = (facts.classes + facts.functions)[:MAX_SYMBOL_NODES_PER_FILE]
    for symbol in symbols:
        symbol_node = graph.add_symbol_node(
            facts.path, symbol.name, kind=symbol.kind, line=symbol.line, language=facts.language
        )
        graph.add_edge(
            file_node,
            edge_type="defines",
            evidence_level="DIRECT_EVIDENCE",
            detection_method="ast_symbol",
            target_node_id=symbol_node,
            metadata={"kind": symbol.kind, "line": symbol.line},
        )

    # Entry point.
    if facts.entry_point:
        entry_node = graph.add_entrypoint_node(facts.path, language=facts.language)
        graph.add_edge(
            file_node,
            edge_type="is_entrypoint",
            evidence_level="DIRECT_EVIDENCE",
            detection_method="entry_point_detection",
            target_node_id=entry_node,
        )
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="ENTRY_POINT",
                severity="INFO",
                message="Punto de entrada detectado.",
                evidence_level="DIRECT_EVIDENCE",
                detection_method="entry_point_detection",
                tool="sirep-source-analysis",
                file_path=facts.path,
                language=facts.language,
            )
        )

    # Archivos de prueba.
    if facts.has_tests:
        test_node = graph.add_test_node(facts.path, language=facts.language)
        graph.add_edge(
            file_node,
            edge_type="is_test",
            evidence_level="DIRECT_EVIDENCE",
            detection_method="test_file_detection",
            target_node_id=test_node,
        )
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="TEST",
                severity="INFO",
                message="Archivo de pruebas detectado.",
                evidence_level="DIRECT_EVIDENCE",
                detection_method="test_file_detection",
                tool="sirep-source-analysis",
                file_path=facts.path,
                language=facts.language,
                metadata={"functions": [fn.name for fn in facts.functions if fn.name.startswith("test_")]},
            )
        )

    # Rutas de API.
    for route in facts.api_routes:
        route_node = graph.add_route_node(
            route.method, route.path, framework=route.framework, language=facts.language
        )
        graph.add_edge(
            file_node,
            edge_type="exposes",
            evidence_level="DIRECT_EVIDENCE",
            detection_method="decorator_route_detection",
            target_node_id=route_node,
            metadata={"line": route.line},
        )
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="API_ROUTE",
                severity="INFO",
                message=f"Ruta de API {route.method} {route.path}",
                evidence_level="DIRECT_EVIDENCE",
                detection_method="decorator_route_detection",
                tool="sirep-source-analysis",
                file_path=facts.path,
                line_start=route.line,
                language=facts.language,
                symbol=f"{route.method} {route.path}",
                metadata={"framework": route.framework},
            )
        )

    # Variables de entorno → nodos + aristas "reads_env".
    seen_env: set[str] = set()
    for env in facts.env_vars:
        if env.name in seen_env:
            continue
        seen_env.add(env.name)
        env_node = graph.add_env_node(env.name, line=env.line, language=facts.language)
        graph.add_edge(
            file_node,
            edge_type="reads_env",
            evidence_level="DIRECT_EVIDENCE",
            detection_method="environment_access_detection",
            target_node_id=env_node,
            metadata={"line": env.line},
        )
        env_usage.append((env.name, env.line))
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="ENVIRONMENT_VARIABLE",
                severity="INFO",
                message=f"Variable de entorno referenciada: {env.name}",
                evidence_level="DIRECT_EVIDENCE",
                detection_method="environment_access_detection",
                tool="sirep-source-analysis",
                file_path=facts.path,
                line_start=env.line,
                language=facts.language,
                symbol=env.name,
            )
        )

    # Uso directo de SDK de proveedores de IA.
    for call in facts.provider_calls:
        provider = _guess_provider_from_call(call.callee)
        if provider:
            providers_seen.add(provider)
            integ_node = graph.add_integration_node(provider, package_hint=call.callee, detection_method="provider_call_detection")
            graph.add_edge(
                file_node,
                edge_type="uses",
                evidence_level="DIRECT_EVIDENCE",
                detection_method="provider_call_detection",
                target_node_id=integ_node,
                metadata={"callee": call.callee, "line": call.line},
            )
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="AI_INTEGRATION",
                severity="INFO",
                message=f"Uso de SDK de proveedor de IA: {call.callee}",
                evidence_level="DIRECT_EVIDENCE",
                detection_method="provider_call_detection",
                tool="sirep-source-analysis",
                file_path=facts.path,
                line_start=call.line,
                language=facts.language,
                symbol=call.callee,
                metadata={"callee": call.callee, "provider": provider},
            )
        )

    # Referencias a modelos (AST + contenido), deduplicadas por valor.
    models: dict[str, int] = {}
    for ref in facts.model_refs:
        models.setdefault(ref.value, ref.line)
    for value, line in _scan_model_strings(source):
        models.setdefault(value, line)
    for value, line in models.items():
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="AI_INTEGRATION",
                severity="INFO",
                message=f"Referencia a modelo de IA: {value}",
                evidence_level="STATIC_INFERENCE",
                detection_method="string_literal_model_pattern",
                tool="sirep-source-analysis",
                file_path=facts.path,
                line_start=line,
                language=facts.language,
                snippet=value,
                metadata={"model": value},
            )
        )

    # Secretos embebidos (heurística estructural).
    for secret in facts.hardcoded_secrets:
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="INSECURE_PATTERN",
                severity=secret.severity,
                message=f"Posible secreto embebido: {secret.snippet}",
                evidence_level="STATIC_INFERENCE",
                detection_method="secret_assignment_heuristic",
                tool="sirep-source-analysis",
                file_path=facts.path,
                line_start=secret.line,
                language=facts.language,
                symbol=secret.rule,
            )
        )

    # Patrones inseguros.
    for pattern in facts.insecure_patterns:
        output.findings.append(
            _finding(
                analysis_id=analysis_id,
                project_id=project_id,
                organization_id=organization_id,
                created_at=created_at,
                category="INSECURE_PATTERN",
                severity=pattern.severity,
                message=f"Patrón potencialmente inseguro ({pattern.rule}): {pattern.snippet}",
                evidence_level="STATIC_INFERENCE",
                detection_method="ast_insecure_pattern",
                tool="sirep-source-analysis",
                file_path=facts.path,
                line_start=pattern.line,
                language=facts.language,
                symbol=pattern.rule,
            )
        )
