"""Persistencia en PostgreSQL (§4.4).

Prueba de integración contra un PostgreSQL real. Se ejecuta solo si se define
``SIREP_TEST_POSTGRES_URL`` (p. ej. ``postgresql://sirep:sirep@127.0.0.1:55432/sirep``);
por defecto se omite para no depender de la red. Verifica que la **misma** capa de
repositorio (SQL escrito para SQLite) funcione sobre PostgreSQL mediante el
adaptador de dialecto, incluidos ``UPDATE ... RETURNING``, ``ON CONFLICT`` y los
marcadores de parámetros.
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_headers, make_zip, register

POSTGRES_URL = os.environ.get("SIREP_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Defina SIREP_TEST_POSTGRES_URL para ejecutar las pruebas de PostgreSQL.",
)

SAMPLE_ZIP = make_zip(
    {
        "src/app.py": "import os\nKEY = os.getenv('GEMINI_API_KEY')\ndef main():\n    return KEY\n",
        "package.json": '{"name":"demo","dependencies":{"@google/generative-ai":"^0.21.0"}}',
    }
)


def _reset_schema(url: str) -> None:
    from psycopg import connect

    with connect(url) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")


def _build_client(tmp_path, monkeypatch, *, queue: str):
    _reset_schema(POSTGRES_URL)

    monkeypatch.setenv("SIREP_DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("SIREP_DATABASE_PATH", str(tmp_path / "unused.sqlite3"))
    monkeypatch.setenv("SIREP_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("SIREP_ENV", "test")
    monkeypatch.setenv("SIREP_SECRET_KEY", "test-key")
    monkeypatch.setenv("SIREP_RATE_LIMIT_BACKEND", "database")
    monkeypatch.setenv("SIREP_JOB_QUEUE", queue)

    from app.core.config import reset_settings_cache
    from app.core.rate_limit import reset_rate_limiter
    from app.db.session import reset_database
    from app.services.job_runner import reset_job_runner

    reset_settings_cache()
    reset_database()
    reset_job_runner()
    reset_rate_limiter()

    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    client.__enter__()
    return client


def _close_client() -> None:
    from app.core.config import reset_settings_cache
    from app.core.rate_limit import reset_rate_limiter
    from app.db.session import reset_database
    from app.services.job_runner import reset_job_runner

    reset_job_runner()
    reset_database()
    reset_settings_cache()
    reset_rate_limiter()


@pytest.fixture()
def pg_client(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, queue="inline")
    try:
        yield client
    finally:
        client.__exit__(None, None, None)
        _close_client()


@pytest.fixture()
def pg_client_external(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch, queue="external")
    try:
        yield client
    finally:
        client.__exit__(None, None, None)
        _close_client()


def _wait_for_analysis(client: TestClient, headers: dict, analysis_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()
        if payload["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS", "FAILED", "CANCELLED"}:
            return payload
        time.sleep(0.1)
    raise AssertionError("El análisis no finalizó en PostgreSQL.")


def test_schema_initialized_on_postgres(pg_client: TestClient):
    from psycopg import connect
    from psycopg.rows import dict_row

    with connect(POSTGRES_URL, row_factory=dict_row) as conn:
        tables = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
    assert {"users", "organizations", "analysis_jobs", "architecture_nodes", "change_sets"} <= tables


def test_full_vertical_flow_on_postgres(pg_client: TestClient):
    session = register(pg_client, "owner@pg.example.com", "Acme")
    headers = auth_headers(session["token"])
    org_id = pg_client.get("/api/v1/organizations", headers=headers).json()[0]["id"]

    project = pg_client.post("/api/v1/projects", json={"name": "PG Demo"}, headers=headers)
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    upload = pg_client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    artifact_id = upload.json()["id"]

    started = pg_client.post(
        f"/api/v1/projects/{project_id}/analyses", json={"artifact_id": artifact_id}, headers=headers
    )
    assert started.status_code == 202, started.text
    analysis_id = started.json()["id"]

    summary = _wait_for_analysis(pg_client, headers, analysis_id)
    assert summary["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}
    assert summary["finding_count"] >= 1
    assert summary["node_count"] >= 1

    graph = pg_client.get(f"/api/v1/analyses/{analysis_id}/architecture", headers=headers)
    assert graph.status_code == 200 and graph.json()["node_count"] >= 1

    created = pg_client.post(
        f"/api/v1/analyses/{analysis_id}/change-sets",
        json={
            "reason": "Ajuste de prueba en PostgreSQL (§4.4).",
            "produced_by_rule": "TEST-PG",
            "edits": [{"path": "src/app.py", "new_content": "def main():\n    return 42\n"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    change_id = created.json()["id"]
    assert created.json()["status"] == "PROPOSED"

    for action in ("approve", "apply", "validate"):
        payload = {"decision": "approved"} if action == "approve" else None
        step = pg_client.post(f"/api/v1/change-sets/{change_id}/{action}", json=payload, headers=headers)
        assert step.status_code == 200, f"{action}: {step.text}"
    assert step.json()["status"] == "VALIDATED"


def test_rate_limiter_uses_postgres(pg_client: TestClient):
    from app.core.rate_limit import check_rate_limit

    key = f"pg-test-{time.time()}"
    results = [check_rate_limit(key, limit=3, window_seconds=60) for _ in range(4)]
    assert all(result.allowed for result in results[:3])
    assert results[3].allowed is False


def test_worker_claim_uses_returning(pg_client_external: TestClient):
    from app.db import repositories as repo
    from app.db.session import get_database

    client = pg_client_external
    session = register(client, "claimer@pg.example.com", "Acme")
    headers = auth_headers(session["token"])
    project_id = client.post("/api/v1/projects", json={"name": "Q"}, headers=headers).json()["id"]
    artifact_id = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    ).json()["id"]
    analysis_id = client.post(
        f"/api/v1/projects/{project_id}/analyses", json={"artifact_id": artifact_id}, headers=headers
    ).json()["id"]

    database = get_database()
    conn = database.connect()
    try:
        claimed = repo.claim_next_job(conn, worker_id="pg-worker", now="2026-01-01T00:00:00+00:00")
        conn.commit()
    finally:
        if not database.is_ephemeral:
            conn.close()

    assert claimed is not None
    assert claimed["id"] == analysis_id
    assert claimed["status"] == "RUNNING"
    assert claimed["claimed_by"] == "pg-worker"
    assert claimed["attempt_count"] == 1
