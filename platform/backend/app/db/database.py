"""Persistencia (§4.4, §16).

MVP: SQLite (stdlib) tras una capa de repositorio, migrable a PostgreSQL en la
Fase 11 sin tocar la lógica de negocio. Se aplican claves foráneas e índices.
Todas las consultas son parametrizadas.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

SCHEMA_VERSION = 8

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organization_memberships (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (organization_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        created_by TEXT NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        filename TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        detected_mime TEXT NOT NULL,
        declared_mime TEXT,
        storage_path TEXT NOT NULL,
        retention_policy TEXT NOT NULL,
        validation_state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        deleted_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analysis_jobs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        phase TEXT,
        progress_completed INTEGER NOT NULL DEFAULT 0,
        progress_total INTEGER NOT NULL DEFAULT 0,
        error_code TEXT,
        error_message TEXT,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        result_summary TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        claimed_by TEXT,
        claimed_at TEXT,
        created_by TEXT NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analysis_findings (
        id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        language TEXT,
        file_path TEXT,
        line_start INTEGER,
        line_end INTEGER,
        symbol TEXT,
        evidence_level TEXT NOT NULL,
        detection_method TEXT NOT NULL,
        tool TEXT NOT NULL,
        tool_version TEXT,
        snippet TEXT,
        message TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS architecture_nodes (
        id TEXT NOT NULL,
        analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        node_type TEXT NOT NULL,
        label TEXT NOT NULL,
        path TEXT,
        language TEXT,
        evidence_level TEXT NOT NULL,
        detection_method TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (analysis_id, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS architecture_edges (
        id TEXT NOT NULL,
        analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        source_node_id TEXT NOT NULL,
        target_node_id TEXT,
        target_ref TEXT,
        edge_type TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        detection_method TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (analysis_id, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dependency_records (
        id TEXT NOT NULL,
        analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        ecosystem TEXT NOT NULL,
        name TEXT NOT NULL,
        version TEXT,
        source_file TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (analysis_id, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_sets (
        id TEXT PRIMARY KEY,
        analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        workspace_path TEXT NOT NULL,
        before_root TEXT NOT NULL,
        after_root TEXT NOT NULL,
        base_artifact_sha256 TEXT,
        reason TEXT NOT NULL,
        produced_by_rule TEXT NOT NULL,
        status TEXT NOT NULL,
        reversible INTEGER NOT NULL DEFAULT 1,
        external_effects TEXT,
        validation_result TEXT,
        associated_tests TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        approved_by TEXT,
        approved_at TEXT,
        applied_at TEXT,
        validated_at TEXT,
        rolled_back_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_files (
        id TEXT PRIMARY KEY,
        change_set_id TEXT NOT NULL REFERENCES change_sets(id) ON DELETE CASCADE,
        path TEXT NOT NULL,
        change_type TEXT NOT NULL,
        base_sha256 TEXT,
        new_sha256 TEXT,
        applied_sha256 TEXT,
        unified_diff TEXT,
        created_at TEXT NOT NULL,
        UNIQUE (change_set_id, path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_approvals (
        id TEXT PRIMARY KEY,
        change_set_id TEXT NOT NULL REFERENCES change_sets(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS migration_plans (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        analysis_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        source_provider TEXT NOT NULL,
        target_provider TEXT NOT NULL,
        status TEXT NOT NULL,
        target_base_url TEXT,
        target_model TEXT,
        operation_count INTEGER NOT NULL DEFAULT 0,
        matrix_summary TEXT,
        plan TEXT,
        limitations TEXT,
        sources TEXT,
        verified_at TEXT,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS migration_changes (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL REFERENCES migration_plans(id) ON DELETE CASCADE,
        change_ref TEXT NOT NULL,
        kind TEXT NOT NULL,
        path TEXT,
        action TEXT NOT NULL,
        description TEXT NOT NULL,
        diff TEXT,
        reversible INTEGER NOT NULL DEFAULT 1,
        rule_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id TEXT PRIMARY KEY,
        organization_id TEXT,
        user_id TEXT,
        action TEXT NOT NULL,
        target_type TEXT,
        target_id TEXT,
        metadata TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usage_records (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id TEXT,
        metric TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS binary_analyses (
        id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        format TEXT NOT NULL,
        architecture TEXT,
        bits INTEGER,
        file_type TEXT,
        size_bytes INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        facts_json TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_memberships_user ON organization_memberships(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(organization_id)",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_project ON analysis_jobs(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON analysis_jobs(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_findings_analysis ON analysis_findings(analysis_id)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_analysis ON architecture_nodes(analysis_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_analysis ON architecture_edges(analysis_id)",
    "CREATE INDEX IF NOT EXISTS idx_deps_analysis ON dependency_records(analysis_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_hash ON sessions(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_change_sets_analysis ON change_sets(analysis_id)",
    "CREATE INDEX IF NOT EXISTS idx_change_files_set ON change_files(change_set_id)",
    "CREATE INDEX IF NOT EXISTS idx_change_approvals_set ON change_approvals(change_set_id)",
    "CREATE INDEX IF NOT EXISTS idx_migration_plans_project ON migration_plans(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_migration_changes_plan ON migration_changes(plan_id)",
    "CREATE INDEX IF NOT EXISTS idx_binary_analyses_project ON binary_analyses(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_records_org ON usage_records(organization_id)",
    """
    CREATE TABLE IF NOT EXISTS rate_limit_counters (
        scope_key TEXT PRIMARY KEY,
        window_start INTEGER NOT NULL,
        count INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS validation_requirements (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        source_document TEXT,
        source_section TEXT,
        source_page INTEGER,
        acceptance_criteria TEXT NOT NULL,
        checks TEXT NOT NULL,
        dependencies TEXT,
        related_files TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS validation_runs (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL,
        status TEXT NOT NULL,
        code_hash TEXT,
        environment TEXT,
        summary TEXT,
        requested_by TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        duration_ms INTEGER,
        limitations TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS validation_results (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
        requirement_id TEXT NOT NULL,
        status TEXT NOT NULL,
        checks_total INTEGER NOT NULL,
        checks_passed INTEGER NOT NULL,
        checks_failed INTEGER NOT NULL,
        checks_skipped INTEGER NOT NULL DEFAULT 0,
        criteria_met TEXT,
        limitations TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS validation_evidence (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
        result_id TEXT NOT NULL REFERENCES validation_results(id) ON DELETE CASCADE,
        requirement_id TEXT NOT NULL,
        check_id TEXT NOT NULL,
        check_type TEXT NOT NULL,
        criterion TEXT,
        target TEXT,
        status TEXT NOT NULL,
        passed INTEGER NOT NULL,
        exit_code INTEGER,
        duration_ms INTEGER,
        command TEXT,
        output TEXT,
        limitations TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_validation_results_run ON validation_results(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_validation_results_req ON validation_results(requirement_id)",
    "CREATE INDEX IF NOT EXISTS idx_validation_evidence_run ON validation_evidence(run_id)",
]

GRAPH_TABLE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_nodes_analysis ON architecture_nodes(analysis_id)",
    "CREATE INDEX IF NOT EXISTS idx_edges_analysis ON architecture_edges(analysis_id)",
    "CREATE INDEX IF NOT EXISTS idx_deps_analysis ON dependency_records(analysis_id)",
]

_GRAPH_TABLE_DDL = {
    "architecture_nodes": """
    CREATE TABLE IF NOT EXISTS architecture_nodes (
        id TEXT NOT NULL,
        analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        node_type TEXT NOT NULL,
        label TEXT NOT NULL,
        path TEXT,
        language TEXT,
        evidence_level TEXT NOT NULL,
        detection_method TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (analysis_id, id)
    )
    """,
    "architecture_edges": """
    CREATE TABLE IF NOT EXISTS architecture_edges (
        id TEXT NOT NULL,
        analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        source_node_id TEXT NOT NULL,
        target_node_id TEXT,
        target_ref TEXT,
        edge_type TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        detection_method TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (analysis_id, id)
    )
    """,
    "dependency_records": """
    CREATE TABLE IF NOT EXISTS dependency_records (
        id TEXT NOT NULL,
        analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
        project_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        ecosystem TEXT NOT NULL,
        name TEXT NOT NULL,
        version TEXT,
        source_file TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (analysis_id, id)
    )
    """,
}


def _column_names(connection, table: str, *, postgres: bool = False) -> set[str]:
    if postgres:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,)
        ).fetchall()
        return {row["column_name"] for row in rows}
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _migrate_job_claim_columns(connection, *, postgres: bool = False) -> None:
    """Añade columnas de reclamo/heartbeat a ``analysis_jobs`` — schema v6.

    Permite que un proceso trabajador externo reclame trabajos y detecte los
    huérfanos (worker caído) sin cambiar el contrato de la API. Idempotente.
    """

    existing = _column_names(connection, "analysis_jobs", postgres=postgres)
    additions = {
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "claimed_by": "TEXT",
        "claimed_at": "TEXT",
    }
    for column, ddl in additions.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE analysis_jobs ADD COLUMN {column} {ddl}")


def _migrate_graph_composite_keys(connection, *, postgres: bool = False) -> None:
    """Rebuild graph tables to use PRIMARY KEY (analysis_id, id) — schema v5.

    Los identificadores de nodo son deterministas (p. ej. ``sym::ruta::name``),
    por lo que la clave primaria debe incluir ``analysis_id`` para permitir más
    de un análisis sobre contenidos equivalentes. Idempotente.

    En PostgreSQL las tablas se crean ya con la clave compuesta, por lo que no se
    requiere reconstrucción (y no existe ``sqlite_master``).
    """

    if postgres:
        return

    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='architecture_nodes'"
    ).fetchone()
    if row is None:
        return
    if "PRIMARY KEY (analysis_id, id)" in (row["sql"] or ""):
        return
    for table, ddl in _GRAPH_TABLE_DDL.items():
        tmp = f"{table}__v4"
        connection.execute(f"ALTER TABLE {table} RENAME TO {tmp}")
        connection.execute(ddl)
        connection.execute(f"INSERT OR IGNORE INTO {table} SELECT * FROM {tmp}")
        connection.execute(f"DROP TABLE {tmp}")
    for statement in GRAPH_TABLE_INDEXES:
        connection.execute(statement)


class Database:
    """Fachada de persistencia con dos dialectos tras la misma interfaz.

    - SQLite (por defecto): archivo o ``:memory:``.
    - PostgreSQL: cuando el destino es una URL ``postgresql://`` (§4.4).
    """

    def __init__(self, target: Path | str) -> None:
        raw = str(target)
        self.url: str | None = raw if raw.startswith(("postgresql://", "postgres://")) else None
        self.is_postgres = self.url is not None
        self._memory_connection: sqlite3.Connection | None = None
        if self.is_postgres:
            self.path = Path("postgresql")
        else:
            self.path = Path(raw)
            if str(self.path) != ":memory:":
                self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def is_ephemeral(self) -> bool:
        """Cierto solo para SQLite en memoria (conexión reutilizada)."""
        return not self.is_postgres and str(self.path) == ":memory:"

    @property
    def label(self) -> str:
        """Etiqueta segura para registros (sin credenciales)."""
        if self.is_postgres:
            from urllib.parse import urlsplit

            parts = urlsplit(self.url or "")
            return f"postgresql://{parts.hostname or '?'}:{parts.port or 5432}{parts.path}"
        return str(self.path)

    def connect(self):
        if self.is_postgres:
            return self._new_pg_connection()
        if self.is_ephemeral:
            if self._memory_connection is None:
                self._memory_connection = self._new_connection()
            return self._memory_connection
        return self._new_connection()

    def _new_connection(self) -> sqlite3.Connection:
        target = ":memory:" if self.is_ephemeral else str(self.path)
        connection = sqlite3.connect(target, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _new_pg_connection(self):
        from psycopg import connect as pg_connect
        from psycopg.rows import dict_row

        from app.db.pg import PostgresConnection

        return PostgresConnection(pg_connect(self.url, row_factory=dict_row))

    @contextlib.contextmanager
    def transaction(self) -> Iterator:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if not self.is_ephemeral:
                connection.close()

    def initialize(self, now: str) -> None:
        connection = self.connect()
        try:
            with connection:
                for statement in SCHEMA_STATEMENTS:
                    connection.execute(statement)
                _migrate_graph_composite_keys(connection, postgres=self.is_postgres)
                _migrate_job_claim_columns(connection, postgres=self.is_postgres)
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, now),
                )
        finally:
            if not self.is_ephemeral:
                connection.close()
