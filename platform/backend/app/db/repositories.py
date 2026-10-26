"""Capa de repositorio sobre SQLite.

Toda lectura/escritura es parametrizada. Las funciones que devuelven datos de un
proyecto exigen ``organization_id`` para impedir IDOR (§16).
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from typing import Any

from app.core.ids import new_id


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _iso_before(now_iso: str, seconds: int) -> str:
    from datetime import datetime, timedelta

    return (datetime.fromisoformat(now_iso) - timedelta(seconds=seconds)).isoformat()


def _load_json(value: str | None) -> Any:
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = "".join(c if c.isalnum() else "-" for c in normalized.lower())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or "org"


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
def create_user(
    conn: sqlite3.Connection,
    *,
    email: str,
    display_name: str,
    password_hash: str,
    created_at: str,
) -> dict[str, Any]:
    user_id = new_id("usr")
    conn.execute(
        "INSERT INTO users(id, email, display_name, password_hash, created_at) VALUES (?,?,?,?,?)",
        (user_id, email.lower(), display_name, password_hash, created_at),
    )
    return {"id": user_id, "email": email.lower(), "display_name": display_name, "created_at": created_at}


def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict[str, Any] | None:
    return _row(conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone())


def get_user_by_id(conn: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
    return _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


# --------------------------------------------------------------------------- #
# Organizations & memberships
# --------------------------------------------------------------------------- #
def create_organization(conn: sqlite3.Connection, *, name: str, created_at: str) -> dict[str, Any]:
    org_id = new_id("org")
    base = slugify(name)
    slug = base
    suffix = 2
    while conn.execute("SELECT 1 FROM organizations WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    conn.execute(
        "INSERT INTO organizations(id, name, slug, created_at) VALUES (?,?,?,?)",
        (org_id, name, slug, created_at),
    )
    return {"id": org_id, "name": name, "slug": slug, "created_at": created_at}


def add_membership(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    user_id: str,
    role: str,
    created_at: str,
) -> dict[str, Any]:
    membership_id = new_id("mem")
    conn.execute(
        "INSERT INTO organization_memberships(id, organization_id, user_id, role, created_at)"
        " VALUES (?,?,?,?,?)",
        (membership_id, organization_id, user_id, role, created_at),
    )
    return {
        "id": membership_id,
        "organization_id": organization_id,
        "user_id": user_id,
        "role": role,
        "created_at": created_at,
    }


def get_membership(
    conn: sqlite3.Connection, *, organization_id: str, user_id: str
) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            "SELECT * FROM organization_memberships WHERE organization_id = ? AND user_id = ?",
            (organization_id, user_id),
        ).fetchone()
    )


def list_organizations_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT o.id, o.name, o.slug, o.created_at, m.role
        FROM organizations o
        JOIN organization_memberships m ON m.organization_id = o.id
        WHERE m.user_id = ?
        ORDER BY o.created_at ASC
        """,
        (user_id,),
    ).fetchall()
    return _rows(rows)


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
def create_session(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    token_hash: str,
    created_at: str,
    expires_at: str,
) -> dict[str, Any]:
    session_id = new_id("ses")
    conn.execute(
        "INSERT INTO sessions(id, user_id, token_hash, created_at, expires_at, revoked_at)"
        " VALUES (?,?,?,?,?,NULL)",
        (session_id, user_id, token_hash, created_at, expires_at),
    )
    return {"id": session_id, "user_id": user_id, "expires_at": expires_at}


def get_session_by_hash(conn: sqlite3.Connection, token_hash: str) -> dict[str, Any] | None:
    return _row(
        conn.execute("SELECT * FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
    )


def revoke_session(conn: sqlite3.Connection, *, session_id: str, revoked_at: str) -> None:
    conn.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (revoked_at, session_id))


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
def create_project(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    name: str,
    created_by: str,
    created_at: str,
) -> dict[str, Any]:
    project_id = new_id("prj")
    conn.execute(
        "INSERT INTO projects(id, organization_id, name, created_by, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, organization_id, name, created_by, created_at, created_at),
    )
    return get_project(conn, project_id, organization_id)  # type: ignore[return-value]


def list_projects(conn: sqlite3.Connection, organization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM projects WHERE organization_id = ? ORDER BY created_at DESC",
        (organization_id,),
    ).fetchall()
    return _rows(rows)


def get_project(
    conn: sqlite3.Connection, project_id: str, organization_id: str
) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            "SELECT * FROM projects WHERE id = ? AND organization_id = ?",
            (project_id, organization_id),
        ).fetchone()
    )


def count_active_jobs_for_project(
    conn: sqlite3.Connection, project_id: str, organization_id: str
) -> int:
    placeholders = ",".join("?" for _ in ACTIVE_JOB_STATUSES)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM analysis_jobs WHERE project_id = ? AND organization_id = ?"
        f" AND status IN ({placeholders})",
        (project_id, organization_id, *ACTIVE_JOB_STATUSES),
    ).fetchone()
    return int(row["n"]) if row else 0


