"""Pruebas del orquestador de análisis estático (§19.1)."""

from __future__ import annotations

from app.engines.analysis.integrations import classify_integration
from app.engines.analysis.source_analysis import run_source_analysis


def _write_project(root):
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(
        "import os\n"
        "from google import generativeai as genai\n"
        "KEY = os.getenv('GEMINI_API_KEY')\n"
        "def main():\n"
        "    return genai\n",
        encoding="utf-8",
    )
    (root / "src" / "index.js").write_text(
        "import { GoogleGenerativeAI } from '@google/generative-ai';\n"
        "const key = process.env.GEMINI_API_KEY;\n"
        "export function make() { return new GoogleGenerativeAI(key); }\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        '{"name":"demo","version":"1.0.0","dependencies":{"@google/generative-ai":"^0.21.0"}}',
        encoding="utf-8",
    )


def test_analysis_produces_findings_and_graph(tmp_path):
    _write_project(tmp_path)
    output = run_source_analysis(
        tmp_path,
        analysis_id="anl_test",
        project_id="prj_test",
        organization_id="org_test",
        created_at="2026-01-01T00:00:00+00:00",
        analysis_max_file_bytes=2_000_000,
        js_timeout_seconds=60,
        rea=None,
        deep_analysis=False,
    )
    categories = {f["category"] for f in output.findings}
    assert "LANGUAGE" in categories
    assert "AI_INTEGRATION" in categories
    assert "ENVIRONMENT_VARIABLE" in categories
    assert "DEPENDENCY" in output.summary or output.dependencies
    npm_deps = {d["name"] for d in output.dependencies}
    assert "@google/generative-ai" in npm_deps
    assert output.summary["files_analyzed"] >= 1  # analizador Python siempre disponible
    assert output.nodes and output.edges
    # El grafo distingue confirmadas de inferidas.
    assert output.summary["confirmed_edge_count"] >= 1
    languages = output.summary["languages"]
    assert "python" in languages
    # JS/TS depende de Node + @babel/parser; si no está, debe quedar como limitación explícita.
    if "javascript" not in languages:
        assert any("babel" in lim.lower() or "node" in lim.lower() for lim in output.limitations)


def test_comment_mentions_do_not_create_integration():
    assert classify_integration("os") is None
    assert classify_integration("google") is None
    assert classify_integration("google.generativeai") is not None
    assert classify_integration("@google/generative-ai").provider == "google_gemini"
