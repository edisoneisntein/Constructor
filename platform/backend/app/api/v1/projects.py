"""Proyectos, artifacts, análisis, hallazgos, grafo y exportación (§17, §20)."""

from __future__ import annotations

from fastapi import APIRouter, File, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import ActiveOrganization, Connection, CurrentUser, require_role
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, PayloadTooLargeError
from app.db import repositories as repo
from app.schemas.models import (
    AnalysisCreate,
    AnalysisSummaryOut,
    ArchitectureGraphOut,
    ArtifactOut,
    DependencyOut,
    EdgeOut,
    FindingOut,
    JobOut,
    NodeDetailOut,
    NodeOut,
    PaginatedFindings,
    ProjectCreate,
    ProjectOut,
    Role,
    SubgraphOut,
)
from app.services import analysis_service
from app.services.job_runner import get_job_runner

router = APIRouter(tags=["projects"])


def _require_project(conn, project_id: str, organization_id: str) -> dict:
    project = repo.get_project(conn, project_id, organization_id)
    if project is None:
        raise NotFoundError("Proyecto no encontrado.")
    return project


async def _read_upload_capped(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                "El archivo supera el límite de carga.",
                details={"max": max_bytes},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _project_out(project: dict) -> ProjectOut:
    return ProjectOut(
        id=project["id"],
        organization_id=project["organization_id"],
        name=project["name"],
        created_by=project["created_by"],
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


def _job_out(job: dict) -> JobOut:
    return JobOut(**analysis_service.job_public(job))


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ProjectOut:
    require_role(organization, Role.developer)
    project = analysis_service.create_project(
        conn, organization_id=organization["id"], user_id=user["id"], name=payload.name
    )
    return _project_out(project)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(organization: ActiveOrganization, conn: Connection) -> list[ProjectOut]:
    return [_project_out(project) for project in repo.list_projects(conn, organization["id"])]


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project_detail(project_id: str, organization: ActiveOrganization, conn: Connection) -> ProjectOut:
    return _project_out(_require_project(conn, project_id, organization["id"]))


@router.delete("/projects/{project_id}", response_model=ProjectOut)
def delete_project(
    project_id: str,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ProjectOut:
    """Elimina un proyecto y sus datos asociados (§14.6)."""
    require_role(organization, Role.developer)
    project = _require_project(conn, project_id, organization["id"])
    deleted = analysis_service.delete_project(
        conn, project=project, user_id=user["id"], settings=get_settings()
    )
    return _project_out(deleted)


@router.post("/projects/{project_id}/artifacts", response_model=ArtifactOut, status_code=201)
async def upload_artifact(
    project_id: str,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
    file: UploadFile = File(...),
) -> ArtifactOut:
    require_role(organization, Role.developer)
    project = _require_project(conn, project_id, organization["id"])
    settings: Settings = get_settings()
    data = await _read_upload_capped(file, settings.max_upload_bytes)
    artifact = analysis_service.ingest_source_zip(
        conn,
        settings=settings,
        project=project,
        user_id=user["id"],
        filename=file.filename or "project.zip",
        declared_mime=file.content_type,
        data=data,
    )
    return ArtifactOut(
        id=artifact["id"],
        project_id=artifact["project_id"],
        kind=artifact["kind"],
        filename=artifact["filename"],
        size_bytes=artifact["size_bytes"],
        sha256=artifact["sha256"],
        detected_mime=artifact["detected_mime"],
        declared_mime=artifact["declared_mime"],
        validation_state=artifact["validation_state"],
        retention_policy=artifact["retention_policy"],
        created_at=artifact["created_at"],
    )


@router.get("/projects/{project_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(project_id: str, organization: ActiveOrganization, conn: Connection) -> list[ArtifactOut]:
    _require_project(conn, project_id, organization["id"])
    artifacts = repo.list_artifacts(conn, project_id, organization["id"])
    return [
        ArtifactOut(
            id=artifact["id"],
            project_id=artifact["project_id"],
            kind=artifact["kind"],
            filename=artifact["filename"],
            size_bytes=artifact["size_bytes"],
            sha256=artifact["sha256"],
            detected_mime=artifact["detected_mime"],
            declared_mime=artifact["declared_mime"],
            validation_state=artifact["validation_state"],
            retention_policy=artifact["retention_policy"],
            created_at=artifact["created_at"],
        )
        for artifact in artifacts
    ]


@router.delete("/projects/{project_id}/artifacts/{artifact_id}", response_model=ArtifactOut)
def delete_artifact(
    project_id: str,
    artifact_id: str,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> ArtifactOut:
    """Elimina un artefacto explícitamente (§14.6)."""
    require_role(organization, Role.developer)
    _require_project(conn, project_id, organization["id"])
    artifact = analysis_service.delete_artifact(
        conn, artifact_id=artifact_id, organization_id=organization["id"], user_id=user["id"]
    )
    return ArtifactOut(
        id=artifact["id"],
        project_id=artifact["project_id"],
        kind=artifact["kind"],
        filename=artifact["filename"],
        size_bytes=artifact["size_bytes"],
        sha256=artifact["sha256"],
        detected_mime=artifact["detected_mime"],
        declared_mime=artifact["declared_mime"],
        validation_state=artifact["validation_state"],
        retention_policy=artifact["retention_policy"],
        created_at=artifact["created_at"],
    )


@router.post("/projects/{project_id}/analyses", response_model=JobOut, status_code=202)
def start_analysis(
    project_id: str,
    payload: AnalysisCreate,
    user: CurrentUser,
    organization: ActiveOrganization,
    conn: Connection,
) -> JobOut:
    require_role(organization, Role.developer)
    project = _require_project(conn, project_id, organization["id"])
    job = analysis_service.start_analysis(
        conn,
        project=project,
        user_id=user["id"],
        artifact_id=payload.artifact_id,
        deep_analysis=payload.deep_analysis,
    )
    return _job_out(job)


@router.get("/projects/{project_id}/analyses", response_model=list[JobOut])
def list_analyses(project_id: str, organization: ActiveOrganization, conn: Connection) -> list[JobOut]:
    _require_project(conn, project_id, organization["id"])
    return [_job_out(job) for job in repo.list_jobs(conn, project_id, organization["id"])]


def _require_analysis(conn, analysis_id: str, organization_id: str) -> dict:
    job = repo.get_job(conn, analysis_id, organization_id)
    if job is None:
        raise NotFoundError("Análisis no encontrado.")
    return job


@router.get("/analyses/{analysis_id}", response_model=AnalysisSummaryOut)
def get_analysis(analysis_id: str, organization: ActiveOrganization, conn: Connection) -> AnalysisSummaryOut:
    return AnalysisSummaryOut(**analysis_service.build_analysis_summary(conn, analysis_id=analysis_id, organization_id=organization["id"]))


@router.get("/analyses/{analysis_id}/findings", response_model=PaginatedFindings)
def get_findings(
    analysis_id: str,
    organization: ActiveOrganization,
    conn: Connection,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> PaginatedFindings:
    _require_analysis(conn, analysis_id, organization["id"])
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    findings, total = repo.list_findings(
        conn,
        analysis_id=analysis_id,
        organization_id=organization["id"],
        category=category,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return PaginatedFindings(
        items=[FindingOut(**{**_finding_public(f)}) for f in findings],
        total=total,
        limit=limit,
        offset=offset,
    )


def _finding_public(finding: dict) -> dict:
    payload = dict(finding)
    payload.pop("organization_id", None)
    return payload


_NODE_FIELDS = set(NodeOut.model_fields)
_EDGE_FIELDS = set(EdgeOut.model_fields)
_DEP_FIELDS = set(DependencyOut.model_fields)


def _node_out(node: dict) -> NodeOut:
    return NodeOut(**{k: v for k, v in node.items() if k in _NODE_FIELDS})


def _edge_out(edge: dict) -> EdgeOut:
    return EdgeOut(**{k: v for k, v in edge.items() if k in _EDGE_FIELDS})


@router.get("/analyses/{analysis_id}/architecture", response_model=ArchitectureGraphOut)
def get_architecture(
    analysis_id: str,
    organization: ActiveOrganization,
    conn: Connection,
    node_type: str | None = None,
    edge_type: str | None = None,
) -> ArchitectureGraphOut:
    _require_analysis(conn, analysis_id, organization["id"])
    nodes = repo.list_nodes_filtered(conn, analysis_id, organization["id"], node_type=node_type)
    edges = repo.list_edges_filtered(conn, analysis_id, organization["id"], edge_type=edge_type)
    deps = repo.list_dependencies(conn, analysis_id, organization["id"])
    evidence_counts = repo.count_edges_by_evidence(conn, analysis_id, organization["id"])
    return ArchitectureGraphOut(
        analysis_id=analysis_id,
        nodes=[_node_out(node) for node in nodes],
        edges=[_edge_out(edge) for edge in edges],
        dependencies=[DependencyOut(**{k: v for k, v in dep.items() if k in _DEP_FIELDS}) for dep in deps],
        node_count=len(nodes),
        edge_count=len(edges),
        dependency_count=len(deps),
        confirmed_edge_count=evidence_counts.get("DIRECT_EVIDENCE", 0),
        inferred_edge_count=evidence_counts.get("STATIC_INFERENCE", 0),
        node_type_counts=repo.count_nodes_by_type(conn, analysis_id, organization["id"]),
        edge_type_counts=repo.count_edges_by_type(conn, analysis_id, organization["id"]),
    )


@router.get("/analyses/{analysis_id}/architecture/subgraph", response_model=SubgraphOut)
def get_subgraph(
    analysis_id: str,
    node_id: str,
    organization: ActiveOrganization,
    conn: Connection,
    depth: int = 1,
) -> SubgraphOut:
    _require_analysis(conn, analysis_id, organization["id"])
    depth = max(1, min(depth, 4))
    nodes = repo.list_nodes(conn, analysis_id, organization["id"])
    index = {node["id"]: node for node in nodes}
    if node_id not in index:
        raise NotFoundError("Nodo raíz no encontrado.")
    edges = repo.list_edges(conn, analysis_id, organization["id"])
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        source = edge["source_node_id"]
        target = edge["target_node_id"]
        adjacency.setdefault(source, set())
        if target:
            adjacency[source].add(target)
            adjacency.setdefault(target, set()).add(source)

    visited: set[str] = {node_id}
    frontier: set[str] = {node_id}
    for _ in range(depth):
        nxt: set[str] = set()
        for current in frontier:
            for neighbor in adjacency.get(current, ()):
                if neighbor not in visited:
                    nxt.add(neighbor)
        if not nxt:
            break
        visited |= nxt
        frontier = nxt

    sub_edges = [
        edge
        for edge in edges
        if edge["source_node_id"] in visited and (edge["target_node_id"] in visited)
    ]
    sub_nodes = [index[node] for node in visited if node in index]
    return SubgraphOut(
        analysis_id=analysis_id,
        root_node_id=node_id,
        depth=depth,
        nodes=[_node_out(node) for node in sub_nodes],
        edges=[_edge_out(edge) for edge in sub_edges],
        node_count=len(sub_nodes),
        edge_count=len(sub_edges),
    )


@router.get("/analyses/{analysis_id}/architecture/node", response_model=NodeDetailOut)
def get_node_detail(
    analysis_id: str, node_id: str, organization: ActiveOrganization, conn: Connection
) -> NodeDetailOut:
    _require_analysis(conn, analysis_id, organization["id"])
    node = repo.get_node(conn, analysis_id, node_id, organization["id"])
    if node is None:
        raise NotFoundError("Nodo no encontrado.")
    nodes = repo.list_nodes(conn, analysis_id, organization["id"])
    index = {item["id"]: item for item in nodes}
    edges = repo.list_edges(conn, analysis_id, organization["id"])
    outgoing = [edge for edge in edges if edge["source_node_id"] == node_id]
    incoming = [edge for edge in edges if edge["target_node_id"] == node_id]
    neighbor_ids: set[str] = set()
    for edge in outgoing:
        if edge["target_node_id"]:
            neighbor_ids.add(edge["target_node_id"])
    for edge in incoming:
        neighbor_ids.add(edge["source_node_id"])
    return NodeDetailOut(
        node=_node_out(node),
        outgoing_edges=[_edge_out(edge) for edge in outgoing],
        incoming_edges=[_edge_out(edge) for edge in incoming],
        neighbors=[_node_out(index[nid]) for nid in neighbor_ids if nid in index],
    )


@router.post("/analyses/{analysis_id}/cancel", response_model=JobOut)
def cancel_analysis(analysis_id: str, organization: ActiveOrganization, conn: Connection) -> JobOut:
    job = _require_analysis(conn, analysis_id, organization["id"])
    updated = analysis_service.cancel_analysis(conn, job=job, organization_id=organization["id"])
    return _job_out(updated)


@router.post("/analyses/{analysis_id}/export")
def export_analysis(
    analysis_id: str,
    organization: ActiveOrganization,
    conn: Connection,
    fmt: str = "json",
) -> Response:
    _require_analysis(conn, analysis_id, organization["id"])
    media_type, content = analysis_service.export_report(
        conn, analysis_id=analysis_id, organization_id=organization["id"], fmt=fmt
    )
    filename = f"report-{analysis_id}.{'json' if fmt == 'json' else 'md'}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