def list_project_artifacts_all(
    conn: sqlite3.Connection, project_id: str, organization_id: str
) -> list[dict[str, Any]]:
    """Artefactos del proyecto en cualquier estado (para limpiar bytes al borrar)."""
    rows = conn.execute(
        "SELECT * FROM artifacts WHERE project_id = ? AND organization_id = ?",
        (project_id, organization_id),
    ).fetchall()
    return _rows(rows)


def list_project_change_sets(
    conn: sqlite3.Connection, project_id: str, organization_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM change_sets WHERE project_id = ? AND organization_id = ?",
        (project_id, organization_id),
    ).fetchall()
    return _rows(rows)


def delete_project(conn: sqlite3.Connection, project_id: str, organization_id: str) -> bool:
    """Elimina el proyecto y sus dependencias sin clave foránea.

    Las tablas con ``REFERENCES projects(id) ON DELETE CASCADE`` (artefactos,
    análisis, hallazgos, grafo, cambios y binarios) se limpian por cascada. Los
    planes de migración no declaran FK, por lo que se eliminan explícitamente
    antes del proyecto. El uso histórico de la organización se conserva.
    """

    conn.execute(
        "DELETE FROM migration_changes WHERE plan_id IN"
        " (SELECT id FROM migration_plans WHERE project_id = ? AND organization_id = ?)",
        (project_id, organization_id),
    )
    conn.execute(
        "DELETE FROM migration_plans WHERE project_id = ? AND organization_id = ?",
        (project_id, organization_id),
    )
    cursor = conn.execute(
        "DELETE FROM projects WHERE id = ? AND organization_id = ?",
        (project_id, organization_id),
    )
    return cursor.rowcount > 0


# --------------------------------------------------------------------------- #
# Observabilidad y uso por organización (§14/§19.6)
# --------------------------------------------------------------------------- #
def count_projects(conn: sqlite3.Connection, organization_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM projects WHERE organization_id = ?", (organization_id,)
    ).fetchone()
    return int(row["n"]) if row else 0


def storage_bytes_used(conn: sqlite3.Connection, organization_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(size_bytes), 0) AS total FROM artifacts"
        " WHERE organization_id = ? AND deleted_at IS NULL",
        (organization_id,),
    ).fetchone()
    return int(row["total"]) if row else 0


def count_artifacts(conn: sqlite3.Connection, organization_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM artifacts WHERE organization_id = ? AND deleted_at IS NULL",
        (organization_id,),
    ).fetchone()
    return int(row["n"]) if row else 0


def count_jobs_by_status(conn: sqlite3.Connection, organization_id: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM analysis_jobs WHERE organization_id = ? GROUP BY status",
        (organization_id,),
    ).fetchall()
    return {row["status"]: int(row["n"]) for row in rows}


def list_org_jobs(conn: sqlite3.Connection, organization_id: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM analysis_jobs WHERE organization_id = ? ORDER BY created_at DESC LIMIT ?",
        (organization_id, limit),
    ).fetchall()
    return _rows(rows)


ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING", "ANALYZING", "GRAPH_BUILDING")


def count_active_jobs(conn: sqlite3.Connection, organization_id: str) -> int:
    placeholders = ",".join("?" for _ in ACTIVE_JOB_STATUSES)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM analysis_jobs WHERE organization_id = ? AND status IN ({placeholders})",
        (organization_id, *ACTIVE_JOB_STATUSES),
    ).fetchone()
    return int(row["n"]) if row else 0


def count_findings_for_org(conn: sqlite3.Connection, organization_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM analysis_findings WHERE organization_id = ?", (organization_id,)
    ).fetchone()
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------- #
# Artifacts
# --------------------------------------------------------------------------- #
def create_artifact(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    organization_id: str,
    kind: str,
    filename: str,
    size_bytes: int,
    sha256: str,
    detected_mime: str,
    declared_mime: str | None,
    storage_path: str,
    retention_policy: str,
    validation_state: str,
    created_at: str,
) -> dict[str, Any]:
    artifact_id = new_id("art")
    conn.execute(
        """
        INSERT INTO artifacts(id, project_id, organization_id, kind, filename, size_bytes,
            sha256, detected_mime, declared_mime, storage_path, retention_policy,
            validation_state, created_at, deleted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
        """,
        (
            artifact_id,
            project_id,
            organization_id,
            kind,
            filename,
            size_bytes,
            sha256,
            detected_mime,
            declared_mime,
            storage_path,
            retention_policy,
            validation_state,
            created_at,
        ),
    )
    return get_artifact(conn, artifact_id, organization_id)  # type: ignore[return-value]


def get_artifact(
    conn: sqlite3.Connection, artifact_id: str, organization_id: str
) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            "SELECT * FROM artifacts WHERE id = ? AND organization_id = ?",
            (artifact_id, organization_id),
        ).fetchone()
    )


