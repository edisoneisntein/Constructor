"""Pruebas del motor de migración Gemini → NVIDIA NIM (§12, §19.5)."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engines.migration import planner
from app.engines.migration.gemini_detector import detect_gemini_operations
from app.engines.migration.nim_compat import assess_operations, matrix_summary
from tests.conftest import auth_headers, make_zip, register

PY_GEMINI = '''
import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-pro")
response = model.generate_content(
    "hola", tools=[], response_mime_type="application/json"
)
for chunk in model.generate_content_stream("hola"):
    pass
embedding = genai.embed_content(model="models/embedding-001", content="texto")
'''

PY_COMMENT_ONLY = """
# import google.generativeai as genai
# genai.configure(api_key="GEMINI_API_KEY")
# model.generate_content("no cuenta")
"""

JS_GEMINI = """
import { GoogleGenerativeAI } from "@google/generative-ai";
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
const model = genAI.getGenerativeModel({ model: "gemini-1.5-pro" });
const r = await model.generateContent("hola");
"""


def test_detects_python_gemini_operations(tmp_path):
    (tmp_path / "app.py").write_text(PY_GEMINI, encoding="utf-8")
    operations, _ = detect_gemini_operations(tmp_path)
    kinds = {operation.kind for operation in operations}
    assert {"sdk_import", "client_init", "generation", "streaming", "embedding", "env_var"} <= kinds
    assert "tool_calling" in kinds
    assert "structured_output" in kinds
    models = {operation.model for operation in operations if operation.model}
    assert "gemini-1.5-pro" in models


def test_comments_are_not_detected(tmp_path):
    (tmp_path / "comments.py").write_text(PY_COMMENT_ONLY, encoding="utf-8")
    operations, _ = detect_gemini_operations(tmp_path)
    assert operations == []


def test_detects_js_gemini_operations(tmp_path):
    (tmp_path / "index.ts").write_text(JS_GEMINI, encoding="utf-8")
    operations, _ = detect_gemini_operations(tmp_path)
    kinds = {operation.kind for operation in operations}
    assert {"sdk_import", "client_init", "generation", "env_var"} <= kinds


def test_compatibility_matrix_categories(tmp_path):
    (tmp_path / "app.py").write_text(PY_GEMINI, encoding="utf-8")
    operations, _ = detect_gemini_operations(tmp_path)
    assessments = assess_operations(operations, get_settings())
    by_kind = {assessment.operation_kind: assessment for assessment in assessments}
    assert by_kind["generation"].category == "COMPATIBLE_WITH_ADAPTER"
    assert by_kind["env_var"].category == "DIRECTLY_COMPATIBLE"
    assert by_kind["embedding"].category == "PARTIAL_COMPATIBILITY"
    assert by_kind["generation"].protocol_compatibility == "OPENAI_COMPATIBLE"
    assert "/v1/chat/completions" in by_kind["generation"].target_endpoint
    summary = matrix_summary(assessments)
    assert summary["COMPATIBLE_WITH_ADAPTER"] >= 1


def test_planner_produces_dependency_adapter_and_env_changes(tmp_path):
    (tmp_path / "app.py").write_text(PY_GEMINI, encoding="utf-8")
    requirements = "google-generativeai==0.8.3\n"
    (tmp_path / "requirements.txt").write_text(requirements, encoding="utf-8")
    (tmp_path / ".env.example").write_text("GEMINI_API_KEY=\n", encoding="utf-8")

    operations, limitations = detect_gemini_operations(tmp_path)
    settings = get_settings()
    assessments = assess_operations(operations, settings)
    file_contents = planner.load_file_contents(
        tmp_path, ["requirements.txt", ".env.example", "app.py"]
    )
    plan = planner.build_plan(
        operations=operations,
        limitations=limitations,
        settings=settings,
        assessments=assessments,
        dependencies=[{"ecosystem": "pypi", "name": "google-generativeai", "source_file": "requirements.txt"}],
        file_contents=file_contents,
    )
    changes = {change["change_id"]: change for change in plan["changes"]}
    assert "dep-py-remove" in changes
    assert "-google-generativeai==0.8.3" in changes["dep-py-remove"]["diff"]
    assert "adapter-py" in changes
    assert changes["adapter-py"]["path"] == planner.ADAPTER_PY_PATH
    assert "env-nim" in changes
    assert "call-rewrite-manual" in changes
    assert any("NO está verificada" in note for note in plan["limitations"])
    assert plan["sources"]


def _setup_analysis(client: TestClient) -> tuple[dict, str, str]:
    session = register(client, "owner@example.com", "Acme")
    headers = auth_headers(session["token"])
    org_id = client.get("/api/v1/organizations", headers=headers).json()[0]["id"]
    headers = auth_headers(session["token"], org_id)
    project = client.post("/api/v1/projects", json={"name": "Demo"}, headers=headers).json()
    sample = make_zip(
        {
            "app.py": PY_GEMINI,
            "comments.py": PY_COMMENT_ONLY,
            "requirements.txt": "google-generativeai==0.8.3\n",
        }
    )
    artifact = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        files={"file": ("demo.zip", sample, "application/zip")},
        headers=headers,
    ).json()
    started = client.post(
        f"/api/v1/projects/{project['id']}/analyses",
        json={"artifact_id": artifact["id"]},
        headers=headers,
    ).json()
    deadline = time.time() + 60
    while time.time() < deadline:
        summary = client.get(f"/api/v1/analyses/{started['id']}", headers=headers).json()
        if summary["job"]["status"] in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}:
            return headers, project["id"], started["id"]
        time.sleep(0.1)
    raise AssertionError("análisis no finalizó")


def test_migration_plan_api_flow(client: TestClient):
    headers, project_id, analysis_id = _setup_analysis(client)
    created = client.post(
        f"/api/v1/projects/{project_id}/migrations",
        json={"analysis_id": analysis_id},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source_provider"] == "Google Gemini"
    assert body["target_provider"] == "NVIDIA NIM"
    assert body["operation_count"] >= 4
    assert body["matrix_summary"]["COMPATIBLE_WITH_ADAPTER"] >= 1
    assert body["plan"]["operations"]
    assert any(change["change_ref"] == "dep-py-remove" for change in body["changes"])

    listed = client.get(f"/api/v1/projects/{project_id}/migrations", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = client.get(f"/api/v1/migrations/{body['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == body["id"]
