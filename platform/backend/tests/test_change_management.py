"""Pruebas de gestión de cambios (§15).

Cubre la lógica pura (clasificación, diffs, rutas seguras) y el ciclo de vida
completo por API: PROPOSED → APPROVED → APPLIED → VALIDATED → ROLLED_BACK,
con verificación de hashes e integridad de archivos en disco.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ValidationAppError
from app.engines.change_management.change_engine import (
    classify_change,
    looks_like_test,
    safe_relative_path,
)
from tests.conftest import auth_headers, make_zip, register

SAMPLE_ZIP = make_zip(
    {
        "src/app.py": "import os\nKEY = os.getenv('GEMINI_API_KEY')\ndef main():\n    return KEY\n",
        "src/helper.py": "def helper():\n    return 1\n",
        "tests/test_smoke.py": "def test_smoke():\n    assert 1 == 1\n",
        "package.json": '{"name":"demo","dependencies":{"@google/generative-ai":"^0.21.0"}}',
    }
)

ORIGINAL_APP = "import os\nKEY = os.getenv('GEMINI_API_KEY')\ndef main():\n    return KEY\n"


# --------------------------------------------------------------------------- #
# Lógica pura
# --------------------------------------------------------------------------- #
def test_classify_added_modified_deleted():
    added = classify_change("a.py", None, b"x = 1\n")
    assert added is not None and added.change_type == "ADDED"
    assert added.base_sha256 is None and added.new_sha256 is not None

    modified = classify_change("a.py", b"x = 1\n", b"x = 2\n")
    assert modified is not None and modified.change_type == "MODIFIED"
    assert "+x = 2" in modified.unified_diff

    deleted = classify_change("a.py", b"x = 1\n", None)
    assert deleted is not None and deleted.change_type == "DELETED"
    assert deleted.new_sha256 is None


def test_classify_returns_none_without_effective_change():
    assert classify_change("a.py", b"x = 1\n", b"x = 1\n") is None
    with pytest.raises(ValidationAppError):
        classify_change("a.py", None, None)


def test_safe_relative_path_rejects_escapes():
    assert safe_relative_path("src/./app.py") == "src/app.py"
    for bad in ["../secret", "/etc/passwd", "a/../../b", "", "~/x"]:
        with pytest.raises(ValidationAppError):
            safe_relative_path(bad)


def test_looks_like_test_detection():
    assert looks_like_test("tests/test_x.py")
    assert looks_like_test("src/foo.test.ts")
    assert not looks_like_test("src/app.py")


# --------------------------------------------------------------------------- #
# Ciclo de vida por API
# --------------------------------------------------------------------------- #
def _setup_analysis(client: TestClient) -> tuple[dict, str]:
    session = register(client, "owner@example.com", "Acme")
    headers = auth_headers(session["token"])
    org = client.get("/api/v1/organizations", headers=headers)
    assert org.status_code == 200, org.text
    org_id = org.json()[0]["id"]
    headers = auth_headers(session["token"], org_id)

    project = client.post("/api/v1/projects", json={"name": "Demo"}, headers=headers)
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    upload = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    artifact_id = upload.json()["id"]
    started = client.post(
        f"/api/v1/projects/{project_id}/analyses",
        json={"artifact_id": artifact_id},
        headers=headers,
    )
    assert started.status_code == 202, started.text
    analysis_id = started.json()["id"]

    import time

    deadline = time.time() + 60
    while time.time() < deadline:
        summary = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()
        if summary["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}:
            return headers, analysis_id
        time.sleep(0.1)
    raise AssertionError("análisis no finalizó")


def _create(client: TestClient, headers: dict, analysis_id: str, edits: list[dict]) -> dict:
    response = client.post(
        f"/api/v1/analyses/{analysis_id}/change-sets",
        json={"reason": "Migrar a NIM", "produced_by_rule": "R-14", "edits": edits},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_change_set_full_lifecycle(client: TestClient):
    headers, analysis_id = _setup_analysis(client)
    new_content = ORIGINAL_APP.replace("GEMINI_API_KEY", "NIM_API_KEY")
    change = _create(
        client,
        headers,
        analysis_id,
        [
            {"path": "src/app.py", "new_content": new_content},
            {"path": "src/helper.py", "new_content": None},
            {"path": "src/new_module.py", "new_content": "VALUE = 42\n"},
        ],
    )
    assert change["status"] == "PROPOSED"
    assert change["reversible"] is True
    assert change["base_artifact_sha256"] and len(change["base_artifact_sha256"]) == 64
    types = {f["path"]: f["change_type"] for f in change["files"]}
    assert types == {
        "src/app.py": "MODIFIED",
        "src/helper.py": "DELETED",
        "src/new_module.py": "ADDED",
    }
    assert all(f["unified_diff"] for f in change["files"])

    workspace = Path(change["workspace_path"])
    assert (workspace / "src/app.py").read_text() == ORIGINAL_APP

    # Aplicar sin aprobar debe fallar.
    premature = client.post(f"/api/v1/change-sets/{change['id']}/apply", headers=headers)
    assert premature.status_code == 409, premature.text

    approved = client.post(
        f"/api/v1/change-sets/{change['id']}/approve",
        json={"decision": "approved", "comment": "ok"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert len(approved.json()["approvals"]) == 1

    applied = client.post(f"/api/v1/change-sets/{change['id']}/apply", headers=headers)
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "APPLIED"

    assert (workspace / "src/app.py").read_text() == new_content
    assert not (workspace / "src/helper.py").exists()
    assert (workspace / "src/new_module.py").read_text() == "VALUE = 42\n"

    validated = client.post(f"/api/v1/change-sets/{change['id']}/validate", headers=headers)
    assert validated.status_code == 200, validated.text
    body = validated.json()
    assert body["status"] == "VALIDATED"
    assert body["validation_result"]["files_analyzed"] >= 1

    rolled = client.post(f"/api/v1/change-sets/{change['id']}/rollback", headers=headers)
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["status"] == "ROLLED_BACK"

    assert (workspace / "src/app.py").read_text() == ORIGINAL_APP
    assert (workspace / "src/helper.py").read_text() == "def helper():\n    return 1\n"
    assert not (workspace / "src/new_module.py").exists()


def test_apply_is_blocked_when_workspace_changed(client: TestClient):
    headers, analysis_id = _setup_analysis(client)
    change = _create(
        client, headers, analysis_id, [{"path": "src/app.py", "new_content": "x = 1\n"}]
    )
    client.post(
        f"/api/v1/change-sets/{change['id']}/approve",
        json={"decision": "approved"},
        headers=headers,
    )
    # Simula una modificación externa que altera el hash base registrado.
    (Path(change["workspace_path"]) / "src/app.py").write_text("tampered\n")

    response = client.post(f"/api/v1/change-sets/{change['id']}/apply", headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "change_conflict"


def test_rejected_change_cannot_be_applied(client: TestClient):
    headers, analysis_id = _setup_analysis(client)
    change = _create(
        client, headers, analysis_id, [{"path": "src/app.py", "new_content": "x = 1\n"}]
    )
    rejected = client.post(
        f"/api/v1/change-sets/{change['id']}/approve",
        json={"decision": "rejected", "comment": "no"},
        headers=headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert client.post(f"/api/v1/change-sets/{change['id']}/apply", headers=headers).status_code == 409


def test_change_set_requires_effective_diff(client: TestClient):
    headers, analysis_id = _setup_analysis(client)
    response = client.post(
        f"/api/v1/analyses/{analysis_id}/change-sets",
        json={
            "reason": "sin cambios",
            "produced_by_rule": "R-00",
            "edits": [{"path": "src/app.py", "new_content": ORIGINAL_APP}],
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_change_set_listed_for_analysis(client: TestClient):
    headers, analysis_id = _setup_analysis(client)
    _create(client, headers, analysis_id, [{"path": "src/app.py", "new_content": "y = 2\n"}])
    listing = client.get(f"/api/v1/analyses/{analysis_id}/change-sets", headers=headers)
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 1
