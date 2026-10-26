"""Reglas ampliadas de la Fase 3: SDK de proveedor, modelos y secretos (§5, §12)."""

from __future__ import annotations

from app.engines.analysis.python_analyzer import analyze_python_file

SAMPLE = '''
import os
import google.generativeai as genai

genai.configure(api_key="AIzaSy0123456789ABCDEFGHIJKLMNOPQRSTUV")
model = genai.GenerativeModel("gemini-1.5-pro")

API_KEY = "sk-abcdef1234567890abcdef1234567890"
DB_PASSWORD = os.getenv("DB_PASSWORD")
'''


def test_detects_provider_usage_and_models():
    facts = analyze_python_file("svc.py", SAMPLE)
    callees = {call.callee for call in facts.provider_calls}
    assert "genai.configure" in callees
    assert "genai.GenerativeModel" in callees
    models = {ref.value for ref in facts.model_refs}
    assert any("gemini" in value.lower() for value in models)


def test_detects_hardcoded_secrets_but_not_env_reads():
    facts = analyze_python_file("svc.py", SAMPLE)
    rules = [secret.rule for secret in facts.hardcoded_secrets]
    assert "HARDCODED_SECRET" in rules
    # Un valor obtenido del entorno no debe marcarse como secreto embebido.
    assert all("DB_PASSWORD" not in secret.snippet for secret in facts.hardcoded_secrets)


def test_placeholder_is_not_a_secret():
    facts = analyze_python_file("env.py", 'API_KEY = "REEMPLAZAR-CON-CLAVE-REAL-1234567890"\n')
    assert facts.hardcoded_secrets == []
