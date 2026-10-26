"""Pruebas unitarias del analizador Python (§19.1)."""

from __future__ import annotations

from app.engines.analysis.python_analyzer import analyze_python_file

SAMPLE = '''
import os
from google import generativeai as genai
from google.generativeai import configure

API_KEY = os.getenv("GEMINI_API_KEY")
REGION = os.environ["REGION"]


class Client:
    def run(self):
        return None


@app.post("/generate")
def generate(prompt: str):
    return eval(prompt)


if __name__ == "__main__":
    print("entry")
'''


def test_detects_imports_symbols_env_routes_entrypoint():
    facts = analyze_python_file("app.py", SAMPLE)
    assert facts.syntax_error is None
    modules = facts.import_specifiers
    assert "os" in modules
    assert "google" in modules
    assert "google.generativeai" in modules
    assert any(fn.name == "generate" for fn in facts.functions)
    assert any(cls.name == "Client" for cls in facts.classes)
    env_names = {env.name for env in facts.env_vars}
    assert "GEMINI_API_KEY" in env_names
    assert "REGION" in env_names
    assert facts.api_routes and facts.api_routes[0].path == "/generate"
    assert facts.api_routes[0].method == "POST"
    assert facts.entry_point is True
    rules = {pattern.rule for pattern in facts.insecure_patterns}
    assert "EVAL" in rules


def test_reports_syntax_error():
    facts = analyze_python_file("broken.py", "def x(:\n  pass\n")
    assert facts.syntax_error is not None
    assert facts.functions == []


def test_does_not_flag_comment_only_mentions():
    facts = analyze_python_file("doc.py", "# This project uses Google Gemini SDK\nx = 1\n")
    assert facts.import_specifiers == []
    assert facts.functions == []
