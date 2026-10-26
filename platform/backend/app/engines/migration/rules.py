"""Reglas de migración versionadas (§11).

Cada regla incluye: identificador, versión, condiciones de aplicación,
transformación, evidencia, riesgos, limitaciones, pruebas y procedimiento de
reversión. Las transformaciones son estructurales (dependencias, configuración,
scaffolding de adaptador), NUNCA sustituciones ciegas por coincidencia textual.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MigrationRule:
    id: str
    version: str
    title: str
    conditions: str
    transformation: str
    evidence: str
    risks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    rollback: str = ""
    evidence_files: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "conditions": self.conditions,
            "transformation": self.transformation,
            "evidence": self.evidence,
            "risks": list(self.risks),
            "limitations": list(self.limitations),
            "tests": list(self.tests),
            "rollback": self.rollback,
        }


RULES: tuple[MigrationRule, ...] = (
    MigrationRule(
        id="GEMINI-DEP-PY",
        version="1.0.0",
        title="Migrar dependencia Python del SDK de Gemini",
        conditions="El proyecto declara google-generativeai o google-genai y usa el SDK en Python.",
        transformation="Eliminar google-generativeai/google-genai y añadir el cliente openai "
        "apuntando a NIM (base_url configurable).",
        evidence="Dependencia declarada + import real en el código (DIRECT_EVIDENCE).",
        risks=("Cambios en la firma de llamadas requieren revisión manual.",),
        limitations=("No se reescriben automáticamente las llamadas generate_content.",),
        tests=("Dependencia ausente tras migrar.", "Cliente openai importable."),
        rollback="Restaurar el archivo de dependencias desde el change set (§15).",
    ),
    MigrationRule(
        id="GEMINI-DEP-JS",
        version="1.0.0",
        title="Migrar dependencia JS/TS del SDK de Gemini",
        conditions="El proyecto declara @google/generative-ai o @google/genai.",
        transformation="Eliminar el paquete de Google del manifiesto y añadir 'openai' "
        "(o 'openai'-compatible) para hablar con NIM.",
        evidence="Dependencia declarada en package.json (DIRECT_EVIDENCE).",
        risks=("El SDK de Gemini y el cliente OpenAI no son intercambiables sin adaptador.",),
        limitations=("Las llamadas del SDK deben reescribirse contra el adaptador.",),
        tests=("package.json sin @google/generative-ai.",),
        rollback="Restaurar package.json desde el change set (§15).",
    ),
    MigrationRule(
        id="GEMINI-ENV",
        version="1.0.0",
        title="Migrar variables de entorno de credenciales",
        conditions="Se detectan variables GEMINI_API_KEY / GOOGLE_API_KEY.",
        transformation="Añadir NIM_BASE_URL, NIM_API_KEY y NIM_MODEL; retirar la clave Gemini "
        "cuando no se use.",
        evidence="Lectura de variable de entorno en el código (DIRECT_EVIDENCE).",
        risks=("Eliminar la clave Gemini antes de reescribir el código rompe la ejecución.",),
        limitations=("Las claves no se migran automáticamente; el usuario provisiona la de NIM.",),
        tests=("Variables NIM presentes en el ejemplo de entorno.",),
        rollback="Restaurar el archivo de entorno desde el change set (§15).",
    ),
    MigrationRule(
        id="GEMINI-CLIENT-ADAPTER",
        version="1.0.0",
        title="Generar adaptador de cliente NIM",
        conditions="Existe al menos una operación de generación, streaming o embeddings.",
        transformation="Crear un módulo adaptador que traduzca la operación de Gemini a la "
        "API OpenAI-compatible de NIM (endpoint y modelo configurables).",
        evidence="Operaciones detectadas (DIRECT_EVIDENCE).",
        risks=("El adaptador debe ajustarse por modelo (tool calling, multimodalidad).",),
        limitations=("No cubre automáticamente function calling ni multimodalidad compleja.",),
        tests=("El adaptador referencia el endpoint y el modelo configurados.",),
        rollback="Eliminar el archivo adaptador desde el change set (§15).",
    ),
    MigrationRule(
        id="GEMINI-CALL-REWRITE",
        version="1.0.0",
        title="Reescribir llamadas de generación (manual/asistida)",
        conditions="Se detectan llamadas generate_content / start_chat / embed_content.",
        transformation="Propuesta de reescritura a messages/chat.completions; REQUIERE "
        "revisión humana. No se aplica por coincidencia textual (§11).",
        evidence="Llamada real detectada (DIRECT_EVIDENCE).",
        risks=(
            "Diferencias de parámetros (temperature, top_p, safety, system instructions).",
            "Salidas estructuradas y herramientas no son equivalentes 1:1.",
        ),
        limitations=("Se entrega como propuesta, no como parche aplicado automáticamente.",),
        tests=("Verificación de equivalencia funcional pendiente (NOT_VERIFIED)."),
        rollback="No aplica: no se modifica el código automáticamente.",
    ),
)


def get_rule(rule_id: str) -> MigrationRule | None:
    return next((rule for rule in RULES if rule.id == rule_id), None)


def rules_as_dicts() -> list[dict]:
    return [rule.to_dict() for rule in RULES]