def list_artifacts(conn: sqlite3.Connection, project_id: str, organization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM artifacts WHERE project_id = ? AND organization_id = ? AND deleted_at IS NULL"
        " ORDER BY created_at DESC",
        (project_id, organization_id),
    ).fetchall()
    return _rows(rows)


def mark_artifact_deleted(
    conn: sqlite3.Connection, artifact_id: str, organization_id: str, deleted_at: str
) -> None:
    conn.execute(
        "UPDATE artifacts SET deleted_at = ?, validation_state = 'REJECTED'"
        " WHERE id = ? AND organization_id = ?",
        (deleted_at, artifact_id, organization_id),
    )


def list_retained_artifacts(conn: sqlite3.Connection, organization_id: str | None = None) -> list[dict[str, Any]]:
    if organization_id is None:
        rows = conn.execute("SELECT * FROM artifacts WHERE deleted_at IS NULL").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM artifacts WHERE organization_id = ? AND deleted_at IS NULL",
            (organization_id,),
        ).fetchall()
    return _rows(rows)


# --------------------------------------------------------------------------- #
# Analysis jobs
# --------------------------------------------------------------------------- #
def create_job(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    organization_id: str,
    artifact_id: str,
    created_by: str,
    status: str,
    created_at: str,
) -> dict[str, Any]:
    job_id = new_id("anl")
    conn.execute(
        """
        INSERT INTO analysis_jobs(id, project_id, organization_id, artifact_id, status, phase,
            progress_completed, progress_total, cancel_requested, created_by, created_at)
        VALUES (?,?,?,?,?,?,0,0,0,?,?)
        """,
        (job_id, project_id, organization_id, artifact_id, status, status, created_by, created_at),
    )
    return get_job(conn, job_id, organization_id)  # type: ignore[return-value]


def get_job(conn: sqlite3.Connection, job_id: str, organization_id: str) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            "SELECT * FROM analysis_jobs WHERE id = ? AND organization_id = ?",
            (job_id, organization_id),
        ).fetchone()
    )


def list_jobs(conn: sqlite3.Connection, project_id: str, organization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM analysis_jobs WHERE project_id = ? AND organization_id = ? ORDER BY created_at DESC",
        (project_id, organization_id),
    ).fetchall()
    return _rows(rows)


def update_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    progress_completed: int | None = None,
    progress_total: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    result_summary: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    for column, value in (
        ("status", status),
        ("phase", phase),
        ("progress_completed", progress_completed),
        ("progress_total", progress_total),
        ("error_code", error_code),
        ("error_message", error_message),
        ("result_summary", result_summary),
        ("started_at", started_at),
        ("finished_at", finished_at),
    ):
        if value is not None:
            fields.append(f"{column} = ?")
            values.append(value)
    if not fields:
        return
    values.append(job_id)
    conn.execute(f"UPDATE analysis_jobs SET {', '.join(fields)} WHERE id = ?", values)


def request_cancel(conn: sqlite3.Connection, job_id: str, organization_id: str) -> bool:
    cursor = conn.execute(
        "UPDATE analysis_jobs SET cancel_requested = 1 WHERE id = ? AND organization_id = ?",
        (job_id, organization_id),
    )
    return cursor.rowcount > 0


