"""Fixtures de prueba. Configura un entorno aislado por test (§19)."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


def make_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def isolated_execution_profile(monkeypatch):
    """§14.1: perfil de ejecución de la suite de pruebas.

    El valor por defecto en producción sigue siendo ``STATIC_ANALYSIS`` (no se
    ejecuta código del proyecto). La suite sí necesita ejecutar el código de
    prueba, así que el perfil se habilita **de forma explícita** en el entorno
    de pruebas en lugar de relajar el default de la aplicación.
    """
    monkeypatch.setenv("SIREP_EXECUTION_PROFILE", "ISOLATED_TEST_EXECUTION")

    from app.core.config import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SIREP_DATABASE_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("SIREP_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("SIREP_ENV", "test")
    monkeypatch.setenv("SIREP_SECRET_KEY", "test-key")

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
    with TestClient(app) as test_client:
        import logging

        logging.getLogger().setLevel(logging.WARNING)
        yield test_client

    reset_job_runner()
    reset_database()
    reset_settings_cache()
    reset_rate_limiter()


def register(client: TestClient, email: str, organization: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "supersecret123",
            "display_name": email.split("@")[0],
            "organization_name": organization,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(token: str, organization_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if organization_id:
        headers["X-Organization-Id"] = organization_id
    return headers
