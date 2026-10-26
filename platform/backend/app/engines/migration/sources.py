"""Fuentes oficiales consultadas y base de conocimiento de NVIDIA NIM (§12.2/§12.3).

§12.3 exige consultar la documentación oficial y registrar la fuente y la fecha
de verificación. Los datos aquí almacenados provienen de esas fuentes y NO
asumen que todos los modelos NIM compartan capacidades ni una URL universal.
"""

from __future__ import annotations

# Fecha (UTC) en la que se verificó la documentación oficial.
VERIFIED_AT = "2026-10-18"

SOURCES: list[dict[str, str]] = [
    {
        "name": "NVIDIA NIM — NIM for Large Language Models, API Reference",
        "url": "https://docs.nvidia.com/nim/large-language-models/latest/reference/api-reference.html",
        "verified_at": VERIFIED_AT,
        "notes": "API de inferencia compatible con OpenAI, respaldada por vLLM.",
    },
    {
        "name": "NVIDIA NIM — Quickstart (LLM)",
        "url": "https://docs.nvidia.com/nim/large-language-models/latest/get-started/quickstart.html",
        "verified_at": VERIFIED_AT,
        "notes": "Endpoints /v1/chat/completions, /v1/completions, /v1/responses; modelo por NIM_SERVED_MODEL_NAME.",
    },
    {
        "name": "NVIDIA NIM — API Catalog (build.nvidia.com)",
        "url": "https://build.nvidia.com/models",
        "verified_at": VERIFIED_AT,
        "notes": "Catálogo de modelos; cada modelo es una microservicio distinto.",
    },
    {
        "name": "NVIDIA API — Create a chat completion",
        "url": "https://docs.api.nvidia.com/nim/reference/models-1",
        "verified_at": VERIFIED_AT,
        "notes": "Host hospedado https://integrate.api.nvidia.com/v1/chat/completions.",
    },
    {
        "name": "Google AI — Gemini API (google-genai / google-generativeai)",
        "url": "https://ai.google.dev/gemini-api/docs",
        "verified_at": VERIFIED_AT,
        "notes": "SDK de origen cuyas operaciones se detectan antes de migrar.",
    },
]

# Hosts y endpoints reales de NVIDIA NIM (configurables; aquí solo valores por defecto).
NIM_HOSTED_BASE_URL = "https://integrate.api.nvidia.com/v1"
NIM_LOCAL_BASE_URL = "http://localhost:8000/v1"

# Endpoints documentados (LLM/VLM). El conjunto soportado depende del modelo desplegado.
NIM_ENDPOINTS = {
    "chat_completions": "POST /v1/chat/completions",
    "completions": "POST /v1/completions",
    "responses": "POST /v1/responses",
    "models": "GET /v1/models",
    "messages": "POST /v1/messages",
    "tokenize": "POST /tokenize",
    "detokenize": "POST /detokenize",
    "embeddings": "POST /v1/embeddings",
}

# Capacidades documentadas de la API (protocolo), independientes del modelo.
NIM_API_CAPABILITIES = {
    "streaming": True,
    "tool_calling": True,
    "openai_compatible": True,
    "multimodal": "depende del modelo (VLM NIM)",
    "structured_output": "depende del modelo / response_format",
    "embeddings": "microservicio separado (Nemo Retriever text-embedding)",
}

# Modelos de ejemplo reales citados en la documentación. NO es una lista exhaustiva.
NIM_KNOWN_MODELS = [
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
    "nvidia/nemotron-3-content-safety",
    "mistralai/ministral-3-14b-instruct-2512",
]

DISCLAIMER = (
    "NVIDIA NIM no es un único modelo ni una API universal: cada modelo es una "
    "microservicio distinto y sus capacidades varían. La compatibilidad debe "
    "verificarse por modelo y por despliegue (§12.2)."
)
