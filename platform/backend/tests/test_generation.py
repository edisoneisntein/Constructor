"""Generación/reparación de código asistida por NIM (§10), con verificación.

Las pruebas usan un transporte HTTP falso (``httpx.MockTransport``) para no
depender de la red. La prueba en vivo se ejecuta solo con ``SIREP_NIM_LIVE_TEST=1``.
"""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.engines.features import nim_codegen
from app.engines.migration.nim_client import NimClient
from tests.conftest import auth_headers, make_zip, register

SAMPLE_ZIP = make_zip(
    {
        "src/app.py": "def main():\n    return 1\n",
        "README.md": "# Demo\n",
    }
)

VALID_PYTHON = "def main():\n    return 2\n"


def _nim_transport(content: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "model": "nvidia/nemotron-3-super-120b-a12b",
                    "choices": [{"message": {"role": "assistant", "content": content}}],
                    "usage": {"total_tokens": 42},
                },
            )
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def _response_with_file(path: str, content: str) -> str:
    return json.dumps({"summary": "cambio", "notes": "ok", "files": [{"path": path, "content": content}]})


def _patch_nim(monkeypatch, content: str | None):
    from app.services import generation_service

    def fake_build(settings, *, transport=None):
        api_key = "secret" if content is not None else None
        return NimClient(
            base_url="https://nim.test/v1",
            api_key=api_key,
            transport=_nim_transport(content) if content is not None else transport,
        )

    monkeypatch.setattr(generation_service, "build_nim_client", fake_build)


def _setup_analysis(client: TestClient) -> tuple[dict, str]:
    session = register(client, "dev@example.com", "Acme")
    headers = auth_headers(session["token"])
    created = client.post("/api/v1/projects", json={"name": "Demo"}, headers=headers)
    project_id = created.json()["id"]
    upload = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        files={"file": ("demo.zip", SAMPLE_ZIP, "application/zip")},
        headers=headers,
    )
    artifact_id = upload.json()["id"]
    started = client.post(
        f"/api/v1/projects/{project_id}/analyses", json={"artifact_id": artifact_id}, headers=headers
    )
    analysis_id = started.json()["id"]
    deadline = time.time() + 60
    while time.time() < deadline:
        payload = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()
        if payload["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.1)
    return headers, analysis_id


def test_generation_creates_verified_change_set(client: TestClient, monkeypatch):
    headers, analysis_id = _setup_analysis(client)
    _patch_nim(monkeypatch, _response_with_file("src/app.py", VALID_PYTHON))

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/generations",
        json={
            "instruction": "Cambia el valor de retorno a 2.",
            "target_path": "src/app.py",
            "mode": "feature",
            "ai_consent": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mode"] == "feature"
    assert body["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert body["change_set"]["status"] == "PROPOSED"
    assert body["change_set"]["produced_by_rule"] == "NIM-GENERATE"
    assert len(body["change_set"]["files"]) == 1
    verification = body["verification"][0]
    assert verification["path"] == "src/app.py"
    assert verification["language"] == "python"
    assert verification["syntax_checked"] is True
    assert verification["syntax_ok"] is True
    assert verification["additions"] >= 1
    assert "+    return 2" in body["change_set"]["files"][0]["unified_diff"]


def test_generation_rejects_invalid_syntax(client: TestClient, monkeypatch):
    headers, analysis_id = _setup_analysis(client)
    _patch_nim(monkeypatch, _response_with_file("src/app.py", "def main(:\n    return 2\n"))

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/generations",
        json={"instruction": "rompe", "target_path": "src/app.py", "ai_consent": True},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "generation_verification_failed"

    listed = client.get(f"/api/v1/analyses/{analysis_id}/change-sets", headers=headers).json()
    assert listed == []


def test_generation_rejects_unsafe_path(client: TestClient, monkeypatch):
    headers, analysis_id = _setup_analysis(client)
    _patch_nim(monkeypatch, _response_with_file("../../etc/passwd", "x\n"))

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/generations",
        json={"instruction": "escapa", "ai_consent": True},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "generation_verification_failed"


def test_generation_requires_consent(client: TestClient, monkeypatch):
    headers, analysis_id = _setup_analysis(client)
    _patch_nim(monkeypatch, _response_with_file("src/app.py", VALID_PYTHON))

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/generations",
        json={"instruction": "sin consentimiento", "target_path": "src/app.py"},
        headers=headers,
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ai_consent_required"


def test_generation_requires_configured_provider(client: TestClient, monkeypatch):
    headers, analysis_id = _setup_analysis(client)
    _patch_nim(monkeypatch, None)

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/generations",
        json={"instruction": "x", "target_path": "src/app.py", "ai_consent": True},
        headers=headers,
    )
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "capability_unavailable"


def test_repair_mode_includes_findings(client: TestClient, monkeypatch):
    headers, analysis_id = _setup_analysis(client)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "model": "nvidia/nemotron-3-super-120b-a12b",
                "choices": [
                    {"message": {"role": "assistant", "content": _response_with_file("src/app.py", VALID_PYTHON)}}
                ],
                "usage": {},
            },
        )

    from app.services import generation_service

    monkeypatch.setattr(
        generation_service,
        "build_nim_client",
        lambda settings, *, transport=None: NimClient(
            base_url="https://nim.test/v1", api_key="secret", transport=httpx.MockTransport(handler)
        ),
    )

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/generations",
        json={"instruction": "Corrige hallazgos.", "target_path": "src/app.py", "mode": "repair", "ai_consent": True},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    user_message = captured["body"]["messages"][1]["content"]
    assert "Archivo objetivo: src/app.py" in user_message


def test_codegen_parsing_and_verification_units():
    files, summary, notes, errors = nim_codegen.parse_response(
        "```json\n" + _response_with_file("a.py", "x = 1\n") + "\n```"
    )
    assert errors == []
    assert summary and notes
    assert files[0].syntax_checked and files[0].syntax_ok

    _, _, _, errors = nim_codegen.parse_response(_response_with_file("a.py", "def (:\n"))
    assert errors and "sintaxis" in errors[0].lower()

    with pytest.raises(Exception):
        nim_codegen.extract_json_object("no hay json aquí")

    request = nim_codegen.CodegenRequest(
        instruction="arregla",
        mode="repair",
        target_path="a.py",
        findings=[{"severity": "HIGH", "category": "SECURITY", "message": "secreto", "file_path": "a.py"}],
    )
    messages = nim_codegen.build_messages(request)
    assert messages[0]["role"] == "system"
    assert "Hallazgos a reparar" in messages[1]["content"]


@pytest.mark.skipif(
    os.environ.get("SIREP_NIM_LIVE_TEST") != "1",
    reason="Prueba en vivo: requiere SIREP_NIM_LIVE_TEST=1 y SIREP_NIM_API_KEY.",
)
def test_live_generation(client: TestClient):
    headers, analysis_id = _setup_analysis(client)
    response = client.post(
        f"/api/v1/analyses/{analysis_id}/generations",
        json={
            "instruction": "Añade a src/app.py una función `def greeting(name): return f'Hola {name}'`.",
            "target_path": "src/app.py",
            "mode": "feature",
            "ai_consent": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["verification"][0]["syntax_ok"] is True
