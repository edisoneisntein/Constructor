"""Contratos de API (Pydantic). §17: validación, OpenAPI, errores normalizados.

Los estados y taxonomías siguen literalmente §12.2, §8.4, §18 y §23 del PDF.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class Role(str, Enum):
    owner = "owner"
    admin = "admin"
    developer = "developer"
    viewer = "viewer"


class EvidenceLevel(str, Enum):
    """§1.2 — categorías de evidencia."""

    direct_evidence = "DIRECT_EVIDENCE"
    static_inference = "STATIC_INFERENCE"
    runtime_observation = "RUNTIME_OBSERVATION"
    user_specified = "USER_SPECIFIED"
    unverified = "UNVERIFIED"
    unknown = "UNKNOWN"


class JobStatus(str, Enum):
    """§18 — estados de un trabajo."""

    queued = "QUEUED"
    analyzing = "ANALYZING"
    graph_building = "GRAPH_BUILDING"
    awaiting_approval = "AWAITING_APPROVAL"
    patching = "PATCHING"
    validating = "VALIDATING"
    completed = "COMPLETED"
    completed_with_limitations = "COMPLETED_WITH_LIMITATIONS"
    rolled_back = "ROLLED_BACK"
    failed = "FAILED"
    cancelled = "CANCELLED"
    blocked = "BLOCKED"


class Severity(str, Enum):
    info = "INFO"
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    critical = "CRITICAL"


class FindingCategory(str, Enum):
    language = "LANGUAGE"
    architecture = "ARCHITECTURE"
    dependency = "DEPENDENCY"
    symbol = "SYMBOL"
    import_edge = "IMPORT_EDGE"
    environment_variable = "ENVIRONMENT_VARIABLE"
    entry_point = "ENTRY_POINT"
    api_route = "API_ROUTE"
    test = "TEST"
    insecure_pattern = "INSECURE_PATTERN"
    ai_integration = "AI_INTEGRATION"
    syntax_error = "SYNTAX_ERROR"
    other = "OTHER"


class ArtifactKind(str, Enum):
    source_zip = "SOURCE_ZIP"
    source_directory = "SOURCE_DIRECTORY"
    binary = "BINARY"


class ValidationState(str, Enum):
    pending = "PENDING"
    valid = "VALID"
    rejected = "REJECTED"
    partial = "PARTIAL"


class ChangeStatus(str, Enum):
    """§15 — ciclo de vida de un conjunto de cambios."""

    proposed = "PROPOSED"
    approved = "APPROVED"
    rejected = "REJECTED"
    applied = "APPLIED"
    validated = "VALIDATED"
    rolled_back = "ROLLED_BACK"
    failed = "FAILED"


class ChangeType(str, Enum):
    added = "ADDED"
    modified = "MODIFIED"
    deleted = "DELETED"


# --------------------------------------------------------------------------- #
# Auth / Organizations
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    display_name: str = Field(min_length=1, max_length=120)
    organization_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: str


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    role: Role
    created_at: str


class SessionOut(BaseModel):
    token: str
    expires_at: str
    user: UserOut


# --------------------------------------------------------------------------- #
# Projects / Artifacts
# --------------------------------------------------------------------------- #
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class ProjectOut(BaseModel):
    id: str
    organization_id: str
    name: str
    created_by: str
    created_at: str
    updated_at: str


class ArtifactOut(BaseModel):
    id: str
    project_id: str
    kind: ArtifactKind
    filename: str
    size_bytes: int
    sha256: str
    detected_mime: str
    declared_mime: str | None
    validation_state: ValidationState
    retention_policy: str
    created_at: str


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
class AnalysisCreate(BaseModel):
    artifact_id: str
    deep_analysis: bool = Field(
        default=False,
        description="Habilita el adaptador REA para análisis profundo JS/Electron (opcional).",
    )


class JobOut(BaseModel):
    id: str
    project_id: str
    artifact_id: str
    status: JobStatus
    phase: str | None
    progress_completed: int
    progress_total: int
    error_code: str | None
    error_message: str | None
    result_summary: dict[str, Any] | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class FindingOut(BaseModel):
    id: str
    analysis_id: str
    category: FindingCategory
    severity: Severity
    language: str | None
    file_path: str | None
    line_start: int | None
    line_end: int | None
    symbol: str | None
    evidence_level: EvidenceLevel
    detection_method: str
    tool: str
    tool_version: str | None
    snippet: str | None
    message: str
    metadata: dict[str, Any] | None
    created_at: str


class NodeOut(BaseModel):
    id: str
    node_type: str
    label: str
    path: str | None
    language: str | None
    evidence_level: EvidenceLevel
    detection_method: str
    metadata: dict[str, Any] | None


class EdgeOut(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str | None
    target_ref: str | None
    edge_type: str
    evidence_level: EvidenceLevel
    detection_method: str
    metadata: dict[str, Any] | None


class DependencyOut(BaseModel):
    id: str
    ecosystem: str
    name: str
    version: str | None
    source_file: str
    evidence_level: EvidenceLevel


class ArchitectureGraphOut(BaseModel):
    analysis_id: str
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    dependencies: list[DependencyOut]
    node_count: int
    edge_count: int
    dependency_count: int
    # Relaciones confirmadas (DIRECT_EVIDENCE) vs inferidas (§7 del PDF).
    confirmed_edge_count: int
    inferred_edge_count: int
    # Desglose por tipo para la navegación del grafo (§18).
    node_type_counts: dict[str, int] = Field(default_factory=dict)
    edge_type_counts: dict[str, int] = Field(default_factory=dict)


class NodeDetailOut(BaseModel):
    """Nodo con sus aristas entrantes/salientes y vecinos (§7/§18)."""

    node: NodeOut
    outgoing_edges: list[EdgeOut]
    incoming_edges: list[EdgeOut]
    neighbors: list[NodeOut]


class SubgraphOut(BaseModel):
    """Subgrafo alcanzable desde un nodo hasta cierta profundidad (§7/§18)."""

    analysis_id: str
    root_node_id: str
    depth: int
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    node_count: int
    edge_count: int


class AnalysisSummaryOut(BaseModel):
    job: JobOut
    finding_count: int
    findings_by_severity: dict[str, int]
    findings_by_category: dict[str, int]
    node_count: int
    edge_count: int
    dependency_count: int
    languages: list[str]
    files_analyzed: int
    # §18: progreso separado de la compatibilidad real. Aquí se documenta la
    # fórmula de progreso del análisis estático.
    progress_formula: str


class PaginatedFindings(BaseModel):
    items: list[FindingOut]
    total: int
    limit: int
    offset: int


# --------------------------------------------------------------------------- #
# Change management (§15)
# --------------------------------------------------------------------------- #
class FileEditIn(BaseModel):
    """Edición propuesta por un agente o usuario.

    ``new_content`` a ``None`` representa la eliminación del archivo (§15).
    """

    path: str = Field(min_length=1, max_length=1024)
    new_content: str | None = None


class ChangeSetCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    produced_by_rule: str = Field(min_length=1, max_length=500)
    edits: list[FileEditIn] = Field(min_length=1)


class ChangeApprovalIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = Field(default=None, max_length=2000)


class ChangeFileOut(BaseModel):
    id: str
    path: str
    change_type: ChangeType
    base_sha256: str | None
    new_sha256: str | None
    applied_sha256: str | None
    unified_diff: str | None
    created_at: str


class ChangeApprovalOut(BaseModel):
    id: str
    change_set_id: str
    user_id: str
    decision: str
    comment: str | None
    created_at: str


class ChangeSetOut(BaseModel):
    """Registro completo exigido por §15."""

    id: str
    analysis_id: str
    project_id: str
    status: ChangeStatus
    workspace_path: str
    base_artifact_sha256: str | None
    reason: str
    produced_by_rule: str
    reversible: bool
    external_effects: str | None
    validation_result: dict[str, Any] | None
    associated_tests: list[str]
    created_by: str
    created_at: str
    updated_at: str
    approved_by: str | None
    approved_at: str | None
    applied_at: str | None
    validated_at: str | None
    rolled_back_at: str | None


class ChangeSetDetailOut(ChangeSetOut):
    files: list[ChangeFileOut]
    approvals: list[ChangeApprovalOut]


# --------------------------------------------------------------------------- #
# Generación asistida por IA (§10)
# --------------------------------------------------------------------------- #
class GenerationCreate(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)
    target_path: str | None = Field(default=None, max_length=1024)
    mode: str = Field(default="feature", pattern="^(feature|repair)$")
    ai_consent: bool = False


class GenerationFileVerification(BaseModel):
    path: str
    language: str
    change_type: str | None = None
    syntax_checked: bool
    syntax_ok: bool | None = None
    additions: int
    deletions: int
    note: str | None = None


class ValidationRequirementOut(BaseModel):
    id: str
    title: str
    description: str
    source_document: str | None = None
    source_section: str | None = None
    source_page: int | None = None
    acceptance_criteria: list[str]
    checks: list[dict[str, Any]]
    dependencies: list[str]
    related_files: list[str]
    updated_at: str


class ValidationEvidenceOut(BaseModel):
    id: str
    requirement_id: str
    check_id: str
    check_type: str
    criterion: str | None = None
    target: str | None = None
    status: str
    passed: bool
    exit_code: int | None = None
    duration_ms: int | None = None
    command: str | None = None
    output: str | None = None
    limitations: list[str]


class ValidationResultOut(BaseModel):
    id: str
    requirement_id: str
    status: str
    checks_total: int
    checks_passed: int
    checks_failed: int
    checks_skipped: int
    criteria_met: list[dict[str, Any]]
    limitations: list[str]
    created_at: str
    evidence: list[ValidationEvidenceOut]


class ValidationRunOut(BaseModel):
    id: str
    scope: str
    status: str
    code_hash: str | None = None
    environment: str | None = None
    summary: dict[str, Any] | None = None
    requested_by: str | None = None
    started_at: str
    finished_at: str | None = None
    duration_ms: int | None = None
    limitations: list[str]
    results: list[ValidationResultOut]


class ValidationRunRequest(BaseModel):
    requirement_ids: list[str] | None = None


class ValidationRunSummaryOut(BaseModel):
    id: str
    scope: str
    status: str
    code_hash: str | None = None
    started_at: str
    finished_at: str | None = None
    duration_ms: int | None = None
    summary: dict[str, Any] | None = None


class ConformanceItemOut(BaseModel):
    id: str
    title: str
    source_section: str | None = None
    status: str
    checks_total: int
    checks_passed: int
    checks_failed: int
    checks_skipped: int
    validated_at: str | None = None
    run_id: str | None = None


class ConformanceReportOut(BaseModel):
    total: int
    verified: int
    failed: int
    partial: int
    blocked: int
    not_run: int
    conformance_ratio: float
    items: list[ConformanceItemOut]


class GenerationOut(BaseModel):
    """Resultado de una generación: conjunto de cambios propuesto + verificación."""

    change_set: ChangeSetDetailOut
    verification: list[GenerationFileVerification]
    summary: str | None = None
    notes: str | None = None
    model: str
    mode: str
    usage: dict[str, Any] | None = None
    latency_ms: float
    limitations: list[str]


# --------------------------------------------------------------------------- #
# Migration (§11/§12)
# --------------------------------------------------------------------------- #
class MigrationCreate(BaseModel):
    analysis_id: str = Field(min_length=1)


class NimStatusOut(BaseModel):
    """Estado de la integración con NVIDIA NIM (único proveedor de IA)."""

    provider: str
    configured: bool
    base_url: str
    model: str
    reachable: bool
    model_available: bool
    models_count: int
    sample_models: list[str]
    completion_ok: bool
    latency_ms: float | None = None
    usage: dict | None = None
    error: str | None = None


class MigrationChangeOut(BaseModel):
    id: str
    change_ref: str
    kind: str
    path: str | None
    action: str
    description: str
    diff: str | None
    reversible: bool
    rule_id: str | None


class MigrationPlanOut(BaseModel):
    id: str
    project_id: str
    analysis_id: str
    source_provider: str
    target_provider: str
    status: str
    target_base_url: str | None
    target_model: str | None
    operation_count: int
    matrix_summary: dict[str, int] | None
    verified_at: str | None
    created_by: str
    created_at: str


class MigrationPlanDetailOut(MigrationPlanOut):
    """Plan completo: operaciones, matriz, cambios, pruebas y limitaciones (§12.3)."""

    plan: dict[str, Any] | None
    limitations: list[str] | None
    sources: list[dict[str, Any]] | None
    changes: list[MigrationChangeOut]


class QuotaItem(BaseModel):
    used: int
    limit: int
    percent: float | None


class UsageOut(BaseModel):
    organization_id: str
    projects: int
    artifacts: int
    storage_bytes: int
    findings: int
    active_jobs: int
    jobs_by_status: dict[str, int]
    usage_totals: dict[str, int]
    quotas: dict[str, QuotaItem]


class MetricsOut(BaseModel):
    organization_id: str
    generated_at: str
    jobs_total: int
    jobs_by_status: dict[str, int]
    jobs_finished: int
    jobs_failed_or_cancelled: int
    avg_duration_seconds: float | None
    durations_observed: int


class BinaryAnalysisOut(BaseModel):
    """Resultado del análisis estático de un binario (§6.2)."""

    id: str
    artifact_id: str
    project_id: str
    organization_id: str
    format: str
    architecture: str | None
    bits: int | None
    file_type: str | None
    size_bytes: int
    sha256: str
    created_by: str
    created_at: str
    facts: dict[str, Any]


class BinaryCompareOut(BaseModel):
    same_format: bool
    same_architecture: bool
    same_digest: bool
    size_delta: int
    added_exports: list[str]
    removed_exports: list[str]
    added_libraries: list[str]
    removed_libraries: list[str]


class BinaryAnalyzeRequest(BaseModel):
    artifact_id: str = Field(min_length=1)


class BinaryCompareRequest(BaseModel):
    left_id: str = Field(min_length=1)
    right_id: str = Field(min_length=1)
