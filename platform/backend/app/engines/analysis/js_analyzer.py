"""Runner del bridge de análisis JS/TS (§5.2).

El parseo real lo hace ``bridges/js_analyze.mjs`` con ``@babel/parser`` (parser
AST, no regex). Este módulo localiza Node y el parser, ejecuta el bridge con
límites y normaliza su salida a :class:`FileFacts`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.engines.analysis.facts import (
    CallRef,
    EnvVarRef,
    FileFacts,
    ImportRef,
    InsecurePattern,
    SymbolRef,
)

BRIDGE_PATH = Path(__file__).resolve().parents[3] / "bridges" / "js_analyze.mjs"


@dataclass
class JsBridgeResult:
    files: list[FileFacts]
    blocked_reason: str | None
    parser_path: str | None
    node_path: str | None
    skipped: list[dict[str, str]]


def find_node() -> str | None:
    return shutil.which("node")


def find_babel_parser() -> str | None:
    """Localiza @babel/parser sin instalar dependencias nuevas.

    Orden: variable de entorno → instalación local del bridge → caché de npx (REA).
    """
    override = os.environ.get("SIREP_BABEL_PARSER")
    if override and Path(override).is_file():
        return override
    local = BRIDGE_PATH.parent / "node_modules" / "@babel" / "parser" / "lib" / "index.js"
    if local.is_file():
        return str(local)
    candidates = sorted(Path.home().glob(".npm/_npx/*/node_modules/@babel/parser/lib/index.js"))
    if candidates:
        return str(candidates[0])
    return None


def _to_facts(raw: dict) -> FileFacts:
    language = raw.get("language", "javascript")
    facts = FileFacts(path=raw.get("path", "?"), language=language)
    if not raw.get("parse_ok", True):
        facts.syntax_error = raw.get("error") or "Error de parseo"
        facts.error_line = raw.get("parse_error_line")
        return facts
    for item in raw.get("imports", []):
        facts.imports.append(
            ImportRef(module=item.get("source", ""), names=item.get("names", []), line=item.get("line", 0), kind="import")
        )
    for item in raw.get("requires", []):
        facts.imports.append(
            ImportRef(module=item.get("source", ""), names=[], line=item.get("line", 0), kind="require")
        )
    for item in raw.get("functions", []):
        facts.functions.append(
            SymbolRef(name=item.get("name", "?"), line=item.get("line", 0), kind="function", is_async=bool(item.get("is_async")))
        )
    for item in raw.get("classes", []):
        facts.classes.append(SymbolRef(name=item.get("name", "?"), line=item.get("line", 0), kind="class"))
    for item in raw.get("env_vars", []):
        facts.env_vars.append(EnvVarRef(name=item.get("name", "?"), line=item.get("line", 0)))
    for item in raw.get("calls", []):
        facts.calls.append(CallRef(callee=item.get("callee", "?"), line=item.get("line", 0), is_new=bool(item.get("is_new"))))
    facts.entry_point = bool(raw.get("has_default_export"))
    name = Path(facts.path).name.lower()
    facts.has_tests = name.startswith("test") or name.endswith(".test.ts") or name.endswith(".test.js") or name.endswith(".spec.ts") or name.endswith(".spec.js")
    if facts.has_tests:
        pass
    # Detección mínima de patrones inseguros por nombre de llamada (evidencia estática).
    for call in facts.calls:
        if call.callee == "eval":
            facts.insecure_patterns.append(
                InsecurePattern(rule="EVAL", line=call.line, snippet="Uso de eval() en JavaScript.", severity="HIGH")
            )
        if call.callee == "child_process.exec":
            facts.insecure_patterns.append(
                InsecurePattern(rule="CHILD_PROCESS_EXEC", line=call.line, snippet="Uso de child_process.exec().", severity="HIGH")
            )
    return facts


def run_js_bridge(
    root: Path,
    *,
    timeout_seconds: int,
    max_file_bytes: int,
    max_files: int,
    limits: dict | None = None,
) -> JsBridgeResult:
    node = find_node()
    if node is None:
        return JsBridgeResult([], "Node.js no está disponible en el entorno.", None, None, [])
    parser_path = find_babel_parser()
    if parser_path is None:
        return JsBridgeResult(
            [],
            "No se localizó @babel/parser; el análisis TS/JS profundo no está disponible.",
            None,
            node,
            [],
        )
    command = [
        node,
        str(BRIDGE_PATH),
        "--root",
        str(root),
        "--parser",
        parser_path,
        "--max-file-bytes",
        str(max_file_bytes),
        "--max-files",
        str(max_files),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            **(limits or {}),
        )
    except subprocess.TimeoutExpired:
        return JsBridgeResult([], "El análisis TS/JS excedió el tiempo límite.", parser_path, node, [])
    if completed.returncode != 0 and not completed.stdout.strip():
        return JsBridgeResult(
            [],
            f"El bridge TS/JS falló: {completed.stderr.strip()[:200]}",
            parser_path,
            node,
            [],
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return JsBridgeResult([], "El bridge TS/JS devolvió JSON inválido.", parser_path, node, [])
    if payload.get("parser_resolved") is False:
        return JsBridgeResult([], payload.get("error") or "Parser no resuelto.", None, node, [])
    files = [_to_facts(item) for item in payload.get("files", [])]
    return JsBridgeResult(files, None, parser_path, node, payload.get("skipped", []))
