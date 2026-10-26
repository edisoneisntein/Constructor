"""Registro verificable de requisitos (§ Implementation Validator).

Los requisitos se declaran en ``requirements.json`` con referencias a la sección
del documento («sas rea»), criterios de aceptación y comprobaciones concretas. El
registro es la fuente de verdad para el motor de validación.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import ValidationAppError
from app.engines.validation.engine import CHECK_TYPES

REGISTRY_PATH = Path(__file__).with_name("requirements.json")


def workspace_root() -> Path:
    """Raíz del backend (contiene ``app/`` y ``tests/``)."""
    return Path(__file__).resolve().parents[3]


def load_requirements(path: Path | None = None) -> list[dict]:
    source = path or REGISTRY_PATH
    if not source.is_file():
        raise ValidationAppError(f"Registro de requisitos no encontrado: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationAppError(f"Registro de requisitos inválido: {exc}") from exc

    requirements = payload.get("requirements") if isinstance(payload, dict) else payload
    if not isinstance(requirements, list):
        raise ValidationAppError("El registro debe ser una lista de requisitos.")

    seen: set[str] = set()
    for requirement in requirements:
        _validate_requirement(requirement, seen)
    return requirements


def _validate_requirement(requirement: object, seen: set[str]) -> None:
    if not isinstance(requirement, dict):
        raise ValidationAppError("Cada requisito debe ser un objeto.")
    required_keys = {"id", "title", "description", "acceptance_criteria", "checks"}
    missing = required_keys - requirement.keys()
    if missing:
        raise ValidationAppError(f"Requisito sin campos obligatorios: {sorted(missing)}")
    requirement_id = requirement["id"]
    if requirement_id in seen:
        raise ValidationAppError(f"Identificador de requisito duplicado: {requirement_id}")
    seen.add(requirement_id)
    if not isinstance(requirement["acceptance_criteria"], list) or not requirement["acceptance_criteria"]:
        raise ValidationAppError(f"{requirement_id}: faltan criterios de aceptación.")
    checks = requirement["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValidationAppError(f"{requirement_id}: faltan comprobaciones.")
    for check in checks:
        if not isinstance(check, dict) or not {"id", "type"} <= check.keys():
            raise ValidationAppError(f"{requirement_id}: comprobación sin 'id'/'type'.")
        if check["type"] not in CHECK_TYPES:
            raise ValidationAppError(f"{requirement_id}: tipo de comprobación no soportado '{check['type']}'.")
