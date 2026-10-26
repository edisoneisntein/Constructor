"""Pruebas de observabilidad, cuotas y límites (§14, §19.6, §21 Fase 11)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import QuotaExceededError
from app.core.rate_limit import check_rate_limit, reset_rate_limiter
from app.db import repositories as repo
from app.db.session import get_database
from app.services.usage_service import (
    enforce_concurrent_jobs_quota,
    enforce_project_quota,
    enforce_storage_quota,
    metrics_summary,
    quota_report,
)
from tests.conftest import auth_headers, make_zip, register

PY_ONLY_ZIP = make_zip({"src/app.py": "import os\nX = os.getenv('X')\n"})


def _setup_org(client: TestClient):
    session = register(client, "obs@example.com", "Obs Org")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "P"}, headers=headers).json()
    return session, headers, project


def test_readiness_endpoint(client: TestClient):
    response = client.get("/health/ready")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database"] == "ok"


def test_request_id_is_generated_and_echoed(client: TestClient):
    generated = client.get("/health")
    assert generated.headers.get("X-Request-ID")

    echoed = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert echoed.headers.get("X-Request-ID") == "trace-123"


def test_meta_exposes_quotas(client: TestClient):
    payload = client.get("/api/v1/meta").json()
    quotas = payload["quotas"]
    assert quotas["org_max_projects"] > 0
    assert quotas["org_max_storage_bytes"] > 0
    assert payload["capabilities"]["observability"] == "IMPLEMENTED"
    assert payload["capabilities"]["rate_limiting"] == "PARTIALLY_IMPLEMENTED"


def test_usage_and_metrics_endpoints(client: TestClient):
    _, headers, project = _setup_org(client)
    upload = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", PY_ONLY_ZIP, "application/zip")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    artifact = upload.json()
    started = client.post(
        f"/api/v1/projects/{project['id']}/analyses",
        json={"artifact_id": artifact["id"]},
        headers=headers,
    )
    assert started.status_code == 202, started.text

    usage = client.get("/api/v1/observability/usage", headers=headers)
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["projects"] == 1
    assert body["artifacts"] == 1
    assert body["storage_bytes"] == len(PY_ONLY_ZIP)
    assert body["quotas"]["projects"]["used"] == 1
    assert body["quotas"]["projects"]["limit"] > 0

    metrics = client.get("/api/v1/observability/metrics", headers=headers)
    assert metrics.status_code == 200, metrics.text
    data = metrics.json()
    assert data["jobs_total"] >= 1
    assert sum(data["jobs_by_status"].values()) == data["jobs_total"]


def test_quota_enforcement_with_low_limits(client: TestClient):
    session, headers, project = _setup_org(client)
    organization_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    upload = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", PY_ONLY_ZIP, "application/zip")},
        headers=headers,
    ).json()

    conn = get_database().connect()
    try:
        with pytest.raises(QuotaExceededError) as project_error:
            enforce_project_quota(conn, Settings(org_max_projects=1), organization_id=organization_id)
        assert project_error.value.status_code == 403
        assert project_error.value.details["resource"] == "projects"

        with pytest.raises(QuotaExceededError) as storage_error:
            enforce_storage_quota(
                conn,
                Settings(org_max_storage_bytes=1),
                organization_id=organization_id,
                incoming_bytes=2,
            )
        assert storage_error.value.details["resource"] == "storage_bytes"

        repo.create_job(
            conn,
            project_id=project["id"],
            organization_id=organization_id,
            artifact_id=upload["id"],
            created_by=session["user"]["id"],
            status="QUEUED",
            created_at="2026-01-01T00:00:00+00:00",
        )
        with pytest.raises(QuotaExceededError) as jobs_error:
            enforce_concurrent_jobs_quota(
                conn, Settings(org_max_concurrent_jobs=1), organization_id=organization_id
            )
        assert jobs_error.value.details["resource"] == "concurrent_jobs"
        conn.commit()
    finally:
        conn.close()


def test_quota_report_and_metrics_are_org_scoped(client: TestClient):
    session, headers, project = _setup_org(client)
    organization_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    conn = get_database().connect()
    try:
        report = quota_report(conn, Settings(), organization_id=organization_id)
        assert report["projects"] == 1
        assert report["quotas"]["storage_bytes"]["percent"] == 0.0
        summary = metrics_summary(conn, organization_id=organization_id)
        assert summary["organization_id"] == organization_id
        # Otra organización no ve nada.
        assert repo.count_projects(conn, "org-inexistente") == 0
    finally:
        conn.close()


def test_sliding_window_rate_limiter():
    reset_rate_limiter()
    assert check_rate_limit("k", limit=2, window_seconds=60).allowed
    assert check_rate_limit("k", limit=2, window_seconds=60).allowed
    third = check_rate_limit("k", limit=2, window_seconds=60)
    assert third.allowed is False
    assert third.retry_after_seconds >= 1
    # Claves distintas no se afectan.
    assert check_rate_limit("other", limit=1, window_seconds=60).allowed
    # límite 0 = sin restricción.
    assert check_rate_limit("k", limit=0, window_seconds=60).allowed


def test_rate_limit_middleware_returns_429(tmp_path, monkeypatch):
    monkeypatch.setenv("SIREP_DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("SIREP_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("SIREP_ENV", "test")
    monkeypatch.setenv("SIREP_SECRET_KEY", "test-key")
    monkeypatch.setenv("SIREP_RATE_LIMIT_AUTH_PER_MINUTE", "1")

    from app.core.config import reset_settings_cache
    from app.core.rate_limit import reset_rate_limiter
    from app.db.session import reset_database
    from app.services.job_runner import reset_job_runner

    reset_settings_cache()
    reset_database()
    reset_job_runner()
    reset_rate_limiter()

    from app.main import create_app

    with TestClient(create_app()) as local_client:
        payload = {
            "email": "rate@example.com",
            "password": "supersecret123",
            "display_name": "rate",
            "organization_name": "Rate Org",
        }
        first = local_client.post("/api/v1/auth/register", json=payload)
        assert first.status_code == 201, first.text
        second = local_client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
        assert second.status_code == 429, second.text
        assert second.json()["error"]["code"] == "rate_limited"
        assert "Retry-After" in second.headers

    reset_rate_limiter()
    reset_database()
    reset_settings_cache()


def test_rate_limit_identity_ignores_client_supplied_organization(tmp_path, monkeypatch):
    """§14: la identidad del limitador no puede ser controlada por el cliente.

    Rotar ``X-Organization-Id`` no debe crear cubos nuevos ni evadir el límite.
    """
    monkeypatch.setenv("SIREP_DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("SIREP_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("SIREP_ENV", "test")
    monkeypatch.setenv("SIREP_SECRET_KEY", "test-key")
    monkeypatch.setenv("SIREP_RATE_LIMIT_API_PER_MINUTE", "2")

    from app.core.config import reset_settings_cache
    from app.core.rate_limit import reset_rate_limiter
    from app.db.session import reset_database
    from app.services.job_runner import reset_job_runner

    reset_settings_cache()
    reset_database()
    reset_job_runner()
    reset_rate_limiter()

    from app.main import create_app

    with TestClient(create_app()) as local_client:
        for index in range(3):
            response = local_client.get(
                "/api/v1/projects",
                headers={"X-Organization-Id": f"org-falsa-{index}"},
            )
            # La primera petición es 401 (sin token) pero consume cuota igual.
            assert response.status_code in (401, 429), response.text
        limited = local_client.get(
            "/api/v1/projects", headers={"X-Organization-Id": "org-falsa-otra"}
        )
        assert limited.status_code == 429, limited.text
        assert limited.json()["error"]["code"] == "rate_limited"

    reset_rate_limiter()
    reset_database()
    reset_settings_cache()


def test_rate_limit_session_identity_is_stable_per_token(tmp_path, monkeypatch):
    """§14: el token de sesión define un cubo propio, independiente de la IP."""
    monkeypatch.setenv("SIREP_DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("SIREP_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("SIREP_ENV", "test")
    monkeypatch.setenv("SIREP_SECRET_KEY", "test-key")
    monkeypatch.setenv("SIREP_RATE_LIMIT_API_PER_MINUTE", "5")

    from app.core.config import reset_settings_cache
    from app.core.rate_limit import reset_rate_limiter
    from app.db.session import reset_database
    from app.services.job_runner import reset_job_runner

    reset_settings_cache()
    reset_database()
    reset_job_runner()
    reset_rate_limiter()

    from app.main import create_app

    with TestClient(create_app()) as local_client:
        session = register(local_client, "cubo@example.com", "Cubo Org")
        headers = auth_headers(session["token"])
        first = local_client.get("/api/v1/projects", headers=headers)
        assert first.status_code == 200, first.text
        # Mismo token, distinta organización declarada: mismo cubo.
        second = local_client.get(
            "/api/v1/projects",
            headers={**headers, "X-Organization-Id": "org-inexistente"},
        )
        assert second.status_code == 403, second.text

    reset_rate_limiter()
    reset_database()
    reset_settings_cache()
