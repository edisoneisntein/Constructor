# Informe de Fase 12 — Preparación comercial (§21, §22, §23)

## 1. Objetivo

Según §21 Fase 12 y §22: cerrar la preparación comercial del MVP —documentación,
despliegue verificable, gestión de uso y cuotas— entregando solo lo realmente
funcional. La facturación y los costes dependen de decisiones de negocio y
credenciales y se declaran `PROPOSED_NOT_IMPLEMENTED`.

## 2. Archivos creados

| Archivo | Propósito |
|---------|-----------|
| `backend/app/db/transaction.py` | `TransactionMiddleware`: confirma la conexión antes de enviar la respuesta (§4.4) |
| `backend/tests/test_transaction.py` | 2 pruebas de borde transaccional (visibilidad de la escritura al recibir 2xx) |
| `backend/.dockerignore`, `frontend/.dockerignore` | Contexto de build limpio |
| `frontend/components/UsagePanel.tsx` | Panel de uso, cuotas y jobs por estado (§18) |
| `docs/reports/FASE_12_REPORT.md` | Este informe |
| `docs/test-runs/20261018-container-e2e.md` | Registro de verificación build/run E2E (§19.6) |

## 3. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `backend/requirements.txt` | `python-multipart==0.0.32` (arranque real en contenedor) |
| `backend/app/api/deps.py` | `get_conn` registra la conexión en `request.state.db_conn` |
| `backend/app/main.py` | Monta `TransactionMiddleware` (interno, junto al router) |
| `backend/app/services/usage_service.py`, `backend/app/api/v1/observability.py`, `backend/app/api/v1/router.py` | (Fase 12.1) uso/cuotas y capacidades en `/meta` |
| `docs/DEPLOYMENT.md`, `docs/COMMERCIAL_READINESS.md`, `.env.example` | (Fase 12.1) despliegue, preparación comercial y variables |
| `frontend/lib/api.ts` | Tipos `Usage`/`Metrics`/`QuotaItem` y `getUsage`/`getMetrics` |
| `frontend/app/dashboard/page.tsx` | Monta `UsagePanel` |
| `docs/PROGRESS.md`, `docs/FASE_0_WBS.md` | W12.1–W12.3 y roadmap |

## 4. Componentes reutilizados

- `docs/DEPLOYMENT.md`, `docs/COMMERCIAL_READINESS.md` (W12.1).
- `services/usage_service.py` (cuotas/uso/métricas) y `/observability/*`.
- `docker-compose.yml` y `Dockerfile`s de backend/frontend (Fase 3).
- Capa de repositorio/`Database` (`app/db/database.py`).

## 5. Funcionalidades implementadas

- **Verificación de despliegue real**: `docker compose build` + `up -d` con las
  dos imágenes y healthchecks (`/health`, `/health/ready`) y flujo vertical E2E
  dentro de contenedores.
- **Corrección del borde transaccional**: la confirmación de escrituras ocurre
  antes de devolver la respuesta HTTP, eliminando 401/pérdidas de visibilidad
  intermitentes al reutilizar la sesión recién creada.
- **Contexto de build reproducible** (`:0`): `.dockerignore` por servicio.
- Uso, cuotas y métricas por API (W12.1) y capacidades declaradas en `/meta`.
- **Panel de uso y monitor de jobs** en la UI (§18): proyectos, artefactos,
  almacenamiento, hallazgos, jobs activos/totales/finalizados, duración media,
  barras de cuota y jobs por estado (`UsagePanel`).
- **E2E de UI con navegador real** (Playwright/Chromium, W12.4): registro →
  dashboard/uso → proyecto → subida → análisis → paneles de resultados.
- **Corrección de la clave primaria del grafo** (defecto detectado por el E2E):
  `architecture_nodes/edges/dependency_records` pasan a `PRIMARY KEY
  (analysis_id, id)` con migración idempotente a `SCHEMA_VERSION = 5`, de modo que
  análisis repetidos sobre contenido equivalente no colisionan.

## 6. Pruebas ejecutadas

- `cd platform/backend && python3 -m pytest` → registro
  `docs/test-runs/20261018-180513.{json,md}`.
- Verificación de contenedores → `docs/test-runs/20261018-container-e2e.md`.
- E2E de UI con navegador → `docs/test-runs/20261018-ui-e2e-playwright.md`.

## 7. Resultados reales

- **92 passed, 0 failed, 0 errors, 0 skipped**.
- Contenedores: 2/2 imágenes construidas, 2/2 servicios arriba, `/health` 200,
  `/health/ready` 200 (DB ok), frontend 200; flujo completo `job_status=COMPLETED`
  con 3 hallazgos y `jobs_total=1`.
- E2E de UI: 1/1 escenario aprobado, ejecutado dos veces sobre la misma base de
  datos persistente (idempotencia entre análisis verificada).
- 72 peticiones autenticadas consecutivas tras la corrección: 0 fallos.
- Frontend: `npm run typecheck` sin errores; `npm run build` OK; imagen de
  frontend reconstruida y `/dashboard` → 200 en contenedor.

## 8. Pruebas no ejecutadas

- Pasarela de pago / facturación real: `PROPOSED_NOT_IMPLEMENTED` (decisión de
  negocio y credenciales).
- Escala horizontal (Redis/Postgres): `PROPOSED_NOT_IMPLEMENTED` (fuera del MVP).

## 9. Problemas pendientes

- Escalabilidad (cola externa, Postgres, limitador de tasa compartido) fuera del
  alcance del MVP.
- Costes/facturación sin implementar.

## 10. Riesgos

- SQLite y jobs en proceso no escalan horizontalmente (documentado en
  `docs/LIMITATIONS.md`).
- Secretos por defecto en `docker-compose.yml` (`change-me-in-production`);
  deben sustituirse en producción vía `SIREP_SECRET_KEY`.

## 11. Instrucciones para reproducir

```bash
cd platform
docker compose build
FRONTEND_PORT=3100 SIREP_ALLOWED_ORIGINS=http://localhost:3100 docker compose up -d
curl -s http://127.0.0.1:8000/health/ready
cd backend && python3 -m pytest
cd ../frontend && npm install && npx playwright install chromium
E2E_BASE_URL=http://localhost:3100 npx playwright test
```

## 12. Próxima fase

- Escalabilidad (§14/§21): limitador de tasa y cola compartidos (Redis) y
  migración a PostgreSQL tras la capa de repositorio.
- Ampliar §6 de la Fase 8 a más formatos de §6.1 cuando haya herramientas y
  pruebas; §6.3 avanzado sigue bloqueado por ejecución aislada.
