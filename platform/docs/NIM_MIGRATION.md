# Guía de migración Gemini → NVIDIA NIM (§12)

> Estado: **PARTIALLY_IMPLEMENTED**. La detección, la matriz de compatibilidad y el
> plan de migración (con diffs estructurales) están implementados y probados. Las
> pruebas de integración contra NVIDIA NIM quedan **BLOCKED** por falta de credenciales.

## 1. Panorama

El módulo `app/engines/migration/` implementa el adaptador `GeminiToNIM` del PDF
(§12). No asume que NVIDIA NIM sea un modelo único ni una API universal: cada
modelo NIM es un microservicio distinto y sus capacidades varían (§12.2).

Componentes:

| Archivo | Función |
|---------|---------|
| `gemini_detector.py` | Detecta operaciones reales del SDK de Gemini (AST en Python; patrones sin comentarios en JS/TS). |
| `nim_compat.py` | Matriz de compatibilidad con las 6 categorías de §12.2. |
| `planner.py` | Plan, cambios de dependencias, adaptador, entorno y diffs. |
| `rules.py` | Reglas de migración versionadas (§11). |
| `sources.py` | Fuentes oficiales y fecha de verificación (§12.3). |

## 2. Detección (§12.1)

Categorías detectadas: `sdk_import`, `client_init`, `generation`, `streaming`,
`embedding`, `tool_calling`, `structured_output`, `multimodal`, `model_config`,
`env_var`, `rest_call`, `error_handling`.

- **Python**: se analiza el AST, por lo que referencias en comentarios o cadenas
  no ejecutadas **no** se cuentan (verificado en `tests/test_migration.py`).
- **JS/TS**: se eliminan los comentarios conservando números de línea y se
  aplican patrones de `@google/generative-ai` y `@google/genai`.

Ejemplo:

```python
import google.generativeai as genai            # sdk_import
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))  # client_init + env_var
model = genai.GenerativeModel("gemini-1.5-pro")       # client_init + model_config
model.generate_content("hola", tools=[], response_mime_type="application/json")
# → generation + tool_calling + structured_output
```

## 3. Matriz de compatibilidad (§12.2)

Por cada operación se evalúan proveedor/modelo de origen, API de origen, modelo y
endpoint de destino, formato, parámetros, streaming, herramientas, salidas
estructuradas, modalidades, contexto, errores, autenticación, límites,
dependencias y pruebas. Categorías:

| Operación | Categoría | Protocolo | Equivalencia funcional |
|-----------|-----------|-----------|------------------------|
| `env_var` | DIRECTLY_COMPATIBLE | — | HIGH |
| `generation` / `streaming` | COMPATIBLE_WITH_ADAPTER | OPENAI_COMPATIBLE | MEDIUM |
| `tool_calling` | COMPATIBLE_WITH_ADAPTER | OPENAI_COMPATIBLE | MEDIUM |
| `client_init` / `sdk_import` | COMPATIBLE_WITH_ADAPTER | DIFFERENT_PROTOCOL | HIGH |
| `rest_call` / `error_handling` | COMPATIBLE_WITH_ADAPTER | OPENAI_COMPATIBLE | MEDIUM |
| `embedding` | PARTIAL_COMPATIBILITY | OPENAI_COMPATIBLE | UNKNOWN |
| `structured_output` | PARTIAL_COMPATIBILITY | OPENAI_COMPATIBLE | UNKNOWN |
| `multimodal` | PARTIAL_COMPATIBILITY | OPENAI_COMPATIBLE | UNKNOWN |
| `model_config` | REQUIRES_REDESIGN | DIFFERENT_PROTOCOL | LOW |

Se distingue explícitamente **compatibilidad de protocolo** y **equivalencia
funcional**. `NOT_VERIFIED` se usa cuando no hay evidencia suficiente.

## 4. Plan de migración (§12.3)

`build_plan` genera:

- **Cambios de dependencias**: eliminación determinista de
  `google-generativeai`/`google-genai` o `@google/generative-ai`/`@google/genai`
  (con diff real si el manifiesto está disponible). La adición de `openai` se
  propone como cambio manual: la versión exacta la elige el usuario (no se inventa).
- **Adaptador**: `migration/nim_client.py` y/o `migration/nimClient.ts`, con
  endpoint y modelo configurables (leídos del entorno).
- **Entorno de ejemplo**: `NIM_BASE_URL`, `NIM_API_KEY`, `NIM_MODEL` (sin claves reales).
- **Reescritura de llamadas**: propuesta **manual** (`REQUIRES_REDESIGN`); no se
  aplica por coincidencia textual (§11).
- **Pruebas propuestas** e **informe de limitaciones**.

Los cambios propuestos son compatibles con el motor de cambios (§15): pueden
llevarse a un `change_set` para aprobación y reversión.

## 5. Fuentes oficiales y fecha de verificación (§12.3)

| Fuente | URL | Verificado |
|--------|-----|------------|
| NVIDIA NIM — API Reference (LLM) | https://docs.nvidia.com/nim/large-language-models/latest/reference/api-reference.html | 2026-10-18 |
| NVIDIA NIM — Quickstart (LLM) | https://docs.nvidia.com/nim/large-language-models/latest/get-started/quickstart.html | 2026-10-18 |
| NVIDIA NIM — API Catalog | https://build.nvidia.com/models | 2026-10-18 |
| NVIDIA API — chat completion | https://docs.api.nvidia.com/nim/reference/models-1 | 2026-10-18 |
| Google AI — Gemini API | https://ai.google.dev/gemini-api/docs | 2026-10-18 |

Datos de NIM registrados: API **OpenAI-compatible** (vLLM); endpoints
`POST /v1/chat/completions` (streaming y tool calling), `POST /v1/completions`,
`POST /v1/responses`, `GET /v1/models`, `POST /v1/messages`; host hospedado
`https://integrate.api.nvidia.com`; modelo por `NIM_SERVED_MODEL_NAME`. **No se
asume una URL universal** para todos los despliegues (§12.3).

## 6. Configuración (sin secretos reales)

```
SIREP_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
SIREP_NIM_MODEL=meta/llama-3.1-8b-instruct
SIREP_NIM_API_KEY=nvapi-REEMPLAZAR-CON-CLAVE-REAL
SIREP_GEMINI_API_BASE_URL=https://generativelanguage.googleapis.com
```

## 7. Limitaciones conocidas

- La **equivalencia funcional** no está verificada sin credenciales de NIM (§1.1).
- No se reescriben automáticamente las llamadas (`generate_content`, etc.).
- Las capacidades de tool calling, structured output y multimodalidad dependen
  del modelo NIM desplegado.
- Los embeddings migran a un microservicio NIM distinto (Nemo Retriever).

## 8. Pruebas pendientes (BLOCKED)

Las pruebas de integración real contra `https://integrate.api.nvidia.com` requieren
`NIM_API_KEY` real. Permanecen `BLOCKED` y no se afirman como ejecutadas.
