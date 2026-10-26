"""Relaciones ampliadas del grafo (Fase 3, §7)."""

from __future__ import annotations

from app.engines.analysis.source_analysis import run_source_analysis


def _write_project(root):
    (root / "src").mkdir()
    (root / "src" / "index.js").write_text(
        "import { GoogleGenerativeAI } from '@google/generative-ai';\n"
        "const key = process.env.GEMINI_API_KEY;\n"
        "export function make() { return new GoogleGenerativeAI(key); }\n",
        encoding="utf-8",
    )
    (root / "src" / "app.py").write_text(
        "import os\n"
        "def main():\n"
        "    return os.getenv('GEMINI_API_KEY')\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        '{"name":"demo","dependencies":{"@google/generative-ai":"^0.21.0"}}',
        encoding="utf-8",
    )


def test_graph_has_rich_relations(tmp_path):
    _write_project(tmp_path)
    output = run_source_analysis(
        tmp_path,
        analysis_id="anl_graph",
        project_id="prj",
        organization_id="org",
        created_at="2026-01-01T00:00:00+00:00",
        analysis_max_file_bytes=2_000_000,
        js_timeout_seconds=60,
        rea=None,
        deep_analysis=False,
    )
    node_types = {node["node_type"] for node in output.nodes}
    assert {"file", "manifest", "dependency", "integration", "env_var", "symbol"} <= node_types

    edge_types = {edge["edge_type"] for edge in output.edges}
    assert {"declares_dependency", "depends_on", "uses", "reads_env", "defines"} <= edge_types

    # La relación SDK ↔ variable de entorno debe ser inferida, no directa.
    configures = [edge for edge in output.edges if edge["edge_type"] == "configures"]
    assert configures
    assert all(edge["evidence_level"] == "STATIC_INFERENCE" for edge in configures)

    # Los nodos clave existen con identificadores estables.
    node_ids = {node["id"] for node in output.nodes}
    assert "integ::google_gemini" in node_ids
    assert "env::GEMINI_API_KEY" in node_ids
    assert "dep::npm::@google/generative-ai" in node_ids

    # El summary desglosa por tipo.
    assert output.summary["node_type_counts"].get("integration") == 1
    assert output.summary["edge_type_counts"].get("uses", 0) >= 1
