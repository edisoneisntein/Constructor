"""Pruebas de endurecimiento derivadas de la auditoría (2026-10-26).

Cubre los cambios de seguridad y rendimiento aplicados tras la auditoría:

* contención del workspace en la generación (path traversal);
* guard de salida (SSRF) en el cliente NIM;
* fallo en cerrado del perfil de ejecución de alto riesgo;
* propiedad del trabajo (evita que un trabajador sin propiedad escriba estado);
* extracción de cadenas con memoria acotada y resultado idéntico;
* conteos agregados del grafo para el resumen de análisis.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnsafeArchiveError
from app.core.execution_profiles import DEFAULT_PROFILE, ExecutionProfile, active_profile
from app.db import repositories as repo
from app.engines.binary_analysis.utils import StringLimits, extract_strings
from app.engines.migration.nim_client import NimClient
from app.services.generation_service import _build_context
from tests.conftest import auth_headers, make_zip, register

SAMPLE_ZIP = make_zip({"src/app.py": "def main():\n    return 1\n"})


@pytest.fixture()
def external_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
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


def _write_zip(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


# --------------------------------------------------------------------------- #
# Contención del workspace en la generación
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("target_path", ["../outside.txt", "/etc/hosts", "src/../../escape.py"])
def test_generation_context_rejects_paths_outside_workspace(tmp_path, target_path):
    artifact_path = _write_zip(tmp_path / "artifact.zip", {"src/app.py": "x = 1\n"})
    settings = get_settings()
    with pytest.raises(UnsafeArchiveError):
        _build_context(
            settings,
            artifact={"storage_path": str(artifact_path)},
            target_path=target_path,
            context_root=tmp_path / "context",
        )


def test_generation_context_reads_valid_target(tmp_path):
    artifact_path = _write_zip(tmp_path / "artifact.zip", {"src/app.py": "x = 1\n"})
    settings = get_settings()
    index, target_content, context = _build_context(
        settings,
        artifact={"storage_path": str(artifact_path)},
        target_path="src/app.py",
        context_root=tmp_path / "context",
    )
    assert target_content is not None
    assert "x = 1" in target_content
    assert "src/app.py" not in index
    assert context == []


# --------------------------------------------------------------------------- #
# Guard de salida (SSRF) en el cliente NIM
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "base_url",
    ["http://127.0.0.1:11434/v1", "http://localhost:8080/v1", "http://169.254.169.254/v1"],
)
def test_nim_client_rejects_internal_endpoints(base_url):
    with pytest.raises(ForbiddenError):
        NimClient(base_url=base_url, api_key="secret")


def test_nim_client_accepts_public_endpoint():
    client = NimClient(base_url="https://integrate.api.nvidia.com/v1/", api_key="secret")
    assert client.base_url == "https://integrate.api.nvidia.com/v1"


def test_nim_client_requires_allowed_host_when_allowlist_is_set():
    with pytest.raises(ForbiddenError):
        NimClient(
            base_url="https://other.test/v1",
            api_key="secret",
            outbound_allowed_hosts=["integrate.api.nvidia.com"],
        )


# --------------------------------------------------------------------------- #
# Perfil de ejecución: fallo en cerrado
# --------------------------------------------------------------------------- #


def test_high_risk_profile_degrades_without_explicit_flag():
    settings = Settings(execution_profile="HIGH_RISK_DYNAMIC_ANALYSIS", execution_allow_high_risk=False)
    assert active_profile(settings) is DEFAULT_PROFILE


def test_high_risk_profile_is_effective_with_explicit_flag():
    settings = Settings(execution_profile="HIGH_RISK_DYNAMIC_ANALYSIS", execution_allow_high_risk=True)
    assert active_profile(settings) is ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS


# --------------------------------------------------------------------------- #
# Propiedad del trabajo
# --------------------------------------------------------------------------- #


def _queued_job(client: TestClient) -> tuple[str, str, str]:
    session = register(client, "owner@example.com", "Dueños")
    headers = auth_headers(session["token"])
    organizations = client.get("/api/v1/organizations", headers=headers).json()
    organization_id = organizations[0]["id"]
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
    assert started.status_code in (201, 202), started.text
    return started.json()["id"], organization_id, project["id"]


def test_update_job_respects_worker_ownership(external_client):
    from app.core.ids import utcnow_iso
    from app.db.session import get_database

    job_id, organization_id, _ = _queued_job(external_client)
    conn = get_database().connect()
    try:
        claimed = repo.claim_next_job(conn, worker_id="wrk_a", now=utcnow_iso())
        assert claimed is not None and claimed["id"] == job_id

        assert repo.heartbeat_job(conn, job_id, worker_id="wrk_b", now=utcnow_iso()) is False
        assert repo.heartbeat_job(conn, job_id, worker_id="wrk_a", now=utcnow_iso()) is True

        assert repo.update_job(conn, job_id, status="COMPLETED", claimed_by="wrk_b") is False
        current = repo.get_job(conn, job_id, organization_id)
        assert current is not None and current["status"] == "RUNNING"

        assert repo.update_job(conn, job_id, status="COMPLETED", claimed_by="wrk_a") is True
        current = repo.get_job(conn, job_id, organization_id)
        assert current is not None and current["status"] == "COMPLETED"
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Extracción de cadenas con memoria acotada
# --------------------------------------------------------------------------- #


def _reference_extract_strings(data: bytes, limits: StringLimits) -> list[str]:
    printable = set(range(0x20, 0x7F))
    ascii_strings: list[str] = []
    current: list[str] = []
    for byte in data:
        if byte in printable:
            current.append(chr(byte))
        else:
            if len(current) >= limits.min_length:
                ascii_strings.append("".join(current)[: limits.max_length])
            current = []
    if len(current) >= limits.min_length:
        ascii_strings.append("".join(current)[: limits.max_length])

    utf16: list[str] = []
    current16: list[str] = []
    for index in range(0, len(data) - 1, 2):
        low, high = data[index], data[index + 1]
        if high == 0 and low in printable:
            current16.append(chr(low))
        else:
            if len(current16) >= limits.min_length:
                utf16.append("".join(current16)[: limits.max_length])
            current16 = []
    if len(current16) >= limits.min_length:
        utf16.append("".join(current16)[: limits.max_length])

    seen: set[str] = set()
    unique: list[str] = []
    for value in ascii_strings + utf16:
        if value not in seen:
            seen.add(value)
            unique.append(value)
        if len(unique) >= limits.max_strings:
            break
    return unique


def test_extract_strings_matches_reference_implementation():
    limits = StringLimits(min_length=5, max_strings=200, max_length=32)
    samples = [
        b"hello world\x00another string here\x00",
        b"https://example.com/path\x00\x01\x02\x03\x04",
        b"A" * 4096 + b"\x00" + b"B" * 10,
        b"\x00".join(f"value-{index}".encode() for index in range(400)),
        bytes(range(256)) * 4,
        b"short\x00" + "hola".encode("utf-16-le") + b"\x00",
    ]
    for sample in samples:
        unique, relevant = extract_strings(sample, limits)
        assert unique == _reference_extract_strings(sample, limits)
        assert set(relevant).issubset(set(unique))


def test_extract_strings_caps_output_on_noisy_input():
    limits = StringLimits(min_length=5, max_strings=200, max_length=32)
    noisy = b"".join(f"unique-string-{index:06d}".encode() + b"\x00" for index in range(5000))
    unique, relevant = extract_strings(noisy, limits)
    assert len(unique) == limits.max_strings
    assert all(len(value) <= limits.max_length for value in unique)
    assert all(isinstance(value, str) for value in relevant)


# --------------------------------------------------------------------------- #
# Conteos agregados del grafo
# --------------------------------------------------------------------------- #


def test_graph_counts_match_persisted_rows(external_client):
    from app.db.session import get_database

    job_id, organization_id, _ = _queued_job(external_client)
    conn = get_database().connect()
    try:
        now = "2026-10-26T00:00:00+00:00"
        repo.insert_nodes(
            conn,
            [
                {
                    "id": "n1",
                    "analysis_id": job_id,
                    "project_id": "p1",
                    "organization_id": organization_id,
                    "node_type": "file",
                    "label": "a.py",
                    "path": "a.py",
                    "language": "python",
                    "evidence_level": "observed",
                    "detection_method": "ast",
                    "metadata": None,
                    "created_at": now,
                }
            ],
        )
        repo.insert_edges(
            conn,
            [
                {
                    "id": "e1",
                    "analysis_id": job_id,
                    "project_id": "p1",
                    "organization_id": organization_id,
                    "source_node_id": "n1",
                    "target_node_id": None,
                    "target_ref": "n1",
                    "edge_type": "references",
                    "evidence_level": "observed",
                    "detection_method": "ast",
                    "metadata": None,
                    "created_at": now,
                }
            ],
        )
        assert repo.count_nodes(conn, job_id, organization_id) == 1
        assert repo.count_edges(conn, job_id, organization_id) == 1
        assert repo.count_dependencies(conn, job_id, organization_id) == 0
    finally:
        conn.close()
