"""Modelos de datos del motor de migración (§11, §12)."""

from __future__ import annotations

from dataclasses import dataclass, field

# Categorías de compatibilidad exigidas por §12.2.
# DIRECTLY_COMPATIBLE · COMPATIBLE_WITH_ADAPTER · PARTIAL_COMPATIBILITY ·
# REQUIRES_REDESIGN · UNSUPPORTED · NOT_VERIFIED
COMPATIBILITY_CATEGORIES = (
    "DIRECTLY_COMPATIBLE",
    "COMPATIBLE_WITH_ADAPTER",
    "PARTIAL_COMPATIBILITY",
    "REQUIRES_REDESIGN",
    "UNSUPPORTED",
    "NOT_VERIFIED",
)

# Categorías de operación detectada (§12.1).
OPERATION_KINDS = (
    "sdk_import",
    "client_init",
    "generation",
    "streaming",
    "embedding",
    "tool_calling",
    "structured_output",
    "multimodal",
    "model_config",
    "env_var",
    "rest_call",
    "error_handling",
)


@dataclass
class Operation:
    """Una operación de Gemini detectada en el código (§12.1)."""

    kind: str
    language: str
    file_path: str
    line: int
    snippet: str
    evidence_level: str = "DIRECT_EVIDENCE"
    detection_method: str = "ast_or_pattern"
    model: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "language": self.language,
            "file_path": self.file_path,
            "line": self.line,
            "snippet": self.snippet,
            "evidence_level": self.evidence_level,
            "detection_method": self.detection_method,
            "model": self.model,
            "detail": self.detail,
        }


@dataclass
class CompatibilityAssessment:
    """Evaluación de compatibilidad de una operación (§12.2)."""

    operation_kind: str
    category: str
    source_provider: str
    source_api: str
    target_provider: str
    target_endpoint: str
    target_model: str
    # La compatibilidad de protocolo y la equivalencia funcional se distinguen.
    protocol_compatibility: str
    functional_equivalence: str
    criteria: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "operation_kind": self.operation_kind,
            "category": self.category,
            "source_provider": self.source_provider,
            "source_api": self.source_api,
            "target_provider": self.target_provider,
            "target_endpoint": self.target_endpoint,
            "target_model": self.target_model,
            "protocol_compatibility": self.protocol_compatibility,
            "functional_equivalence": self.functional_equivalence,
            "criteria": self.criteria,
            "notes": self.notes,
        }


@dataclass
class MigrationChange:
    """Un cambio propuesto por el plan de migración (§11/§12.3/§15)."""

    change_id: str
    kind: str  # dependency | adapter | env | config | manual
    path: str | None
    action: str  # add | modify | remove | manual
    description: str
    diff: str | None = None
    reversible: bool = True
    rule_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "kind": self.kind,
            "path": self.path,
            "action": self.action,
            "description": self.description,
            "diff": self.diff,
            "reversible": self.reversible,
            "rule_id": self.rule_id,
        }
