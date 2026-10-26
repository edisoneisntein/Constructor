# Informe Fase 13 — Escalabilidad (§4.3, §4.4, §14, §21, §23)

## 1. Objetivo
Permitir que la plataforma escale horizontalmente sin cambiar los contratos de la
API: (a) ejecutar los análisis en procesos trabajadores externos en lugar del pool
de hilos del proceso de la API, con reclamo atómico y recuperación de huérfanos; y
(b) compartir la limitación de tasa entre instancias mediante contadores en la
base de datos, manteniendo el modo en memoria como predeterminado ligero.

## 2. Archivos creados
- `platform/backend/app/worker.py` — proceso trabajador de la cola externa
  (`python -m app.worker [--once]`), reclamo, heartbeat, recuperación, señales.
- `platform/backend/tests/test_worker.py` — 6 pruebas de la cola externa.
- `platform/backend/tests/test_rate_limit_backend.py` — 6 pruebas del backend de
  límites compartido.
- `platform/docs/test-runs/20261018-external-worker-e2e.md` — verificación en
  contenedores.

## 3. Archivos modificados
- `platform/backend/app/core/config.py` — `job_queue_backend`, `worker_id`,
  `worker_poll_interval_seconds`, `worker_claim_batch`, `job_stale_after_seconds`,
  `job_max_attempts`, `rate_limit_backend` y su lectura desde el entorno
  (`_env_float` nueva).
- `platform/backend/app/db/database.py` — `SCHEMA_VERSION = 7`; columnas
  `attempt_count`/`claimed_by`/`claimed_at` en `analysis_jobs` (migración
  `_migrate_job_claim_columns`); tabla `rate_limit_counters`; índice
  `idx_jobs_status_created`.
- `platform/backend/app/db/repositories.py` — `claim_next_job`, `heartbeat_job`,
  `recover_stale_jobs`, `is_cancel_requested`, helper `_iso_before`;
  `ACTIVE_JOB_STATUSES` incluye `ANALYZING`/`GRAPH_BUILDING`.
- `platform/backend/app/services/analysis_service.py` — `_run_analysis_job`
  renombrado a `run_analysis_job` (público) con `worker_id`/heartbeat;
  `start_analysis` respeta el modo de cola; `cancel_analysis` distingue
  `QUEUED`/`ANALYZING`/`RUNNING` en modo externo.
- `platform/backend/app/core/rate_limit.py` — backends `memory` y `database`.
- `platform/backend/app/core/logging.py` — el formateador incluye extras
  estructurados y los redacta.
- `platform/backend/app/api/v1/router.py` — `/meta` expone `job_queue`,
  `rate_limit` y la capacidad `external_job_workers`.
- `platform/docker-compose.yml` — servicio `worker`; `SIREP_JOB_QUEUE=external` y
  `SIREP_RATE_LIMIT_BACKEND=database` por defecto.
- `platform/.env.example` — variables de cola y de límites.
- `platform/docs/PROGRESS.md`, `ARCHITECTURE.md`, `LIMITATIONS.md`,
  `DEPLOYMENT.md`.

## 4. Componentes reutilizados
- `run_analysis_job` (motor de análisis existente) sin cambios de contrato.
- Repositorio SQLite (`analysis_jobs`) como cola persistente: sin broker nuevo.
- `RequestContextMiddleware` de observabilidad, sin cambios de contrato.

## 5. Funcionalidades implementadas
- **Cola externa**: la API crea el trabajo `QUEUED` y no lo ejecuta; uno o varios
  workers lo reclaman con `UPDATE … RETURNING` (atómico) y lo ejecutan.
- **Heartbeat y recuperación**: los trabajos `RUNNING` sin latido se reencolan
  hasta `job_max_attempts`, luego pasan a `FAILED` (`worker_lost`).
- **Cancelación cooperativa entre procesos**: el worker lee `cancel_requested`.
- **Limitación de tasa compartida** (ventana fija en base de datos) seleccionable
  por configuración.
- **Purga de retención programada (§14.6)**: el worker aplica
  `purge_expired_artifacts` según `SIREP_RETENTION_PURGE_INTERVAL_SECONDS`
  (<=0 la desactiva), cubriendo el hueco del "sin planificador periódico".

## 6. Pruebas ejecutadas
- `cd platform/backend && python3 -m pytest` → `docs/test-runs/20261018-182757.{json,md}`.
- Verificación multi-servicio → `docs/test-runs/20261018-external-worker-e2e.md`.
- E2E de UI → `docs/test-runs/20261018-ui-e2e-playwright.md`.

## 7. Resultados reales
- **105 passed, 0 failed, 0 errors, 0 skipped** (antes 92; +13).
- En contenedores: `backend`, `worker`, `frontend` arriba; el análisis iniciado
  por la API queda `QUEUED` y el worker lo completa (`COMPLETED`, `nodes=3`,
  `findings=3`); logs del worker con `worker_claimed … attempt=1`.
- `rate_limit_counters` poblado → el conteo es compartido por base de datos.
- E2E de UI en modo externo: 1/1 aprobado.

## 8. Pruebas no ejecutadas
- Escala con múltiples réplicas reales y PostgreSQL: `PROPOSED_NOT_IMPLEMENTED`
  (ver §9).
- Redis como backend alternativo: `PROPOSED_NOT_IMPLEMENTED` (no requerido por el
  MVP; la base de datos cubre el caso multi-instancia).

## 9. Problemas pendientes
- **PostgreSQL**: la capa de repositorio es el punto de migración, pero el código
  usa `sqlite3` y placeholders `?`; falta un dialecto/adaptador y pruebas contra
  un servidor real.
- SQLite en modo WAL soporta varios procesos, pero no es el objetivo de escala
  final; la cola externa está diseñada para migrar a un broker (Redis/ARQ/Celery)
  sin cambiar los contratos.

## 10. Riesgos
- Con SQLite y varios workers aumenta la contención de escritura; aceptable para
  MVP, mitigable con PostgreSQL.
- El modo `database` de límites añade una escritura por petición; se mantiene
  `memory` como predeterminado para no degradar el caso de una sola instancia.

## 11. Instrucciones para reproducir
```bash
cd platform
FRONTEND_PORT=3100 SIREP_ALLOWED_ORIGINS=http://localhost:3100 docker compose up -d --build
curl -s http://127.0.0.1:8000/api/v1/meta            # job_queue.backend=external
docker logs platform-worker-1 | tail                 # worker_started / worker_claimed
cd backend && python3 -m pytest
```

## 12. Próxima fase
- Migración a PostgreSQL tras la capa de repositorio (dialecto + pruebas contra
  contenedor).
- Fase 8 §6.3 y Fases 5/7/6 siguen bloqueadas por ejecución aislada / IA real
  (ver `docs/reports/FASE_5_8_REPORT.md`).
