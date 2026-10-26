"""Plan de migración Gemini → NVIDIA NIM (§11/§12.3).

Genera plan, cambios de dependencias, adaptador, configuración, variables de
entorno de ejemplo, diffs, pruebas propuestas e informe de limitaciones. Las
transformaciones son estructurales y deterministas; las reescrituras de llamadas
se entregan como propuesta manual (no por coincidencia textual, §11).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.engines.change_management.change_engine import unified_diff
from app.engines.migration import sources
from app.engines.migration.models import (
    CompatibilityAssessment,
    MigrationChange,
    Operation,
)

_PY_GEMINI_PKGS = {"google-generativeai", "google-genai"}
_JS_GEMINI_PKGS = {"@google/generative-ai", "@google/genai"}

ADAPTER_PY_PATH = "migration/nim_client.py"
ADAPTER_JS_PATH = "migration/nimClient.ts"
ENV_PATH = ".env.example"

ADAPTER_PY = '''"""Adaptador generado por SIREP para migrar de Gemini a NVIDIA NIM (§12.3).

Traduce una solicitud de texto a la API OpenAI-compatible de NIM. El endpoint,
el modelo y la credencial se leen del entorno; no hay secretos embebidos ni una
URL universal asumida.
"""

from __future__ import annotations

import os

from openai import OpenAI

NIM_BASE_URL = os.environ.get("NIM_BASE_URL", "__NIM_BASE_URL__")
NIM_MODEL = os.environ.get("NIM_MODEL", "__NIM_MODEL__")


def _client() -> OpenAI:
    return OpenAI(base_url=NIM_BASE_URL, api_key=os.environ["NIM_API_KEY"])


def generate_text(prompt: str, *, temperature: float = 0.2) -> str:
    response = _client().chat.completions.create(
        model=NIM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def generate_text_stream(prompt: str):
    stream = _client().chat.completions.create(
        model=NIM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
'''

ADAPTER_JS = """// Adaptador generado por SIREP para migrar de Gemini a NVIDIA NIM (§12.3).
// La API de NIM es compatible con OpenAI. Endpoint, modelo y credencial desde el entorno.
import OpenAI from "openai";

const baseURL = process.env.NIM_BASE_URL ?? "__NIM_BASE_URL__";
const model = process.env.NIM_MODEL ?? "__NIM_MODEL__";

const client = new OpenAI({ baseURL, apiKey: process.env.NIM_API_KEY });

