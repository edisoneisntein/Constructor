"""Matriz de compatibilidad Gemini → NVIDIA NIM (§12.2).

Evalúa, por cada operación detectada, proveedor/modelo de origen, API de origen,
modelo y endpoint de destino, formato, parámetros, streaming, herramientas,
salidas estructuradas, modalidades, contexto, errores, autenticación, límites,
dependencias y pruebas. Distingue compatibilidad de protocolo y equivalencia
funcional, y NO asume que todos los modelos NIM compartan capacidades.
"""

from __future__ import annotations

from app.core.config import Settings
from app.engines.migration import sources
from app.engines.migration.models import CompatibilityAssessment, Operation

# kind → (categoría, formato de destino, equivalencia funcional, notas)
_MATRIX: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "sdk_import": (
        "COMPATIBLE_WITH_ADAPTER",
        "Se sustituye el SDK de Google por un cliente OpenAI-compatible.",
        "HIGH",
        ("NIM expone API compatible con OpenAI; el SDK Gemini no habla ese protocolo.",),
    ),
    "client_init": (
        "COMPATIBLE_WITH_ADAPTER",
        "base_url apuntando al endpoint NIM configurado.",
        "HIGH",
        ("La credencial pasa de GEMINI_API_KEY a NIM_API_KEY.",),
    ),
    "generation": (
        "COMPATIBLE_WITH_ADAPTER",
        "POST /v1/chat/completions con messages=[{role,content}].",
        "MEDIUM",
        (
            "Gemini usa contents/parts; NIM usa messages. Requiere adaptador.",
            "Parámetros de generación no son idénticos (temperature, top_p, max_tokens).",
        ),
    ),
    "streaming": (
        "COMPATIBLE_WITH_ADAPTER",
        "POST /v1/chat/completions con stream=true (SSE).",
        "MEDIUM",
        ("NIM documenta streaming en chat/completions, completions y responses.",),
    ),
    "embedding": (
        "PARTIAL_COMPATIBILITY",
        "POST /v1/embeddings (microservicio de embeddings aparte).",
        "UNKNOWN",
        (
            "Los embeddings en NIM corresponden a un microservicio distinto (Nemo Retriever).",
            "La dimensionalidad y el modelo de embeddings no son equivalentes a Gemini.",
        ),
    ),
    "tool_calling": (
        "COMPATIBLE_WITH_ADAPTER",
        "Campo tools/function calling de chat/completions.",
        "MEDIUM",
        (
            "NIM LLM documenta tool calling en /v1/chat/completions.",
            "La equivalencia depende del modelo desplegado.",
        ),
    ),
    "structured_output": (
        "PARTIAL_COMPATIBILITY",
        "response_format (JSON schema) cuando el modelo lo soporta.",
        "UNKNOWN",
        (
            "El soporte de salidas estructuradas depende del modelo NIM.",
            "No se asume paridad con response_schema de Gemini.",
        ),
    ),
    "multimodal": (
        "PARTIAL_COMPATIBILITY",
        "chat/completions con content multimodal (image_url).",
        "UNKNOWN",
        (
            "Las entradas multimodales requieren un modelo VLM NIM que las soporte.",
            "No todos los modelos NIM son multimodales.",
        ),
    ),
    "model_config": (
        "REQUIRES_REDESIGN",
        "Selección de modelo NIM por id (p. ej. meta/llama-3.1-8b-instruct).",
        "LOW",
        ("Los identificadores de modelo Gemini no existen en NIM; hay que reasignarlos.",),
    ),
    "env_var": (
        "DIRECTLY_COMPATIBLE",
        "NIM_BASE_URL, NIM_API_KEY, NIM_MODEL.",
        "HIGH",
        ("Cambio de configuración; el protocolo no interviene.",),
    ),
    "rest_call": (
        "COMPATIBLE_WITH_ADAPTER",
        "POST {NIM_BASE_URL}/chat/completions con Authorization: Bearer.",
        "MEDIUM",
        ("El cuerpo de la petición REST cambia de formato (contents → messages).",),
    ),
    "error_handling": (
        "COMPATIBLE_WITH_ADAPTER",
        "Errores HTTP estándar del endpoint OpenAI-compatible.",
        "MEDIUM",
        ("Las excepciones del SDK de Google deben reemplazarse por manejo de errores HTTP.",),
    ),
}


def _base_assessment(kind: str, settings: Settings) -> CompatibilityAssessment:
    category, request_format, equivalence, notes = _MATRIX.get(
        kind,
        (
            "NOT_VERIFIED",
            "Sin equivalente evaluado.",
            "UNKNOWN",
            ("Operación no evaluada en la matriz; requiere revisión manual.",),
        ),
    )
    endpoint_key = "chat_completions"
    if kind == "embedding":
        endpoint_key = "embeddings"
    elif kind == "rest_call":
        endpoint_key = "chat_completions"
    protocol = "OPENAI_COMPATIBLE" if kind not in {"sdk_import", "model_config"} else "DIFFERENT_PROTOCOL"
    criteria = {
        "formato_solicitud": request_format,
        "streaming": "soportado (stream=true)" if kind in {"streaming", "generation"} else "n/a",
        "herramientas": "depende del modelo" if kind == "tool_calling" else "n/a",
        "salidas_estructuradas": "depende del modelo" if kind == "structured_output" else "n/a",
        "modalidades": "depende del modelo (VLM)" if kind == "multimodal" else "texto",
        "contexto": "definido por el modelo NIM desplegado",
        "errores": "HTTP estándar del endpoint OpenAI-compatible",
        "autenticacion": "Authorization: Bearer <NIM_API_KEY>",
        "limites_uso": "definidos por el despliegue/modelo",
        "dependencias": "cliente OpenAI-compatible; sin SDK de Google",
        "pruebas": "unitarias disponibles; integración requiere credenciales (BLOCKED)",
    }
    return CompatibilityAssessment(
        operation_kind=kind,
        category=category,
        source_provider="Google Gemini",
        source_api="google-generativeai / google-genai SDK",
        target_provider="NVIDIA NIM",
        target_endpoint=f"{settings.nim_base_url}/{sources.NIM_ENDPOINTS[endpoint_key].split(' ', 1)[1].lstrip('/')}",
        target_model=settings.nim_model,
        protocol_compatibility=protocol,
        functional_equivalence=equivalence,
        criteria=criteria,
        notes=list(notes) + [sources.DISCLAIMER],
    )


def assess_operations(operations: list[Operation], settings: Settings) -> list[CompatibilityAssessment]:
    seen: set[str] = set()
    assessments: list[CompatibilityAssessment] = []
    for operation in operations:
        if operation.kind in seen:
            continue
        seen.add(operation.kind)
        assessments.append(_base_assessment(operation.kind, settings))
    return assessments


def matrix_summary(assessments: list[CompatibilityAssessment]) -> dict[str, int]:
    counts: dict[str, int] = {category: 0 for category in (
        "DIRECTLY_COMPATIBLE",
        "COMPATIBLE_WITH_ADAPTER",
        "PARTIAL_COMPATIBILITY",
        "REQUIRES_REDESIGN",
        "UNSUPPORTED",
        "NOT_VERIFIED",
    )}
    for assessment in assessments:
        counts[assessment.category] = counts.get(assessment.category, 0) + 1
    return counts
