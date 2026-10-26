"""Detección de integraciones reales de Google Gemini (§12.1).

Busca SDKs, imports, inicialización de clientes, llamadas de generación,
streaming, function calling, salidas estructuradas, embeddings, entradas
multimodales, variables de entorno, REST y manejo de errores.

No confunde referencias en comentarios o documentación con llamadas ejecutables:
en Python se analiza el AST (que excluye comentarios y textos no ejecutados); en
JS/TS se eliminan los comentarios preservando los números de línea.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.engines.migration.models import Operation

PY_EXTENSIONS = {".py"}
JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

_GEMINI_MODEL_RE = re.compile(r"\bgemini[-_][0-9a-zA-Z.\-]+", re.IGNORECASE)
_ENV_KEY_RE = re.compile(r"(GEMINI_API_KEY|GOOGLE_API_KEY|GOOGLE_GENAI_USE_VERTEXAI)")
_REST_HOST_RE = re.compile(r"generativelanguage\.googleapis\.com")
_SDK_MODULES = {"google.generativeai", "google.genai"}
_CALL_KINDS = {
    "configure": "client_init",
    "GenerativeModel": "client_init",
    "getGenerativeModel": "client_init",
    "generate_content": "generation",
    "generateContent": "generation",
    "generate_content_stream": "streaming",
    "generateContentStream": "streaming",
    "start_chat": "generation",
    "startChat": "generation",
    "send_message": "generation",
    "sendMessage": "generation",
    "embed_content": "embedding",
    "embed_content_batch": "embedding",
    "embedContent": "embedding",
    "batchEmbedContents": "embedding",
    "list_models": "model_config",
    "get_model": "model_config",
    "count_tokens": "model_config",
}
_ERROR_NAMES = ("GoogleGenerativeAIError", "google.api_core", "ResourceExhausted", "GenerativeAIError")


def _strip_js_comments(text: str) -> str:
    """Elimina comentarios JS/TS conservando la longitud y las líneas."""
    out: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        nxt = text[i + 1] if i + 1 < length else ""
        if char == "/" and nxt == "/":
            while i < length and text[i] not in "\r\n":
                i += 1
        elif char == "/" and nxt == "*":
            i += 2
            while i < length and not (text[i] == "*" and i + 1 < length and text[i + 1] == "/"):
                out.append("\n" if text[i] in "\r\n" else " ")
                i += 1
            i += 2
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _python_operations(path: str, source: str) -> tuple[list[Operation], list[str]]:
    operations: list[Operation] = []
    limitations: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return operations, [f"No se pudo analizar {path} (error de sintaxis)."]

    sdk_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _SDK_MODULES or any(
                    alias.name.startswith(module + ".") for module in _SDK_MODULES
                ):
                    sdk_aliases.add(alias.asname or alias.name.split(".")[0])
                    operations.append(
                        Operation(
                            kind="sdk_import",
                            language="python",
                            file_path=path,
                            line=node.lineno,
                            snippet=f"import {alias.name}",
                            detail=alias.name,
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {alias.name for alias in node.names}
            if module in _SDK_MODULES or (module == "google" and names & {"genai", "generativeai"}):
                for alias in node.names:
                    sdk_aliases.add(alias.asname or alias.name)
                operations.append(
                    Operation(
                        kind="sdk_import",
                        language="python",
                        file_path=path,
                        line=node.lineno,
                        snippet=f"from {module} import {', '.join(sorted(names))}",
                        detail=module,
                    )
                )
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
            if name in _CALL_KINDS:
                kind = _CALL_KINDS[name]
                model = _extract_model(node)
                operations.append(
                    Operation(
                        kind=kind,
                        language="python",
                        file_path=path,
                        line=node.lineno,
                        snippet=name,
                        model=model,
                        detection_method="python_ast",
                    )
                )
                operations.extend(_call_sub_operations(path, node, name))
                operations.extend(_detect_multimodal(path, node))
        elif isinstance(node, ast.ExceptHandler):
            type_name = _handled_name(node)
            if type_name and any(needle in type_name for needle in _ERROR_NAMES):
                operations.append(
                    Operation(
                        kind="error_handling",
                        language="python",
                        file_path=path,
                        line=node.lineno,
                        snippet=f"except {type_name}",
                        detail=type_name,
                    )
                )
        elif isinstance(node, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
            for item in _iter_constants(node):
                text = _string_value(item)
                if text and _REST_HOST_RE.search(text):
                    operations.append(
                        Operation(
                            kind="rest_call",
                            language="python",
                            file_path=path,
                            line=getattr(item, "lineno", 0),
                            snippet=text[:120],
                        )
                    )

    operations.extend(_env_operations(path, tree, "python"))
    return _dedupe(operations), limitations


def _iter_constants(node: ast.AST):
    for child in ast.walk(node):
        if isinstance(child, ast.Constant):
            yield child


def _string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _handled_name(handler: ast.ExceptHandler) -> str | None:
    exc = handler.type
    if isinstance(exc, ast.Name):
        return exc.id
    if isinstance(exc, ast.Attribute):
        return exc.attr
    return None


def _extract_model(call: ast.Call) -> str | None:
    for keyword in call.keywords:
        if keyword.arg in {"model", "model_name", "model_id"}:
            value = _string_value(keyword.value)
            if value:
                return value
    if call.args:
        value = _string_value(call.args[0])
        if value and _GEMINI_MODEL_RE.search(value):
            return value
    return None


def _call_sub_operations(path: str, call: ast.Call, name: str) -> list[Operation]:
    operations: list[Operation] = []
    keywords = {keyword.arg for keyword in call.keywords if keyword.arg}
    if "tools" in keywords or "tool_config" in keywords:
        operations.append(
            Operation(kind="tool_calling", language="python", file_path=path, line=call.lineno, snippet=name)
        )
    if "response_schema" in keywords or "response_mime_type" in keywords:
        operations.append(
            Operation(kind="structured_output", language="python", file_path=path, line=call.lineno, snippet=name)
        )
    if name in {"generate_content_stream", "generateContentStream"}:
        operations.append(
            Operation(kind="streaming", language="python", file_path=path, line=call.lineno, snippet=name)
        )
    return operations


def _detect_multimodal(path: str, call: ast.Call) -> list[Operation]:
    snippet = ast.dump(call)
    if "inline_data" in snippet or "from_bytes" in snippet or "image" in snippet.lower():
        if "inline_data" in snippet or "from_bytes" in snippet or "Part" in snippet:
            return [Operation(kind="multimodal", language="python", file_path=path, line=call.lineno, snippet="multimodal content")]
    return []


def _env_operations(path: str, tree: ast.AST, language: str) -> list[Operation]:
    operations: list[Operation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
            if name in {"getenv", "get"} and node.args:
                value = _string_value(node.args[0])
                if value and _ENV_KEY_RE.search(value):
                    operations.append(
                        Operation(kind="env_var", language=language, file_path=path, line=node.lineno, snippet=value, detail=value)
                    )
        elif isinstance(node, ast.Subscript):
            value = _string_value(node.slice) if isinstance(node.slice, ast.Constant) else None
            if value and _ENV_KEY_RE.search(value):
                operations.append(
                    Operation(kind="env_var", language=language, file_path=path, line=node.lineno, snippet=value, detail=value)
                )
    return operations


_JS_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("sdk_import", "@google", re.compile(r"@google/(generative-ai|genai)")),
    ("client_init", "GoogleGenerativeAI", re.compile(r"new\s+GoogleGenerativeAI")),
    ("client_init", "getGenerativeModel", re.compile(r"getGenerativeModel\s*\(")),
    ("streaming", "generateContentStream", re.compile(r"generateContentStream\s*\(")),
    ("generation", "generateContent", re.compile(r"generateContent\s*\(")),
    ("generation", "startChat", re.compile(r"startChat\s*\(")),
    ("embedding", "embedContent", re.compile(r"(embedContent|batchEmbedContents)\s*\(")),
    ("structured_output", "responseSchema", re.compile(r"responseSchema|responseMimeType")),
    ("tool_calling", "functionDeclarations", re.compile(r"functionDeclarations|tools\s*:")),
    ("multimodal", "inlineData", re.compile(r"inlineData|image_url|mimeType")),
    ("rest_call", "generativelanguage", re.compile(r"generativelanguage\.googleapis\.com")),
    ("env_var", "GEMINI_API_KEY", re.compile(r"process\.env\.(GEMINI_API_KEY|GOOGLE_API_KEY)|GEMINI_API_KEY")),
]


def _js_operations(path: str, source: str) -> list[Operation]:
    operations: list[Operation] = []
    cleaned = _strip_js_comments(source)
    for line_no, line in enumerate(cleaned.splitlines(), start=1):
        for kind, label, pattern in _JS_PATTERNS:
            if pattern.search(line):
                operations.append(
                    Operation(
                        kind=kind,
                        language="typescript" if path.endswith((".ts", ".tsx")) else "javascript",
                        file_path=path,
                        line=line_no,
                        snippet=line.strip()[:120],
                        detection_method="js_pattern",
                        detail=label,
                    )
                )
    return _dedupe(operations)


def _dedupe(operations: list[Operation]) -> list[Operation]:
    seen: set[tuple] = set()
    result: list[Operation] = []
    for operation in operations:
        key = (operation.kind, operation.file_path, operation.line, operation.snippet)
        if key not in seen:
            seen.add(key)
            result.append(operation)
    return result


def detect_gemini_operations(root: Path, *, max_file_bytes: int = 2 * 1024 * 1024) -> tuple[list[Operation], list[str]]:
    """Recorre el árbol y devuelve las operaciones Gemini y las limitaciones."""
    operations: list[Operation] = []
    limitations: list[str] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in PY_EXTENSIONS and suffix not in JS_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                limitations.append(f"Omitido {path.name}: supera el tamaño máximo de análisis.")
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        relative = str(path.relative_to(root)).replace("\\", "/")
        if suffix in PY_EXTENSIONS:
            found, notes = _python_operations(relative, source)
            operations.extend(found)
            limitations.extend(notes)
        else:
            operations.extend(_js_operations(relative, source))
    if scanned == 0:
        limitations.append("No se encontraron archivos Python o JS/TS para el detector Gemini.")
    return operations, limitations