export async function generateText(prompt: string): Promise<string> {
  const response = await client.chat.completions.create({
    model,
    messages: [{ role: "user", content: prompt }],
  });
  return response.choices[0]?.message?.content ?? "";
}
"""


def _change(change_id: str, **kwargs) -> MigrationChange:
    return MigrationChange(change_id=change_id, **kwargs)


def _python_dependency_changes(
    dependencies: list[dict], file_contents: dict[str, str]
) -> list[MigrationChange]:
    changes: list[MigrationChange] = []
    gemini = [dep for dep in dependencies if dep.get("name") in _PY_GEMINI_PKGS]
    if not gemini:
        return changes
    requirements_path = next(
        (path for path in file_contents if path.endswith(("requirements.txt", "requirements-dev.txt"))),
        None,
    )
    if requirements_path:
        before = file_contents[requirements_path]
        lines = before.splitlines()
        kept = [
            line
            for line in lines
            if not any(pkg in line for pkg in _PY_GEMINI_PKGS)
        ]
        after = "\n".join(kept) + ("\n" if before.endswith("\n") or kept else "")
        changes.append(
            _change(
                "dep-py-remove",
                kind="dependency",
                path=requirements_path,
                action="modify",
                description=f"Eliminar {', '.join(sorted({d['name'] for d in gemini}))} de {requirements_path}.",
                diff=unified_diff(requirements_path, before.encode(), after.encode()),
                rule_id="GEMINI-DEP-PY",
            )
        )
    changes.append(
        _change(
            "dep-py-add-openai",
            kind="dependency",
            path=requirements_path or "requirements.txt",
            action="manual",
            description="Añadir 'openai' al manifiesto (la versión exacta la elige el usuario; no se inventa).",
            rule_id="GEMINI-DEP-PY",
        )
    )
    return changes


def _js_dependency_changes(
    dependencies: list[dict], file_contents: dict[str, str]
) -> list[MigrationChange]:
    changes: list[MigrationChange] = []
    gemini = [dep for dep in dependencies if dep.get("name") in _JS_GEMINI_PKGS]
    if not gemini:
        return changes
    package_path = next((path for path in file_contents if path.endswith("package.json")), None)
    if package_path:
        before = file_contents[package_path]
        try:
            data = json.loads(before)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for section in ("dependencies", "devDependencies"):
                block = data.get(section)
                if isinstance(block, dict):
                    for pkg in _JS_GEMINI_PKGS:
                        block.pop(pkg, None)
            after = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            changes.append(
                _change(
                    "dep-js-remove",
                    kind="dependency",
                    path=package_path,
                    action="modify",
                    description=f"Eliminar {', '.join(sorted({d['name'] for d in gemini}))} de {package_path}.",
                    diff=unified_diff(package_path, before.encode(), after.encode()),
                    rule_id="GEMINI-DEP-JS",
                )
            )
    changes.append(
        _change(
            "dep-js-add-openai",
            kind="dependency",
            path=package_path or "package.json",
            action="manual",
            description="Añadir 'openai' como dependencia (versión a criterio del usuario).",
            rule_id="GEMINI-DEP-JS",
        )
    )
    return changes


def _adapter_changes(operations: list[Operation], settings: Settings) -> list[MigrationChange]:
    changes: list[MigrationChange] = []
    languages = {operation.language for operation in operations}
    generative = any(
        operation.kind in {"generation", "streaming", "embedding", "tool_calling"} for operation in operations
    )
    if not generative:
        return changes
    if "python" in languages:
        content = ADAPTER_PY.replace("__NIM_BASE_URL__", settings.nim_base_url).replace(
            "__NIM_MODEL__", settings.nim_model
        )
        changes.append(
            _change(
                "adapter-py",
                kind="adapter",
                path=ADAPTER_PY_PATH,
                action="add",
                description="Adaptador Python hacia NIM (endpoint/modelo configurables).",
                diff=unified_diff(ADAPTER_PY_PATH, None, content.encode()),
                rule_id="GEMINI-CLIENT-ADAPTER",
            )
        )
    if languages & {"javascript", "typescript"}:
        content = ADAPTER_JS.replace("__NIM_BASE_URL__", settings.nim_base_url).replace(
            "__NIM_MODEL__", settings.nim_model
        )
        changes.append(
            _change(
                "adapter-js",
                kind="adapter",
                path=ADAPTER_JS_PATH,
                action="add",
                description="Adaptador JS/TS hacia NIM.",
                diff=unified_diff(ADAPTER_JS_PATH, None, content.encode()),
                rule_id="GEMINI-CLIENT-ADAPTER",
            )
        )
    return changes


def _env_changes(operations: list[Operation], settings: Settings, file_contents: dict[str, str]) -> list[MigrationChange]:
    if not any(operation.kind == "env_var" for operation in operations):
        return []
    before = file_contents.get(ENV_PATH, "")
    block = (
        "# NVIDIA NIM (migración desde Gemini, §12)\n"
        f"NIM_BASE_URL={settings.nim_base_url}\n"
        "NIM_API_KEY=REEMPLAZAR-CON-CLAVE-REAL\n"
        f"NIM_MODEL={settings.nim_model}\n"
    )
    if "NIM_API_KEY" in before:
        return []
    after = (before + ("\n" if before and not before.endswith("\n") else "")) + block
    return [
        _change(
            "env-nim",
            kind="env",
            path=ENV_PATH,
            action="modify" if before else "add",
            description="Añadir variables de entorno de NIM (sin secretos reales).",
            diff=unified_diff(ENV_PATH, before.encode() if before else None, after.encode()),
            rule_id="GEMINI-ENV",
        )
    ]


def build_plan(
    *,
    operations: list[Operation],
    limitations: list[str],
    settings: Settings,
    assessments: list[CompatibilityAssessment],
    dependencies: list[dict] | None = None,
    file_contents: dict[str, str] | None = None,
) -> dict:
    dependencies = dependencies or []
    file_contents = file_contents or {}

    changes: list[MigrationChange] = []
    changes.extend(_python_dependency_changes(dependencies, file_contents))
    changes.extend(_js_dependency_changes(dependencies, file_contents))
    changes.extend(_adapter_changes(operations, settings))
    changes.extend(_env_changes(operations, settings, file_contents))

    manual_operations = [
        operation.kind
        for operation in operations
        if operation.kind in {"generation", "streaming", "tool_calling", "structured_output", "multimodal"}
    ]
    if manual_operations:
        changes.append(
            _change(
                "call-rewrite-manual",
                kind="manual",
                path=None,
                action="manual",
                description=(
                    "Reescribir las llamadas de Gemini (" + ", ".join(sorted(set(manual_operations))) + ") "
                    "contra el adaptador. Requiere revisión humana; no se aplica automáticamente (§11)."
                ),
                reversible=False,
                rule_id="GEMINI-CALL-REWRITE",
            )
        )

    plan_limitations = list(limitations)
    plan_limitations.append(
        "La equivalencia funcional de las operaciones migradas NO está verificada sin credenciales "
        "de NVIDIA NIM (§1.1, §12.2)."
    )
    plan_limitations.append(sources.DISCLAIMER)
    for assessment in assessments:
        if assessment.functional_equivalence == "UNKNOWN":
            plan_limitations.append(
                f"Compatibilidad funcional de '{assessment.operation_kind}' no verificada (NOT_VERIFIED)."
            )

    proposed_tests = [
        "El proyecto no declara dependencias de Google Gemini tras el cambio.",
        "El adaptador referencia NIM_BASE_URL y NIM_MODEL del entorno.",
        "El archivo de entorno define NIM_API_KEY sin valores reales.",
        "Integración real contra NIM (BLOCKED: requiere credenciales).",
    ]

    return {
        "source_provider": "Google Gemini",
        "target_provider": "NVIDIA NIM",
        "target_base_url": settings.nim_base_url,
        "target_model": settings.nim_model,
        "operations": [operation.to_dict() for operation in operations],
        "compatibility_matrix": [assessment.to_dict() for assessment in assessments],
        "changes": [change.to_dict() for change in changes],
        "proposed_tests": proposed_tests,
        "limitations": plan_limitations,
        "sources": sources.SOURCES,
        "verified_at": sources.VERIFIED_AT,
    }


def load_file_contents(root: Path, relative_paths: list[str]) -> dict[str, str]:
    """Carga el contenido de manifiestos conocidos para calcular diffs reales."""
    contents: dict[str, str] = {}
    for relative in relative_paths:
        target = root / relative
        if target.is_file():
            try:
                contents[relative] = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return contents
