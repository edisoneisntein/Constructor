# Registro de verificación — Build/run E2E de contenedores (§19.6, §21 Fase 12)

- **ID**: 20261018-container-e2e
- **Fecha**: 2026-10-18 (UTC-05:00)
- **Tipo**: verificación de integración en contenedor (no `pytest`)
- **Comando principal**: `docker compose build && docker compose up -d`
- **Herramientas y versiones**: Docker Engine 29.5.2 (`linux`, vía Colima),
  Docker Compose v5.4.0, imagen `python:3.12-slim`, imagen `node:22-slim`,
  FastAPI 0.139.0, uvicorn 0.49.0, Python 3.12.x en contenedor.
- **Resultado**: `TEST_PASSED`
- **Resumen**: 2/2 imágenes construidas; 2/2 servicios en ejecución; health y
  flujo vertical funcionales.
- **Passed**:
  1. `docker compose build` backend → imagen `platform-backend` OK.
  2. `docker compose build` frontend → imagen `platform-frontend` OK.
  3. `docker compose up -d` → `platform-backend-1` y `platform-frontend-1` `Up`.
  4. `GET http://127.0.0.1:8000/health` → 200 `{"status":"ok"}`.
  5. `GET http://127.0.0.1:8000/health/ready` → 200 `{"status":"ready"}` (DB ok).
  6. `GET http://127.0.0.1:3000/` (frontend) → 200.
  7. Flujo E2E real: registro → proyecto → subida `src.zip` → análisis →
     `job_status=COMPLETED`, `finding_count=3`; `/observability/metrics`
     `jobs_total=1`.
- **Failed**: 0
- **Not run**: 0 (en este registro; la UI no se ejercitó con navegador —
  automatización de navegador sigue `TEST_NOT_RUN`).
- **Diagnóstico / defecto corregido**:
  - `RuntimeError: Form data requires "python-multipart"` al arrancar en
    contenedor. Causa: `python-multipart` no estaba en `requirements.txt` (solo
    presente en el entorno local). Corrección: se fija `python-multipart==0.0.32`.
  - **Carrera transaccional**: el `commit` de dependencias `yield` se ejecutaba
    *después* de enviar la respuesta, causando 401 intermedios (~1/12) al
    reutilizar la sesión recién creada en un servidor con conexión por petición.
    Corrección: `app/db/transaction.py` (`TransactionMiddleware`) confirma la
    conexión antes de devolver la respuesta. Verificado con 72 peticiones
    autenticadas consecutivas: 0 fallos.
  - Se añadieron `.dockerignore` (backend/frontend) para excluir
    `node_modules`/`.next`/cachés del contexto de build.

Reproducir:

```bash
cd platform
colima start                     # o cualquier daemon de Docker
docker compose build
docker compose up -d
curl -s http://127.0.0.1:8000/health/ready
```
