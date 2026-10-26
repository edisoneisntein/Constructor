"""Pruebas de seguridad (§19.3): perfiles, sandbox, SSRF, redacción, IDOR y retención."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError
from app.core.execution_profiles import (
    DEFAULT_PROFILE,
    ExecutionProfile,
    assert_profile_allowed,
    current_profile_spec,
    enabled_profiles,
)
from app.core.logging import redact
from app.core.net_guard import is_host_allowed, validate_outbound_url
from app.core.sandbox import build_preexec, limits_supported, subprocess_limits
from tests.conftest import auth_headers, make_zip, register

PY_ONLY_ZIP = make_zip({"src/app.py": "import os\nVALUE = os.getenv('X')\n"})
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_default_execution_profile_is_static_and_high_risk_disabled():
    settings = Settings()
    assert DEFAULT_PROFILE is ExecutionProfile.STATIC_ANALYSIS
    assert settings.execution_profile == "STATIC_ANALYSIS"
    assert ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS.value not in enabled_profiles(settings)
    with pytest.raises(ForbiddenError):
        assert_profile_allowed(ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS, settings)


def test_high_risk_profile_requires_explicit_flag():
    disabled = Settings()
    with pytest.raises(ForbiddenError):
        assert_profile_allowed(ExecutionProfile.ISOLATED_TEST_EXECUTION, disabled)
    enabled = Settings(execution_profile="HIGH_RISK_DYNAMIC_ANALYSIS", execution_allow_high_risk=True)
    assert_profile_allowed(ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS, enabled)
    assert ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS.value in enabled_profiles(enabled)


def test_meta_exposes_security_configuration(client: TestClient):
    response = client.get("/api/v1/meta")
    assert response.status_code == 200, response.text
    payload = response.json()
    execution = payload["security"]["execution"]
    assert execution["profile"] == "ISOLATED_TEST_EXECUTION"
    assert execution["high_risk_enabled"] is False
    assert "HIGH_RISK_DYNAMIC_ANALYSIS" not in execution["enabled_profiles"]
    assert "ISOLATED_TEST_EXECUTION" in execution["enabled_profiles"]
    assert payload["capabilities"]["execution_profiles"] == "IMPLEMENTED"


def test_sandbox_preexec_construction():
    if not limits_supported():
        assert build_preexec(cpu_seconds=5) is None
        assert subprocess_limits(Settings()) == {}
        return
    preexec = build_preexec(cpu_seconds=5, max_file_bytes=1024)
    assert callable(preexec)
    kwargs = subprocess_limits(Settings())
    assert "preexec_fn" in kwargs and callable(kwargs["preexec_fn"])


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.10/",
        "http://[::1]/",
        "ftp://example.com/file",
        "file:///etc/passwd",
    ],
)
def test_net_guard_blocks_internal_and_unsupported(url: str):
    with pytest.raises(ForbiddenError):
        validate_outbound_url(url)


def test_net_guard_allows_external_and_enforces_allowlist():
    validate_outbound_url("https://integrate.api.nvidia.com/v1/chat/completions")
    assert is_host_allowed("integrate.api.nvidia.com")
    assert not is_host_allowed("localhost")
    with pytest.raises(ForbiddenError):
        validate_outbound_url("https://evil.example.com/", allowlist=["integrate.api.nvidia.com"])
    validate_outbound_url("https://integrate.api.nvidia.com/v1", allowlist=["integrate.api.nvidia.com"])


def test_secret_redaction_covers_common_providers():
    samples = [
        "Authorization: Bearer abc123def456",
        "api_key=sk-live-0123456789",
        "AIzaSyA1234567890abcdefghijklmnopqrst",
        "nvapi-abcdefghijklmnop",
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_0123456789abcdefghijklmnopqrstuvwx",
        "xoxb-1234567890-abcdefghijklm",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc",
        "-----BEGIN RSA PRIVATE KEY-----",
        '{"private_key": "-----BEGIN PRIVATE KEY-----"}',
    ]
    for sample in samples:
        assert "[REDACTED]" in redact(sample), sample
        assert "nvapi-abcdefghijklmnop" != redact(sample)


def test_upload_detects_type_by_content_not_extension(client: TestClient):
    session = register(client, "mime@example.com", "Mime Org")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "Mime"}, headers=headers).json()

    disguised_zip = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("logo.png", PY_ONLY_ZIP, "image/png")},
        headers=headers,
    )
    assert disguised_zip.status_code == 201, disguised_zip.text
    assert disguised_zip.json()["detected_mime"] == "application/zip"

    fake_zip = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("data.zip", PNG_BYTES, "application/zip")},
        headers=headers,
    )
    assert fake_zip.status_code == 422, fake_zip.text
    assert fake_zip.json()["error"]["details"]["detected_mime"] != "application/zip"


def test_artifact_deletion_removes_bytes_and_is_org_scoped(client: TestClient):
    owner = register(client, "owner-a@example.com", "Org A")
    owner_headers = auth_headers(owner["token"])
    project = client.post("/api/v1/projects", json={"name": "A"}, headers=owner_headers).json()
    upload = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", PY_ONLY_ZIP, "application/zip")},
        headers=owner_headers,
    )
    assert upload.status_code == 201, upload.text
    artifact = upload.json()

    storage_root = Path(get_settings().storage_root)
    stored_files = list(storage_root.rglob("demo.zip"))
    assert stored_files, "el artefacto debía almacenarse en disco"

    # IDOR: otra organización no puede borrar el artefacto.
    outsider = register(client, "owner-b@example.com", "Org B")
    outsider_headers = auth_headers(outsider["token"])
    forbidden = client.delete(
        f"/api/v1/projects/{project['id']}/artifacts/{artifact['id']}", headers=outsider_headers
    )
    assert forbidden.status_code == 404

    deleted = client.delete(
        f"/api/v1/projects/{project['id']}/artifacts/{artifact['id']}", headers=owner_headers
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["validation_state"] == "REJECTED"
    assert not stored_files[0].exists(), "los bytes debían eliminarse del almacenamiento"

    remaining = client.get(f"/api/v1/projects/{project['id']}/artifacts", headers=owner_headers)
    assert remaining.json() == []


def test_retention_purge_removes_expired_artifacts(client: TestClient):
    from app.db import repositories as repo
    from app.db.session import get_database
    from app.services.analysis_service import purge_expired_artifacts

    session = register(client, "retention@example.com", "Retention Org")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "R"}, headers=headers).json()
    upload = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", PY_ONLY_ZIP, "application/zip")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text

    organizations = client.get("/api/v1/organizations", headers=headers).json()
    organization_id = organizations[0]["id"]

    conn = get_database().connect()
    try:
        settings = Settings(workspace_retention_seconds=1)
        future = datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()
        purged = purge_expired_artifacts(conn, settings, now=future)
        conn.commit()
        assert purged == [upload.json()["id"]]
        assert repo.list_artifacts(conn, project["id"], organization_id) == []
    finally:
        conn.close()


def test_cancellation_is_idempotent(client: TestClient):
    session = register(client, "cancel@example.com", "Cancel Org")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "C"}, headers=headers).json()
    upload = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", PY_ONLY_ZIP, "application/zip")},
        headers=headers,
    ).json()
    started = client.post(
        f"/api/v1/projects/{project['id']}/analyses",
        json={"artifact_id": upload["id"]},
        headers=headers,
    )
    assert started.status_code == 202, started.text
    analysis_id = started.json()["id"]

    first = client.post(f"/api/v1/analyses/{analysis_id}/cancel", headers=headers)
    second = client.post(f"/api/v1/analyses/{analysis_id}/cancel", headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["status"] in {"CANCELLED", "COMPLETED", "COMPLETED_WITH_LIMITATIONS"}


def test_analysis_and_migration_are_org_scoped(client: TestClient):
    owner = register(client, "scoped-owner@example.com", "Scoped A")
    owner_headers = auth_headers(owner["token"])
    project = client.post("/api/v1/projects", json={"name": "S"}, headers=owner_headers).json()
    upload = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", PY_ONLY_ZIP, "application/zip")},
        headers=owner_headers,
    ).json()
    analysis_id = client.post(
        f"/api/v1/projects/{project['id']}/analyses",
        json={"artifact_id": upload["id"]},
        headers=owner_headers,
    ).json()["id"]

    outsider = register(client, "scoped-outsider@example.com", "Scoped B")
    outsider_headers = auth_headers(outsider["token"])

    assert client.get(f"/api/v1/analyses/{analysis_id}", headers=outsider_headers).status_code == 404
    assert client.get(f"/api/v1/analyses/{analysis_id}/findings", headers=outsider_headers).status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}", headers=outsider_headers).status_code == 404
    assert (
        client.post(
            f"/api/v1/analyses/{analysis_id}/change-sets",
            json={
                "reason": "motivo",
                "produced_by_rule": "regla",
                "edits": [{"path": "src/app.py", "new_content": "y = 1\n"}],
            },
            headers=outsider_headers,
        ).status_code
        == 404
    )