def is_cancel_requested(conn: sqlite3.Connection, job_id: str) -> bool:
    row = conn.execute(
        "SELECT cancel_requested FROM analysis_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    return bool(row and int(row["cancel_requested"]) == 1)


def claim_next_job(conn: sqlite3.Connection, *, worker_id: str, now: str) -> dict[str, Any] | None:
    """Reclama atómicamente el trabajo QUEUED más antiguo (§4.3, cola externa).

    Usa ``UPDATE ... RETURNING`` sobre una subconsulta, por lo que el reclamo es
    atómico incluso con varios procesos trabajadores sobre la misma base de
    datos: una sola sentencia elige y marca el trabajo.
    """

    row = conn.execute(
        """
        UPDATE analysis_jobs
        SET status = 'RUNNING', phase = 'claimed', claimed_by = ?, claimed_at = ?,
            attempt_count = attempt_count + 1, started_at = COALESCE(started_at, ?)
        WHERE id = (
            SELECT id FROM analysis_jobs WHERE status = 'QUEUED' ORDER BY created_at LIMIT 1
        )
        RETURNING *
        """,
        (worker_id, now, now),
    ).fetchone()
    return _row(row)


def heartbeat_job(conn: sqlite3.Connection, job_id: str, *, worker_id: str, now: str) -> None:
    conn.execute(
        "UPDATE analysis_jobs SET claimed_at = ? WHERE id = ? AND claimed_by = ?",
        (now, job_id, worker_id),
    )


def recover_stale_jobs(
    conn: sqlite3.Connection, *, now: str, stale_seconds: int, max_attempts: int
) -> dict[str, int]:
    """Reencola trabajos RUNNING sin latido (worker caído) o los marca fallidos.

    Devuelve cuántos se reencolaron y cuántos se agotaron por intentos.
    """

    cutoff = _iso_before(now, stale_seconds)
    requeued = conn.execute(
        """
        UPDATE analysis_jobs
        SET status = 'QUEUED', phase = 'requeued', claimed_by = NULL, claimed_at = NULL
        WHERE status = 'RUNNING' AND claimed_at IS NOT NULL AND claimed_at < ?
          AND attempt_count < ?
        """,
        (cutoff, max_attempts),
    ).rowcount
    exhausted = conn.execute(
        """
        UPDATE analysis_jobs
        SET status = 'FAILED', phase = 'failed', error_code = 'worker_lost',
            error_message = 'El trabajador se perdió y se agotaron los intentos.',
            finished_at = ?
        WHERE status = 'RUNNING' AND claimed_at IS NOT NULL AND claimed_at < ?
          AND attempt_count >= ?
        """,
        (now, cutoff, max_attempts),
    ).rowcount
    return {"requeued": int(requeued), "failed": int(exhausted)}


def is_cancel_requested(conn: sqlite3.Connection, job_id: str) -> bool:
    row = conn.execute("SELECT cancel_requested FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
    return bool(row and row["cancel_requested"])


# --------------------------------------------------------------------------- #
# Findings / graph / dependencies
# --------------------------------------------------------------------------- #
def insert_findings(conn: sqlite3.Connection, findings: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO analysis_findings(id, analysis_id, project_id, organization_id, category,
            severity, language, file_path, line_start, line_end, symbol, evidence_level,
            detection_method, tool, tool_version, snippet, message, metadata, created_at)
        VALUES (:id,:analysis_id,:project_id,:organization_id,:category,:severity,:language,
            :file_path,:line_start,:line_end,:symbol,:evidence_level,:detection_method,:tool,
            :tool_version,:snippet,:message,:metadata,:created_at)
        """,
        findings,
    )


def list_findings(
    conn: sqlite3.Connection,
    *,
    analysis_id: str,
    organization_id: str,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["analysis_id = ?", "organization_id = ?"]
    params: list[Any] = [analysis_id, organization_id]
    if category:
        clauses.append("category = ?")
        params.append(category)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    where = " AND ".join(clauses)
    total_row = conn.execute(f"SELECT COUNT(*) AS c FROM analysis_findings WHERE {where}", params).fetchone()
    total = int(total_row["c"]) if total_row else 0
    rows = conn.execute(
        f"SELECT * FROM analysis_findings WHERE {where} ORDER BY severity DESC, file_path ASC, line_start ASC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    findings = _rows(rows)
    for finding in findings:
        finding["metadata"] = _load_json(finding.get("metadata"))
    return findings, total


def count_findings_by(
    conn: sqlite3.Connection, *, analysis_id: str, organization_id: str, column: str
) -> dict[str, int]:
    if column not in {"severity", "category", "language"}:
        raise ValueError("columna no permitida")
    rows = conn.execute(
        f"SELECT {column} AS k, COUNT(*) AS c FROM analysis_findings"
        " WHERE analysis_id = ? AND organization_id = ? GROUP BY {column}".replace("{column}", column),
        (analysis_id, organization_id),
    ).fetchall()
    return {str(row["k"]): int(row["c"]) for row in rows}


def insert_nodes(conn: sqlite3.Connection, nodes: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO architecture_nodes(id, analysis_id, project_id, organization_id, node_type,
            label, path, language, evidence_level, detection_method, metadata, created_at)
        VALUES (:id,:analysis_id,:project_id,:organization_id,:node_type,:label,:path,:language,
            :evidence_level,:detection_method,:metadata,:created_at)
        """,
        nodes,
    )


def insert_edges(conn: sqlite3.Connection, edges: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO architecture_edges(id, analysis_id, project_id, organization_id, source_node_id,
            target_node_id, target_ref, edge_type, evidence_level, detection_method, metadata, created_at)
        VALUES (:id,:analysis_id,:project_id,:organization_id,:source_node_id,:target_node_id,
            :target_ref,:edge_type,:evidence_level,:detection_method,:metadata,:created_at)
        """,
        edges,
    )


def insert_dependencies(conn: sqlite3.Connection, deps: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO dependency_records(id, analysis_id, project_id, organization_id, ecosystem,
            name, version, source_file, evidence_level, created_at)
        VALUES (:id,:analysis_id,:project_id,:organization_id,:ecosystem,:name,:version,
            :source_file,:evidence_level,:created_at)
        """,
        deps,
    )


def list_nodes(conn: sqlite3.Connection, analysis_id: str, organization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM architecture_nodes WHERE analysis_id = ? AND organization_id = ? ORDER BY label",
        (analysis_id, organization_id),
    ).fetchall()
    nodes = _rows(rows)
    for node in nodes:
        node["metadata"] = _load_json(node.get("metadata"))
    return nodes


def list_edges(conn: sqlite3.Connection, analysis_id: str, organization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM architecture_edges WHERE analysis_id = ? AND organization_id = ?",
        (analysis_id, organization_id),
    ).fetchall()
    edges = _rows(rows)
    for edge in edges:
        edge["metadata"] = _load_json(edge.get("metadata"))
    return edges


def list_dependencies(conn: sqlite3.Connection, analysis_id: str, organization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM dependency_records WHERE analysis_id = ? AND organization_id = ? ORDER BY name",
        (analysis_id, organization_id),
    ).fetchall()
    return _rows(rows)


def count_edges_by_evidence(conn: sqlite3.Connection, analysis_id: str, organization_id: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT evidence_level AS k, COUNT(*) AS c FROM architecture_edges
        WHERE analysis_id = ? AND organization_id = ? GROUP BY evidence_level
        """,
        (analysis_id, organization_id),
    ).fetchall()
    return {str(row["k"]): int(row["c"]) for row in rows}


def get_node(
    conn: sqlite3.Connection, analysis_id: str, node_id: str, organization_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM architecture_nodes WHERE id = ? AND analysis_id = ? AND organization_id = ?",
        (node_id, analysis_id, organization_id),
    ).fetchone()
    node = _row(row)
    if node is not None:
        node["metadata"] = _load_json(node.get("metadata"))
    return node


def list_nodes_filtered(
    conn: sqlite3.Connection, analysis_id: str, organization_id: str, node_type: str | None = None
) -> list[dict[str, Any]]:
    clauses = ["analysis_id = ?", "organization_id = ?"]
    params: list[Any] = [analysis_id, organization_id]
    if node_type:
        clauses.append("node_type = ?")
        params.append(node_type)
    rows = conn.execute(
        f"SELECT * FROM architecture_nodes WHERE {' AND '.join(clauses)} ORDER BY label", params
    ).fetchall()
    nodes = _rows(rows)
    for node in nodes:
        node["metadata"] = _load_json(node.get("metadata"))
    return nodes


def list_edges_filtered(
    conn: sqlite3.Connection, analysis_id: str, organization_id: str, edge_type: str | None = None
) -> list[dict[str, Any]]:
    clauses = ["analysis_id = ?", "organization_id = ?"]
    params: list[Any] = [analysis_id, organization_id]
    if edge_type:
        clauses.append("edge_type = ?")
        params.append(edge_type)
    rows = conn.execute(
        f"SELECT * FROM architecture_edges WHERE {' AND '.join(clauses)}", params
    ).fetchall()
    edges = _rows(rows)
    for edge in edges:
        edge["metadata"] = _load_json(edge.get("metadata"))
    return edges


def count_nodes_by_type(conn: sqlite3.Connection, analysis_id: str, organization_id: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT node_type AS k, COUNT(*) AS c FROM architecture_nodes
        WHERE analysis_id = ? AND organization_id = ? GROUP BY node_type
        """,
        (analysis_id, organization_id),
    ).fetchall()
    return {str(row["k"]): int(row["c"]) for row in rows}


def count_edges_by_type(conn: sqlite3.Connection, analysis_id: str, organization_id: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT edge_type AS k, COUNT(*) AS c FROM architecture_edges
        WHERE analysis_id = ? AND organization_id = ? GROUP BY edge_type
        """,
        (analysis_id, organization_id),
    ).fetchall()
    return {str(row["k"]): int(row["c"]) for row in rows}


# --------------------------------------------------------------------------- #
# Change management (§15)
# --------------------------------------------------------------------------- #
def create_change_set(
    conn: sqlite3.Connection,
    *,
    change_set_id: str,
    analysis_id: str,
    project_id: str,
    organization_id: str,
    workspace_path: str,
    before_root: str,
    after_root: str,
    base_artifact_sha256: str | None,
    reason: str,
    produced_by_rule: str,
    status: str,
    reversible: bool,
    external_effects: str | None,
    associated_tests: str | None,
    created_by: str,
    created_at: str,
) -> dict[str, Any]:
    conn.execute(
        """
        INSERT INTO change_sets(id, analysis_id, project_id, organization_id, workspace_path,
            before_root, after_root, base_artifact_sha256, reason, produced_by_rule, status,
            reversible, external_effects, validation_result, associated_tests, created_by,
            created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?)
        """,
        (
            change_set_id,
            analysis_id,
            project_id,
            organization_id,
            workspace_path,
            before_root,
            after_root,
            base_artifact_sha256,
            reason,
            produced_by_rule,
            status,
            1 if reversible else 0,
            external_effects,
            associated_tests,
            created_by,
            created_at,
            created_at,
        ),
    )
    return get_change_set(conn, change_set_id, organization_id)  # type: ignore[return-value]


def get_change_set(conn: sqlite3.Connection, change_set_id: str, organization_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM change_sets WHERE id = ? AND organization_id = ?",
        (change_set_id, organization_id),
    ).fetchone()
    change_set = _row(row)
    if change_set is not None:
        change_set["reversible"] = bool(change_set["reversible"])
        change_set["validation_result"] = _load_json(change_set.get("validation_result"))
        change_set["associated_tests"] = _load_json(change_set.get("associated_tests"))
    return change_set


def list_change_sets(conn: sqlite3.Connection, analysis_id: str, organization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM change_sets WHERE analysis_id = ? AND organization_id = ? ORDER BY created_at DESC",
        (analysis_id, organization_id),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["reversible"] = bool(item["reversible"])
        item["validation_result"] = _load_json(item.get("validation_result"))
        item["associated_tests"] = _load_json(item.get("associated_tests"))
        result.append(item)
    return result


def update_change_set(
    conn: sqlite3.Connection,
    change_set_id: str,
    *,
    status: str | None = None,
    validation_result: str | None = None,
    approved_by: str | None = None,
    approved_at: str | None = None,
    applied_at: str | None = None,
    validated_at: str | None = None,
    rolled_back_at: str | None = None,
    updated_at: str | None = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    for column, value in (
        ("status", status),
        ("validation_result", validation_result),
        ("approved_by", approved_by),
        ("approved_at", approved_at),
        ("applied_at", applied_at),
        ("validated_at", validated_at),
        ("rolled_back_at", rolled_back_at),
        ("updated_at", updated_at),
    ):
        if value is not None:
            fields.append(f"{column} = ?")
            values.append(value)
    if not fields:
        return
    values.append(change_set_id)
    conn.execute(f"UPDATE change_sets SET {', '.join(fields)} WHERE id = ?", values)


def insert_change_files(conn: sqlite3.Connection, files: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO change_files(id, change_set_id, path, change_type, base_sha256, new_sha256,
            applied_sha256, unified_diff, created_at)
        VALUES (:id,:change_set_id,:path,:change_type,:base_sha256,:new_sha256,
            NULL,:unified_diff,:created_at)
        """,
        files,
    )


def list_change_files(conn: sqlite3.Connection, change_set_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM change_files WHERE change_set_id = ? ORDER BY path", (change_set_id,)
    ).fetchall()
    return _rows(rows)


def set_change_file_applied(conn: sqlite3.Connection, change_file_id: str, applied_sha256: str | None) -> None:
    conn.execute(
        "UPDATE change_files SET applied_sha256 = ? WHERE id = ?", (applied_sha256, change_file_id)
    )


def add_change_approval(
    conn: sqlite3.Connection,
    *,
    change_set_id: str,
    user_id: str,
    decision: str,
    comment: str | None,
    created_at: str,
) -> dict[str, Any]:
    approval_id = new_id("apr")
    conn.execute(
        "INSERT INTO change_approvals(id, change_set_id, user_id, decision, comment, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (approval_id, change_set_id, user_id, decision, comment, created_at),
    )
    return {
        "id": approval_id,
        "change_set_id": change_set_id,
        "user_id": user_id,
        "decision": decision,
        "comment": comment,
        "created_at": created_at,
    }


def list_change_approvals(conn: sqlite3.Connection, change_set_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM change_approvals WHERE change_set_id = ? ORDER BY created_at", (change_set_id,)
    ).fetchall()
    return _rows(rows)


# --------------------------------------------------------------------------- #
# Migration plans (§11/§12)
# --------------------------------------------------------------------------- #
def create_migration_plan(
    conn: sqlite3.Connection,
    *,
    plan_id: str,
    project_id: str,
    analysis_id: str,
    organization_id: str,
    source_provider: str,
    target_provider: str,
    status: str,
    target_base_url: str | None,
    target_model: str | None,
    operation_count: int,
    matrix_summary: str | None,
    plan: str | None,
    limitations: str | None,
    sources: str | None,
    verified_at: str | None,
    created_by: str,
    created_at: str,
) -> dict[str, Any]:
    conn.execute(
        """
        INSERT INTO migration_plans(id, project_id, analysis_id, organization_id, source_provider,
            target_provider, status, target_base_url, target_model, operation_count, matrix_summary,
            plan, limitations, sources, verified_at, created_by, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            plan_id,
            project_id,
            analysis_id,
            organization_id,
            source_provider,
            target_provider,
            status,
            target_base_url,
            target_model,
            operation_count,
            matrix_summary,
            plan,
            limitations,
            sources,
            verified_at,
            created_by,
            created_at,
        ),
    )
    return get_migration_plan(conn, plan_id, organization_id)  # type: ignore[return-value]


def _decode_migration(row: sqlite3.Row | None) -> dict[str, Any] | None:
    item = _row(row)
    if item is None:
        return None
    item["matrix_summary"] = _load_json(item.get("matrix_summary"))
    item["plan"] = _load_json(item.get("plan"))
    item["limitations"] = _load_json(item.get("limitations"))
    item["sources"] = _load_json(item.get("sources"))
    return item


def get_migration_plan(conn: sqlite3.Connection, plan_id: str, organization_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM migration_plans WHERE id = ? AND organization_id = ?",
        (plan_id, organization_id),
    ).fetchone()
    return _decode_migration(row)


def list_migration_plans(conn: sqlite3.Connection, project_id: str, organization_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM migration_plans WHERE project_id = ? AND organization_id = ? ORDER BY created_at DESC",
        (project_id, organization_id),
    ).fetchall()
    return [_decode_migration(row) for row in rows if row is not None]  # type: ignore[misc]


def insert_migration_changes(conn: sqlite3.Connection, changes: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO migration_changes(id, plan_id, change_ref, kind, path, action, description, diff,
            reversible, rule_id)
        VALUES (:id,:plan_id,:change_ref,:kind,:path,:action,:description,:diff,:reversible,:rule_id)
        """,
        changes,
    )


def list_migration_changes(conn: sqlite3.Connection, plan_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM migration_changes WHERE plan_id = ? ORDER BY change_ref", (plan_id,)
    ).fetchall()
    result = _rows(rows)
    for item in result:
        item["reversible"] = bool(item["reversible"])
    return result


# --------------------------------------------------------------------------- #
# Audit & usage
# --------------------------------------------------------------------------- #
def record_audit(
    conn: sqlite3.Connection,
    *,
    action: str,
    created_at: str,
    organization_id: str | None = None,
    user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_events(id, organization_id, user_id, action, target_type, target_id,
            metadata, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            new_id("aud"),
            organization_id,
            user_id,
            action,
            target_type,
            target_id,
            json.dumps(metadata or {}, ensure_ascii=False),
            created_at,
        ),
    )


def record_usage(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    metric: str,
    quantity: int,
    created_at: str,
    project_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO usage_records(id, organization_id, project_id, metric, quantity, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (new_id("usg"), organization_id, project_id, metric, quantity, created_at),
    )


def usage_totals(conn: sqlite3.Connection, organization_id: str) -> dict[str, int]:
    """Suma acumulada por métrica de uso (§21 Fase 12: gestión de uso)."""
    rows = conn.execute(
        "SELECT metric, COALESCE(SUM(quantity), 0) AS total FROM usage_records"
        " WHERE organization_id = ? GROUP BY metric",
        (organization_id,),
    ).fetchall()
    return {row["metric"]: int(row["total"]) for row in rows}


# --------------------------------------------------------------------------- #
# Binary analysis (§6.2)
# --------------------------------------------------------------------------- #
def create_binary_analysis(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    project_id: str,
    organization_id: str,
    format: str,
    architecture: str | None,
    bits: int | None,
    file_type: str | None,
    size_bytes: int,
    sha256: str,
    facts_json: str,
    created_by: str,
    created_at: str,
) -> dict[str, Any]:
    analysis_id = new_id("bin")
    conn.execute(
        """
        INSERT INTO binary_analyses(id, artifact_id, project_id, organization_id, format,
            architecture, bits, file_type, size_bytes, sha256, facts_json, created_by, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            analysis_id,
            artifact_id,
            project_id,
            organization_id,
            format,
            architecture,
            bits,
            file_type,
            size_bytes,
            sha256,
            facts_json,
            created_by,
            created_at,
        ),
    )
    return get_binary_analysis(conn, analysis_id, organization_id)  # type: ignore[return-value]


def get_binary_analysis(
    conn: sqlite3.Connection, analysis_id: str, organization_id: str
) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            "SELECT * FROM binary_analyses WHERE id = ? AND organization_id = ?",
            (analysis_id, organization_id),
        ).fetchone()
    )


def list_binary_analyses(
    conn: sqlite3.Connection, project_id: str, organization_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM binary_analyses WHERE project_id = ? AND organization_id = ?"
        " ORDER BY created_at DESC",
        (project_id, organization_id),
    ).fetchall()
    return _rows(rows)


# --------------------------------------------------------------------------- #
# Implementation Validator (§ validación de requisitos)
# --------------------------------------------------------------------------- #
def upsert_validation_requirement(
    conn: sqlite3.Connection,
    *,
    requirement_id: str,
    title: str,
    description: str,
    source_document: str | None,
    source_section: str | None,
    source_page: int | None,
    acceptance_criteria: str,
    checks: str,
    dependencies: str | None,
    related_files: str | None,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO validation_requirements(id, title, description, source_document, source_section,
            source_page, acceptance_criteria, checks, dependencies, related_files, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            description = excluded.description,
            source_document = excluded.source_document,
            source_section = excluded.source_section,
            source_page = excluded.source_page,
            acceptance_criteria = excluded.acceptance_criteria,
            checks = excluded.checks,
            dependencies = excluded.dependencies,
            related_files = excluded.related_files,
            updated_at = excluded.updated_at
        """,
        (
            requirement_id, title, description, source_document, source_section, source_page,
            acceptance_criteria, checks, dependencies, related_files, updated_at,
        ),
    )


def _decode_requirement(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    decoded = dict(row)
    decoded["acceptance_criteria"] = _load_json(decoded.get("acceptance_criteria")) or []
    decoded["checks"] = _load_json(decoded.get("checks")) or []
    decoded["dependencies"] = _load_json(decoded.get("dependencies")) or []
    decoded["related_files"] = _load_json(decoded.get("related_files")) or []
    return decoded


def list_validation_requirements(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM validation_requirements ORDER BY id").fetchall()
    return [_decode_requirement(row) for row in _rows(rows)]


def get_validation_requirement(conn: sqlite3.Connection, requirement_id: str) -> dict[str, Any] | None:
    return _decode_requirement(
        _row(conn.execute("SELECT * FROM validation_requirements WHERE id = ?", (requirement_id,)).fetchone())
    )


def create_validation_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    scope: str,
    status: str,
    code_hash: str | None,
    environment: str | None,
    requested_by: str | None,
    started_at: str,
) -> dict[str, Any]:
    conn.execute(
        """
        INSERT INTO validation_runs(id, scope, status, code_hash, environment, requested_by, started_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (run_id, scope, status, code_hash, environment, requested_by, started_at),
    )
    return get_validation_run(conn, run_id)  # type: ignore[return-value]


def finish_validation_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    status: str,
    summary: str,
    finished_at: str,
    duration_ms: int,
    limitations: str | None,
) -> None:
    conn.execute(
        "UPDATE validation_runs SET status = ?, summary = ?, finished_at = ?, duration_ms = ?, limitations = ?"
        " WHERE id = ?",
        (status, summary, finished_at, duration_ms, limitations, run_id),
    )


def get_validation_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = _row(conn.execute("SELECT * FROM validation_runs WHERE id = ?", (run_id,)).fetchone())
    if row is None:
        return None
    row["summary"] = _load_json(row.get("summary"))
    row["limitations"] = _load_json(row.get("limitations")) or []
    return row


def list_validation_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM validation_runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    result = []
    for row in _rows(rows):
        row["summary"] = _load_json(row.get("summary"))
        result.append(row)
    return result


def insert_validation_results(conn: sqlite3.Connection, results: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO validation_results(id, run_id, requirement_id, status, checks_total,
            checks_passed, checks_failed, checks_skipped, criteria_met, limitations, created_at)
        VALUES (:id,:run_id,:requirement_id,:status,:checks_total,:checks_passed,:checks_failed,
            :checks_skipped,:criteria_met,:limitations,:created_at)
        """,
        results,
    )


def insert_validation_evidence(conn: sqlite3.Connection, evidence: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO validation_evidence(id, run_id, result_id, requirement_id, check_id, check_type,
            criterion, target, status, passed, exit_code, duration_ms, command, output, limitations, created_at)
        VALUES (:id,:run_id,:result_id,:requirement_id,:check_id,:check_type,:criterion,:target,
            :status,:passed,:exit_code,:duration_ms,:command,:output,:limitations,:created_at)
        """,
        evidence,
    )


def list_validation_results(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM validation_results WHERE run_id = ? ORDER BY requirement_id", (run_id,)
    ).fetchall()
    result = []
    for row in _rows(rows):
        row["criteria_met"] = _load_json(row.get("criteria_met")) or []
        row["limitations"] = _load_json(row.get("limitations")) or []
        result.append(row)
    return result


def list_validation_evidence(
    conn: sqlite3.Connection, run_id: str, requirement_id: str | None = None
) -> list[dict[str, Any]]:
    clauses = ["run_id = ?"]
    params: list[Any] = [run_id]
    if requirement_id:
        clauses.append("requirement_id = ?")
        params.append(requirement_id)
    rows = conn.execute(
        f"SELECT * FROM validation_evidence WHERE {' AND '.join(clauses)} ORDER BY check_id", params
    ).fetchall()
    result = []
    for row in _rows(rows):
        row["limitations"] = _load_json(row.get("limitations")) or []
        result.append(row)
    return result


def latest_result_per_requirement(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Último resultado de validación por requisito (para el informe de conformidad)."""
    rows = conn.execute(
        """
        SELECT r.* FROM validation_results r
        JOIN (
            SELECT requirement_id, MAX(created_at) AS latest FROM validation_results GROUP BY requirement_id
        ) m ON m.requirement_id = r.requirement_id AND m.latest = r.created_at
        """
    ).fetchall()
    return {row["requirement_id"]: row for row in _rows(rows)}
