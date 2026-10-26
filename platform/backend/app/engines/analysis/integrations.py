"""Clasificación de integraciones de IA a partir de especificadores de import.

§5.2 ("Integraciones de IA") y base para §12.1 (detección Gemini). Solo se
clasifica por el **especificador de import de un módulo**, que es evidencia
estructural (DIRECT_EVIDENCE): no se confunde con menciones en comentarios o
documentación.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class IntegrationMatch:
    provider: str
    package_hint: str
    detection_method: str


# Patrones por proveedor sobre el especificador de import (Python y JS/TS).
_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "google_gemini": [
        re.compile(r"^@google/generative-ai$"),
        re.compile(r"^@google/genai$"),
        re.compile(r"^@google-cloud/vertexai$"),
        re.compile(r"^@google-cloud/aiplatform$"),
        re.compile(r"^google\.generativeai$"),
        re.compile(r"^google\.genai$"),
        re.compile(r"^google\.cloud\.aiplatform"),
        re.compile(r"^vertexai"),
        re.compile(r"^langchain[_\.]google[_\.]genai"),
        re.compile(r"^llama_index\.llms\.google"),
        re.compile(r"^langchain_google_vertexai"),
    ],
    "nvidia_nim": [
        re.compile(r"^openai$"),  # NIM es compatible con OpenAI; requiere verificación (§12)
        re.compile(r"^@nvidia/"),
        re.compile(r"^nvidia[-_]?nim"),
    ],
    "openai": [re.compile(r"^openai$")],
    "anthropic": [re.compile(r"^@anthropic-ai/sdk$"), re.compile(r"^anthropic$")],
}


def classify_integration(module_specifier: str) -> IntegrationMatch | None:
    """Devuelve la coincidencia de proveedor o ``None``.

    El método se marca como coincidencia exacta de especificador de import para
    dejar constancia de que la evidencia es estructural, no semántica.
    """
    spec = module_specifier.strip().strip("'\"")
    if not spec:
        return None
    for provider, patterns in _PATTERNS.items():
        for pattern in patterns:
            if pattern.search(spec):
                return IntegrationMatch(
                    provider=provider,
                    package_hint=spec,
                    detection_method="import_specifier_exact_match",
                )
    return None
