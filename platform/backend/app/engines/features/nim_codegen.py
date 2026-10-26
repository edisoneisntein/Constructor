"""Generación de código asistida por NVIDIA NIM con verificación (§10/§13).

Responsabilidades de este módulo (lógica pura, sin E/S de workspace):

- Construir el prompt de generación a partir del contexto del proyecto
  (árbol de archivos, contenido del archivo objetivo y hallazgos para reparación).
- Extraer y validar la respuesta estructurada del modelo (JSON estricto).
- Verificar cada archivo generado: ruta segura, contenido no vacío y sintaxis
  comprobable. La verificación es honesta: los lenguajes sin comprobador se marcan
  explícitamente como no verificados (§6.2/§10).
"""

from __future__ import annotations

import ast
import json
import posixpath
import re
from dataclasses import dataclass, field

from app.core.errors import ValidationAppError
from app.engines.change_management.change_engine import safe_relative_path

MODES = {"feature", "repair"}

# Lenguajes con comprobador de sintaxis disponible sin dependencias externas.
SYNTAX_CHECKED_LANGUAGES = {"python", "json"}

_EXTENSION_LANGUAGE = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".txt": "text",
    ".sh": "shell",
    ".sql": "sql",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
}

_SYSTEM_PROMPT = (
    "Eres un ingeniero de software senior que propone cambios de código mínimos y "
    "correctos. Devuelves EXCLUSIVAMENTE un objeto JSON válido, sin texto adicional "
    "ni bloques de código Markdown, con esta forma exacta:\n"
    '{"summary": "<resumen breve>", "notes": "<notas y supuestos>", '
    '"files": [{"path": "<ruta relativa>", "content": "<contenido completo del archivo>"}]}\n'
    "Reglas obligatorias:\n"
    "1. Usa rutas relativas dentro del proyecto; nunca rutas absolutas ni '..'.\n"
    "2. Incluye el contenido COMPLETO resultante de cada archivo (no parches).\n"
    "3. Cambia lo mínimo necesario y conserva el estilo existente.\n"
    "4. El código debe ser sintácticamente válido y no incluir secretos ni credenciales.\n"
    "5. Si no puedes cumplir la tarea, devuelve \"files\": [] y explícalo en \"notes\"."
)

# Límites de contexto enviado al proveedor (§14: minimización de datos).
MAX_CONTEXT_FILES = 40
MAX_CONTEXT_FILE_BYTES = 8000
MAX_CONTEXT_TOTAL_BYTES = 60000
MAX_TARGET_FILE_BYTES = 24000
MAX_RAW_OUTPUT_PREVIEW = 800


@dataclass
class CodegenRequest:
    instruction: str
    mode: str
    target_path: str | None = None
    target_content: str | None = None
    file_index: list[str] = field(default_factory=list)
    context_files: list[tuple[str, str]] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    language_hint: str | None = None


@dataclass
class GeneratedFile:
    path: str
    content: str
    language: str
    syntax_checked: bool
    syntax_ok: bool | None
    error: str | None = None


def language_for_path(path: str) -> str:
    _, ext = posixpath.splitext(path.lower())
    return _EXTENSION_LANGUAGE.get(ext, "unknown")


