"""Eliminación de proyectos (§14.6): datos, almacenamiento y control de acceso."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, make_zip, register

SAMPLE_ZIP = make_zip({"src/app.py": "import os\nKEY = os.getenv('API_KEY')\n"})


def _org_id(client: TestClient, headers: dict) -> str:
    response = client.get("/api/v1/organizations", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()[0]["id"]


def _create_project_with_artifact(client: TestClient, headers: dict, name: str) -> tuple[dict, dict]:
    project = client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert project.status_code == 201, project.text
    artifact = client.post(
        f"/api/v1/projects/{project.json()['id']}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    )
    assert artifact.status_code == 201, artifact.text
    return project.json(), artifact.json()


def test_delete_project_removes_database_rows_and_storage(client: TestClient):
    session = register(client, "delete@example.com", "DeleteOrg")
    headers = auth_headers(session["token"])
    project, artifact = _create_project_with_artifact(client, headers, "Efímero")
    keeper = client.post("/api/v1/projects", json={"name": "Conservar"}, headers=headers).json()

    from app.db import repositories as repo
    from app.db.session import get_database

    conn = get_database().connect()
    stored = repo.get_artifact(conn, artifact["id"], project["organization_id"])
    conn.close()
    artifact_path = Path(stored["storage_path"])
    assert artifact_path.is_file()

    deleted = client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["id"] == project["id"]

    remaining = client.get("/api/v1/projects", headers=headers)
    assert remaining.status_code == 200
    assert [item["id"] for item in remaining.json()] == [keeper["id"]]

    assert client.get(f"/api/v1/projects/{project['id']}", headers=headers).status_code == 404
    assert (
        client.get(f"/api/v1/projects/{project['id']}/analyses", headers=headers).status_code == 404
    )
    assert not artifact_path.exists()

    missing = client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
    assert missing.status_code == 404


def test_delete_project_is_scoped_to_the_organization(client: TestClient):
    owner = register(client, "owner-del@example.com", "OwnedOrg")
    headers_owner = auth_headers(owner["token"])
    project = client.post("/api/v1/projects", json={"name": "Privado"}, headers=headers_owner).json()

    intruder = register(client, "intruder-del@example.com", "OtherOrg")
    headers_intruder = auth_headers(intruder["token"])

    denied = client.delete(f"/api/v1/projects/{project['id']}", headers=headers_intruder)
    assert denied.status_code == 404, denied.text
    assert client.get(f"/api/v1/projects/{project['id']}", headers=headers_owner).status_code == 200


def test_viewer_cannot_delete_project(client: TestClient):
    owner = register(client, "owner-viewer-del@example.com", "ViewerDelOrg")
    headers_owner = auth_headers(owner["token"])
    org_id = _org_id(client, headers_owner)
    project = client.post("/api/v1/projects", json={"name": "Intacto"}, headers=headers_owner).json()

    viewer = register(client, "viewer-del@example.com", "ViewerDelOther")
    headers_viewer = auth_headers(viewer["token"], org_id)

    from app.core.ids import utcnow_iso
    from app.db import repositories as repo
    from app.db.session import get_database

    conn = get_database().connect()
    repo.add_membership(
        conn,
        organization_id=org_id,
        user_id=viewer["user"]["id"],
        role="viewer",
        created_at=utcnow_iso(),
    )
    conn.commit()
    conn.close()

    denied = client.delete(f"/api/v1/projects/{project['id']}", headers=headers_viewer)
    assert denied.status_code == 403, denied.text
    assert client.get(f"/api/v1/projects/{project['id']}", headers=headers_owner).status_code == 200


def test_delete_project_conflicts_with_active_analysis(client: TestClient):
    session = register(client, "active-del@example.com", "ActiveDelOrg")
    headers = auth_headers(session["token"])
    project, artifact = _create_project_with_artifact(client, headers, "En curso")

    from app.core.ids import utcnow_iso
    from app.db import repositories as repo
    from app.db.session import get_database

    conn = get_database().connect()
    job = repo.create_job(
        conn,
        project_id=project["id"],
        organization_id=project["organization_id"],
        artifact_id=artifact["id"],
        created_by=session["user"]["id"],
        status="QUEUED",
        created_at=utcnow_iso(),
    )
    conn.commit()

    conflict = client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "project_has_active_jobs"

    repo.update_job(conn, job["id"], status="CANCELLED", phase="cancelled", finished_at=utcnow_iso())
    conn.commit()
    conn.close()

    deleted = client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text
