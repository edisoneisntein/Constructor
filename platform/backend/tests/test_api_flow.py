"""Flujo vertical E2E por API (§20) y pruebas de seguridad (§19.3)."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, make_zip, register

SAMPLE_ZIP = make_zip(
    {
        "src/app.py": "import os\nKEY = os.getenv('GEMINI_API_KEY')\ndef main():\n    return KEY\n",
        "src/index.js": "import { GoogleGenerativeAI } from '@google/generative-ai';\nexport const x = 1;\n",
        "package.json": '{"name":"demo","dependencies":{"@google/generative-ai":"^0.21.0"}}',
    }
)


def _org_id(client: TestClient, headers: dict) -> str:
    response = client.get("/api/v1/organizations", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()[0]["id"]


def _wait_for_analysis(client: TestClient, headers: dict, analysis_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        status = payload["job"]["status"]
        if status in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS", "FAILED", "CANCELLED"}:
            return payload
        time.sleep(0.1)
    raise AssertionError("El análisis no finalizó dentro del tiempo esperado.")


def test_full_vertical_flow(client: TestClient):
    session = register(client, "owner@example.com", "Acme")
    headers = auth_headers(session["token"])
    org_id = _org_id(client, headers)

    created = client.post("/api/v1/projects", json={"name": "Demo"}, headers=headers)
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    upload = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    artifact = upload.json()
    assert artifact["detected_mime"] == "application/zip"
    assert len(artifact["sha256"]) == 64

    started = client.post(
        f"/api/v1/projects/{project_id}/analyses",
        json={"artifact_id": artifact["id"]},
        headers=headers,
    )
    assert started.status_code == 202, started.text
    analysis_id = started.json()["id"]

    summary = _wait_for_analysis(client, headers, analysis_id)
    assert summary["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}
    assert summary["finding_count"] >= 1
    assert summary["node_count"] >= 1
    assert "python" in summary["languages"]

    findings = client.get(f"/api/v1/analyses/{analysis_id}/findings", headers=headers)
    assert findings.status_code == 200, findings.text
    items = findings.json()["items"]
    categories = {item["category"] for item in items}
    assert "LANGUAGE" in categories
    ai_findings = [item for item in items if item["category"] == "AI_INTEGRATION"]
    assert ai_findings
    assert any(item["evidence_level"] == "DIRECT_EVIDENCE" for item in ai_findings)
    # Relación inferida: variable de entorno que configura el SDK importado (§7).
    assert any(item["evidence_level"] == "STATIC_INFERENCE" for item in ai_findings)

    graph = client.get(f"/api/v1/analyses/{analysis_id}/architecture", headers=headers)
    assert graph.status_code == 200, graph.text
    graph_payload = graph.json()
    assert graph_payload["node_count"] >= 1
    assert graph_payload["confirmed_edge_count"] >= 1

    export_json = client.post(f"/api/v1/analyses/{analysis_id}/export?fmt=json", headers=headers)
    assert export_json.status_code == 200
    assert "findings" in export_json.json()

    export_md = client.post(f"/api/v1/analyses/{analysis_id}/export?fmt=markdown", headers=headers)
    assert export_md.status_code == 200
    assert "# Informe de análisis" in export_md.text

    # Encabezado de organización idempotente.
    assert org_id  # se obtuvo correctamente


def test_graph_navigation_endpoints(client: TestClient):
    session = register(client, "nav@example.com", "NavOrg")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "Nav"}, headers=headers).json()
    artifact = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    ).json()
    started = client.post(
        f"/api/v1/projects/{project['id']}/analyses",
        json={"artifact_id": artifact["id"]},
        headers=headers,
    ).json()
    analysis_id = started["id"]
    _wait_for_analysis(client, headers, analysis_id)

    graph = client.get(f"/api/v1/analyses/{analysis_id}/architecture", headers=headers).json()
    assert graph["node_type_counts"].get("integration", 0) >= 1

    filtered = client.get(
        f"/api/v1/analyses/{analysis_id}/architecture?node_type=integration", headers=headers
    ).json()
    assert filtered["node_count"] >= 1
    assert all(node["node_type"] == "integration" for node in filtered["nodes"])

    detail = client.get(
        f"/api/v1/analyses/{analysis_id}/architecture/node?node_id=integ::google_gemini", headers=headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["node"]["node_type"] == "integration"

    subgraph = client.get(
        f"/api/v1/analyses/{analysis_id}/architecture/subgraph?node_id=integ::google_gemini&depth=2",
        headers=headers,
    )
    assert subgraph.status_code == 200, subgraph.text
    payload = subgraph.json()
    assert payload["root_node_id"] == "integ::google_gemini"
    assert any(node["node_type"] == "env_var" for node in payload["nodes"])

    missing = client.get(
        f"/api/v1/analyses/{analysis_id}/architecture/node?node_id=does-not-exist", headers=headers
    )
    assert missing.status_code == 404


def test_dangerous_upload_is_rejected(client: TestClient):
    session = register(client, "owner2@example.com", "Beta")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "P"}, headers=headers).json()
    malicious = make_zip({"../evil.py": "print(1)\n"})
    response = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("evil.zip", malicious, "application/zip")},
        headers=headers,
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "unsafe_archive"


def test_cross_organization_access_is_denied(client: TestClient):
    owner = register(client, "a@example.com", "OrgA")
    headers_a = auth_headers(owner["token"])
    project = client.post("/api/v1/projects", json={"name": "Secret"}, headers=headers_a).json()

    intruder = register(client, "b@example.com", "OrgB")
    headers_b = auth_headers(intruder["token"])
    response = client.get(f"/api/v1/projects/{project['id']}", headers=headers_b)
    assert response.status_code == 404, response.text


def test_viewer_role_cannot_create_project(client: TestClient):
    owner = register(client, "owner3@example.com", "Gamma")
    headers_owner = auth_headers(owner["token"])
    org_id = _org_id(client, headers_owner)
    viewer = register(client, "viewer@example.com", "Delta")
    headers_viewer = auth_headers(viewer["token"], org_id)

    # Añade al usuario viewer como miembro 'viewer' de la organización del owner.
    from app.db import repositories as repo
    from app.db.session import get_database
    from app.core.ids import utcnow_iso

    connection = get_database().connect()
    repo.add_membership(
        connection,
        organization_id=org_id,
        user_id=viewer["user"]["id"],
        role="viewer",
        created_at=utcnow_iso(),
    )
    connection.commit()
    connection.close()

    response = client.post("/api/v1/projects", json={"name": "Nope"}, headers=headers_viewer)
    assert response.status_code == 403, response.text


def test_unauthenticated_request_is_rejected(client: TestClient):
    response = client.get("/api/v1/projects")
    assert response.status_code == 401, response.text


def test_rejects_unsupported_artifact_type(client: TestClient):
    session = register(client, "owner4@example.com", "Epsilon")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "P"}, headers=headers).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 422, response.text


def test_multiple_analyses_same_content_do_not_collide(client: TestClient):
    """Regresión: ids de nodo deterministas requieren PK (analysis_id, id).

    Dos análisis equivalentes en la misma base de datos deben persistir su grafo
    sin chocar por la clave primaria de ``architecture_nodes``.
    """

    session = register(client, "owner5@example.com", "Zeta")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "Repetido"}, headers=headers).json()
    upload = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    artifact_id = upload.json()["id"]

    completed = []
    for _ in range(2):
        started = client.post(
            f"/api/v1/projects/{project['id']}/analyses",
            json={"artifact_id": artifact_id},
            headers=headers,
        )
        assert started.status_code == 202, started.text
        summary = _wait_for_analysis(client, headers, started.json()["id"])
        assert summary["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}, summary
        completed.append(summary)

    for summary in completed:
        assert summary["node_count"] >= 1
        assert summary["finding_count"] >= 1
