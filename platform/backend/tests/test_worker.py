"""Cola externa y proceso trabajador (§4.3, §21 Fase 13)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_headers, make_zip, register

SAMPLE_ZIP = make_zip(
    {
        "src/app.py": "import os\nKEY = os.getenv('GEMINI_API_KEY')\ndef main():\n    return KEY\n",
    }
)


@pytest.fixture()
def external_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """Cliente con la cola de trabajos en modo externo."""

    monkeypatch.setenv("SIREP_DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("SIREP_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("SIREP_ENV", "test")
    monkeypatch.setenv("SIREP_SECRET_KEY", "test-key")
    monkeypatch.setenv("SIREP_JOB_QUEUE", "external")

    from app.core.config import reset_settings_cache
    from app.db.session import reset_database
    from app.services.job_runner import reset_job_runner

    reset_settings_cache()
    reset_database()
    reset_job_runner()

    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    reset_job_runner()
    reset_database()
    reset_settings_cache()


def _prepare_job(client: TestClient, email: str = "w@example.com") -> dict:
    session = register(client, email, "Workers")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "Cola"}, headers=headers).json()
    upload = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    started = client.post(
        f"/api/v1/projects/{project['id']}/analyses",
        json={"artifact_id": upload.json()["id"]},
        headers=headers,
    )
    assert started.status_code == 202, started.text
    return {"headers": headers, "project": project, "job": started.json()}


def _conn():
    from app.db.session import get_database

    return get_database().connect()


def test_external_queue_leaves_job_queued_and_worker_completes(external_client: TestClient):
    from app.core.config import get_settings
    from app.worker import Worker

    ctx = _prepare_job(external_client)
    assert ctx["job"]["status"] == "QUEUED"

    worker = Worker(get_settings(), worker_id="wrk-test")
    assert worker.run_once() is True

    summary = external_client.get(
        f"/api/v1/analyses/{ctx['job']['id']}", headers=ctx["headers"]
    ).json()
    assert summary["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}
    assert summary["node_count"] >= 1
    assert summary["finding_count"] >= 1


def test_claim_next_job_is_exclusive(external_client: TestClient):
    from app.core.ids import utcnow_iso
    from app.db import repositories as repo

    first = _prepare_job(external_client, email="a@example.com")
    second = _prepare_job(external_client, email="b@example.com")

    conn = _conn()
    try:
        claimed_a = repo.claim_next_job(conn, worker_id="w1", now=utcnow_iso())
        claimed_b = repo.claim_next_job(conn, worker_id="w2", now=utcnow_iso())
        assert claimed_a is not None and claimed_b is not None
        assert claimed_a["id"] != claimed_b["id"]
        assert {claimed_a["id"], claimed_b["id"]} == {first["job"]["id"], second["job"]["id"]}
        assert repo.claim_next_job(conn, worker_id="w3", now=utcnow_iso()) is None
    finally:
        conn.close()


def test_recover_requeues_stale_job_and_worker_finishes_it(external_client: TestClient):
    from app.core.config import get_settings
    from app.core.ids import new_id, utcnow_iso
    from app.db import repositories as repo
    from app.worker import Worker

    ctx = _prepare_job(external_client)
    job_id = ctx["job"]["id"]

    conn = _conn()
    try:
        repo.claim_next_job(conn, worker_id="dead", now=utcnow_iso())
        conn.execute(
            "UPDATE analysis_jobs SET claimed_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", job_id),
        )
        conn.commit()
        result = repo.recover_stale_jobs(
            conn, now=utcnow_iso(), stale_seconds=60, max_attempts=3
        )
        assert result["requeued"] == 1 and result["failed"] == 0
        job = repo.get_job(conn, job_id, ctx["project"]["organization_id"])
        assert job["status"] == "QUEUED"
    finally:
        conn.close()

    worker = Worker(get_settings(), worker_id=new_id("wrk"))
    assert worker.run_once() is True
    summary = external_client.get(
        f"/api/v1/analyses/{job_id}", headers=ctx["headers"]
    ).json()
    assert summary["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}


def test_recover_marks_exhausted_job_failed(external_client: TestClient):
    from app.core.ids import utcnow_iso
    from app.db import repositories as repo

    ctx = _prepare_job(external_client)
    job_id = ctx["job"]["id"]

    conn = _conn()
    try:
        repo.claim_next_job(conn, worker_id="dead", now=utcnow_iso())
        conn.execute(
            "UPDATE analysis_jobs SET claimed_at = ?, attempt_count = 5 WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", job_id),
        )
        conn.commit()
        result = repo.recover_stale_jobs(conn, now=utcnow_iso(), stale_seconds=60, max_attempts=3)
        assert result["failed"] == 1 and result["requeued"] == 0
        job = repo.get_job(conn, job_id, ctx["project"]["organization_id"])
        assert job["status"] == "FAILED"
        assert job["error_code"] == "worker_lost"
    finally:
        conn.close()


def test_cancel_queued_job_external_stops_worker(external_client: TestClient):
    from app.core.config import get_settings
    from app.worker import Worker

    ctx = _prepare_job(external_client)
    job_id = ctx["job"]["id"]

    cancel = external_client.post(
        f"/api/v1/analyses/{job_id}/cancel", headers=ctx["headers"]
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "CANCELLED"

    worker = Worker(get_settings(), worker_id="wrk-cancel")
    worker.run_once()

    summary = external_client.get(
        f"/api/v1/analyses/{job_id}", headers=ctx["headers"]
    ).json()
    assert summary["job"]["status"] == "CANCELLED"


def test_worker_purges_expired_artifacts(external_client: TestClient):
    from app.core.config import get_settings
    from app.worker import Worker

    session = register(external_client, "purge@example.com", "PurgeOrg")
    headers = auth_headers(session["token"])
    project = external_client.post("/api/v1/projects", json={"name": "P"}, headers=headers).json()
    upload = external_client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    )
    artifact_id = upload.json()["id"]

    conn = _conn()
    try:
        conn.execute(
            "UPDATE artifacts SET created_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", artifact_id),
        )
        conn.commit()
    finally:
        conn.close()

    settings = get_settings().model_copy(
        update={"workspace_retention_seconds": 1, "retention_purge_interval_seconds": 60.0}
    )
    worker = Worker(settings, worker_id="wrk-purge")
    conn = _conn()
    try:
        purged = worker.maybe_purge(conn)
    finally:
        conn.close()
    assert purged >= 1

    listing = external_client.get(
        f"/api/v1/projects/{project['id']}/artifacts", headers=headers
    ).json()
    assert all(item["id"] != artifact_id for item in listing)


def test_worker_observes_cross_process_cancel(external_client: TestClient):
    """La cancelación cooperativa se lee de la base, no de memoria del proceso."""

    from app.core.ids import utcnow_iso
    from app.db import repositories as repo

    ctx = _prepare_job(external_client)
    job_id = ctx["job"]["id"]

    conn = _conn()
    try:
        repo.claim_next_job(conn, worker_id="w", now=utcnow_iso())
        repo.request_cancel(conn, job_id, ctx["project"]["organization_id"])
        conn.commit()
        assert repo.is_cancel_requested(conn, job_id) is True
    finally:
        conn.close()