def build_messages(request: CodegenRequest) -> list[dict[str, str]]:
    """Construye los mensajes de chat a partir del contexto del proyecto."""
    if request.mode not in MODES:
        raise ValidationAppError(f"Modo de generación inválido: {request.mode}")

    parts: list[str] = []
    parts.append(f"# Tarea ({request.mode})\n{request.instruction.strip()}")

    if request.file_index:
        listing = "\n".join(f"- {path}" for path in request.file_index[:MAX_CONTEXT_FILES])
        parts.append(f"# Archivos del proyecto (muestra)\n{listing}")

    if request.target_path and request.target_content is not None:
        parts.append(
            f"# Archivo objetivo: {request.target_path}\n"
            f"```\n{request.target_content}\n```"
        )
    elif request.target_path:
        parts.append(f"# Archivo objetivo: {request.target_path} (no existe todavía; se creará)")

    if request.findings:
        lines = []
        for finding in request.findings[:20]:
            location = finding.get("file_path") or request.target_path or "?"
            line = finding.get("line_start")
            loc = f"{location}:{line}" if line else location
            lines.append(
                f"- [{finding.get('severity', 'INFO')}] {finding.get('category', '')} "
                f"({loc}): {finding.get('message', '')}"
            )
        parts.append("# Hallazgos a reparar\n" + "\n".join(lines))

    if request.context_files:
        blocks = []
        for path, content in request.context_files[:MAX_CONTEXT_FILES]:
            blocks.append(f"## {path}\n```\n{content}\n```")
        parts.append("# Contexto adicional\n" + "\n\n".join(blocks))

    parts.append(
        "Responde únicamente con el objeto JSON especificado. Incluye en \"files\" "
        "cada archivo que deba crearse o modificarse."
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def extract_json_object(raw: str) -> dict:
    """Extrae el primer objeto JSON de la respuesta del modelo."""
    if not raw or not raw.strip():
        raise ValidationAppError("El modelo devolvió una respuesta vacía.")
    text = raw.strip()
    if text.startswith("```"):
        # Elimina un bloque de código Markdown si el modelo lo añade.
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValidationAppError(
            "La respuesta del modelo no contiene un objeto JSON válido.",
            details={"preview": raw[:MAX_RAW_OUTPUT_PREVIEW]},
        )
    candidate = text[start : end + 1]
    payload = _parse_json_tolerant(candidate, raw)
    if not isinstance(payload, dict):
        raise ValidationAppError("La respuesta JSON del modelo no es un objeto.")
    return payload


def _parse_json_tolerant(candidate: str, raw: str) -> dict:
    """Parsea el JSON del modelo con tolerancia a errores típicos de los LLM.

    Los modelos de código producen con frecuencia comas finales o caracteres de
    control sin escapar dentro de las cadenas (saltos de línea reales en el
    ``content`` de un archivo). Un ``json.loads`` estricto los rechaza y aborta
    una generación que era válida. Se intenta, en orden: estricto, estricto con
    control chars permitidos y, por último, sin comas finales.
    """
    attempts = (
        candidate,
        None,  # marca: usar strict=False
        _strip_trailing_commas(candidate),
    )
    last_error: json.JSONDecodeError | None = None
    for attempt in attempts:
        try:
            if attempt is None:
                return json.loads(candidate, strict=False)
            return json.loads(attempt)
        except json.JSONDecodeError as exc:
            last_error = exc
    try:
        return json.loads(_strip_trailing_commas(candidate), strict=False)
    except json.JSONDecodeError as exc:
        last_error = exc
    raise ValidationAppError(
        "La respuesta del modelo no es JSON válido.",
        details={"error": str(last_error), "preview": raw[:MAX_RAW_OUTPUT_PREVIEW]},
    ) from last_error


def _strip_trailing_commas(text: str) -> str:
    """Elimina comas finales antes de ``}`` o ``]`` (error frecuente de los LLM)."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def check_syntax(language: str, content: str, path: str) -> tuple[bool, bool | None, str | None]:
    """Devuelve ``(checked, ok, error)`` para un archivo generado."""
    if language == "python":
        try:
            ast.parse(content, filename=path)
        except SyntaxError as exc:
            return True, False, f"Error de sintaxis Python: {exc.msg} (línea {exc.lineno})."
        return True, True, None
    if language == "json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return True, False, f"JSON inválido: {exc.msg} (línea {exc.lineno})."
        return True, True, None
    return False, None, None


def prepare_generated_files(files_payload: object) -> tuple[list[GeneratedFile], list[str]]:
    """Normaliza y verifica los archivos generados.

    Devuelve ``(archivos, errores)``. Los errores son fallos duros (ruta insegura,
    contenido vacío o sintaxis inválida) que impiden persistir el cambio.
    """
    if not isinstance(files_payload, list):
        raise ValidationAppError("El campo 'files' de la respuesta no es una lista.")

    files: list[GeneratedFile] = []
    errors: list[str] = []
    seen: set[str] = set()

    for index, item in enumerate(files_payload):
        if not isinstance(item, dict):
            errors.append(f"Elemento {index} inválido: no es un objeto.")
            continue
        raw_path = item.get("path")
        content = item.get("content")
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"Elemento {index} sin ruta válida.")
            continue
        if not isinstance(content, str):
            errors.append(f"'{raw_path}': el contenido no es texto.")
            continue
        try:
            path = safe_relative_path(raw_path)
        except ValidationAppError as exc:
            errors.append(f"Ruta rechazada '{raw_path}': {exc}")
            continue
        if path in seen:
            errors.append(f"Ruta duplicada en la respuesta: '{path}'.")
            continue
        if not content.strip():
            errors.append(f"'{path}': el contenido generado está vacío.")
            continue

        language = language_for_path(path)
        checked, ok, error = check_syntax(language, content, path)
        if checked and ok is False:
            errors.append(f"{path}: {error}")
        seen.add(path)
        files.append(
            GeneratedFile(
                path=path,
                content=content,
                language=language,
                syntax_checked=checked,
                syntax_ok=ok,
                error=error,
            )
        )

    return files, errors


def parse_response(raw: str) -> tuple[list[GeneratedFile], str, str, list[str]]:
    """Parsea una respuesta cruda del modelo.

    Devuelve ``(archivos, summary, notes, errores_de_verificación)``.
    """
    payload = extract_json_object(raw)
    files, errors = prepare_generated_files(payload.get("files"))
    summary = payload.get("summary") if isinstance(payload.get("summary"), str) else ""
    notes = payload.get("notes") if isinstance(payload.get("notes"), str) else ""
    return files, summary, notes, errors
