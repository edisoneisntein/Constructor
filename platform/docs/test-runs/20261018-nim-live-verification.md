# Registro de verificación — Integración NVIDIA NIM en vivo (§12, §13, §19.6, §21 Fase 14)

- **ID**: 20261018-nim-live-verification
- **Fecha**: 2026-10-18 (UTC-05:00)
- **Tipo**: verificación de integración con proveedor externo real (no `pytest`).
- **Proveedor**: NVIDIA NIM (API compatible con OpenAI). **Proveedor único de IA**
  de la plataforma; **no se integra Gemini**.
- **Endpoint**: `https://integrate.api.nvidia.com/v1` · Modelo:
  `nvidia/nemotron-3-super-120b-a12b`.
- **Resultado**: `TEST_PASSED`
- **Comandos**:
  ```bash
  cd platform/backend && python -m scripts.verify_nim
  SIREP_NIM_LIVE_TEST=1 python3 -m pytest tests/test_nim_client.py::test_live_nim_verification -q
  # En contenedor (también vía API autenticada):
  # POST /api/v1/migrations/nim/verify
  ```
- **Evidencia (real)**:
  - `python -m scripts.verify_nim` → `RESULT: TEST_PASSED`.
  - Prueba en vivo de `pytest` → 1 passed.
  - En contenedor, `POST /api/v1/migrations/nim/verify` (rol developer) → 200:
    `configured=true, reachable=true, model_available=true, models_count=81,
    completion_ok=true, latency_ms≈934–1672`.
  - `GET /api/v1/meta` → `capabilities.nim_integration=IMPLEMENTED`,
    `ai.provider=nvidia_nim`.
- **Failed**: 0
- **Not run**: 0
- **Diagnóstico / ajustes**:
  - **DNS en contenedores**: Colima no propagaba resolvers al DNS embebido de
    Docker (`NO EXTERNAL NAMESERVERS DEFINED`); la llamada a NIM fallaba con
    `Temporary failure in name resolution`. Se fijaron resolvers en
    `docker-compose.yml` (`dns: 1.1.1.1, 8.8.8.8`, parametrizables). Verificado
    con `socket.gethostbyname` dentro del contenedor.
  - **Modelo por defecto**: `meta/llama-3.1-8b-instruct` **no** está servido por
    esta cuenta; se ajustó el valor por defecto a
    `nvidia/nemotron-3-super-120b-a12b` (confirmado en `/v1/models`).
  - **Credenciales**: se cargan desde `.env` local (no versionado) y desde el
    entorno de Compose; nunca se escriben en el código ni en los registros.
  - **Clave de Gemini**: se comprobó que es inválida (`API_KEY_INVALID`). No se
    usa ningún proveedor Gemini, en línea con la decisión del usuario.

Reproducir:

```bash
cd platform/backend
printf 'SIREP_NIM_API_KEY=nvapi-...\n' >> .env   # credencial local (no versionada)
python -m scripts.verify_nim
```
