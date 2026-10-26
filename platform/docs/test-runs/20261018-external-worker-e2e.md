# Registro de verificación — Cola externa en contenedores (§4.3, §19.6, §21 Fase 13)

- **ID**: 20261018-external-worker-e2e
- **Fecha**: 2026-10-18 (UTC-05:00)
- **Tipo**: verificación de integración multi-servicio (no `pytest`).
- **Comando**:
  ```bash
  cd platform
  FRONTEND_PORT=3100 SIREP_ALLOWED_ORIGINS=http://localhost:3100 docker compose up -d --build
  ```
- **Herramientas y versiones**: Docker Engine 29.5.2 (Colima), Docker Compose
  v5.4.0, imagen `python:3.12-slim`, FastAPI 0.139.0.
- **Resultado**: `TEST_PASSED`
- **Resumen**: 3 servicios (`backend`, `worker`, `frontend`) arriba; la API encola
  (`QUEUED`) y el proceso trabajador reclama y completa (`COMPLETED`).
- **Passed**:
  1. `docker compose config` válido; servicios `backend`, `worker`, `frontend`
     construidos y en ejecución.
  2. `GET /api/v1/meta` → `job_queue.backend=external`,
     `capabilities.external_job_workers=IMPLEMENTED`,
     `rate_limit.backend=database`, `capabilities.rate_limiting=IMPLEMENTED`.
  3. Flujo real por API: registro → proyecto → subida ZIP → análisis devuelve
     `status=QUEUED` (la API no ejecuta el trabajo en proceso).
  4. El contenedor `worker` reclama el trabajo
     (`worker_claimed … attempt=1`) y lo finaliza: `COMPLETED`, `nodes=3`,
     `findings=3`.
  5. Cancelación cooperativa entre procesos cubierta por pruebas unitarias.
  6. Limitación de tasa compartida: `rate_limit_counters` contiene filas en la
     base (`api:172.18.0.1:60`, `auth:172.18.0.1:60`), confirmando que el conteo
     se comparte por base de datos y no por proceso.
  7. E2E de UI (Playwright) re-ejecutado contra el modo externo → `TEST_PASSED`.
- **Failed**: 0
- **Not run**: 0
- **Diagnóstico / ajustes**:
  - El proceso trabajador no configuraba el logging estructurado (solo
    `create_app` lo hacía), por lo que no emitía trazas. Se llama a
    `configure_logging()` en `app/worker.py`.
  - `JsonFormatter` ahora incluye los campos estructurados (`worker_id`,
    `job_id`, `attempt`, …) y aplica redacción de secretos también a ellos.
