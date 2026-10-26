# Registro de verificación — E2E de UI con navegador (§18, §19.6, §21 Fase 12)

- **ID**: 20261018-ui-e2e-playwright
- **Fecha**: 2026-10-18 (UTC-05:00)
- **Tipo**: prueba end-to-end de interfaz con navegador real (Playwright/Chromium),
  contra contenedores en ejecución (no forma parte de `pytest`).
- **Comando**:
  ```bash
  cd platform/frontend
  E2E_BASE_URL=http://localhost:3100 npx playwright test
  ```
- **Herramientas y versiones**: `@playwright/test` 1.56.0, Chromium Headless Shell
  141.0.7390.37 (playwright build v1194), Node v22.23.2, Next 15.5.28, React
  19.3.1, FastAPI 0.139.0 (contenedor), Docker Compose v5.4.0.
- **Resultado**: `TEST_PASSED`
- **Resumen**: 1/1 escenario E2E de UI aprobado; ejecutado dos veces consecutivas
  sobre la misma base de datos persistente (idempotencia entre análisis).
- **Passed**:
  1. Registro de usuario + organización desde la UI (`/`), redirección a
     `/dashboard`.
  2. Panel «Uso de la organización» visible (W12.3).
  3. Creación de proyecto y navegación a `/projects/{id}`.
  4. Subida de `e2e/fixtures/sample-project.zip` (`sample-project.zip` listado).
  5. Inicio de análisis estático → estado `COMPLETED`, sección «3. Resultados».
  6. Paneles «Hallazgos», «Grafo de arquitectura» y «Análisis de binarios»
     renderizados.
  7. Segunda ejecución del mismo escenario en la misma BD → `COMPLETED`
     (valida la corrección de la clave primaria compuesta, ver diagnóstico).
- **Failed**: 0
- **Not run**: 0
- **Diagnóstico / defectos corregidos**:
  - **Defecto real detectado por el E2E**: `internal_error — UNIQUE constraint
    failed: architecture_nodes.id`. Causa: los identificadores de nodo son
    deterministas (`file::ruta`, `sym::ruta::name`, …) y `architecture_nodes(id)`
    era clave primaria simple; un segundo análisis con contenido equivalente
    reinsertaba los mismos ids. Corrección: clave primaria compuesta
    `PRIMARY KEY (analysis_id, id)` en `architecture_nodes`, `architecture_edges`
    y `dependency_records`, con migración idempotente a `SCHEMA_VERSION = 5`
    (`_migrate_graph_composite_keys` en `app/db/database.py`). Regresión cubierta
    por `tests/test_api_flow.py::test_multiple_analyses_same_content_do_not_collide`.
  - **Accesibilidad**: etiquetas del formulario de acceso sin asociación
    (`htmlFor`/`id`); se añadieron `id` a los campos (`auth-email`,
    `auth-password`, `auth-name`, `auth-org`) para permitir `getByLabel`.
  - **Conflicto de puerto**: el puerto 3000 del host estaba ocupado por otro
    proceso. Se parametrizó `FRONTEND_PORT` y `SIREP_ALLOWED_ORIGINS` en
    `docker-compose.yml` (`${FRONTEND_PORT:-3000}`, `${SIREP_ALLOWED_ORIGINS:-...}`);
    el E2E se ejecutó en `http://localhost:3100`.

Reproducir:

```bash
cd platform
colima start
FRONTEND_PORT=3100 SIREP_ALLOWED_ORIGINS=http://localhost:3100 docker compose up -d
cd frontend && npm install && npx playwright install chromium
E2E_BASE_URL=http://localhost:3100 npx playwright test
```
