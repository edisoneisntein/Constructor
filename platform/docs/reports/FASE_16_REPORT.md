# Informe Fase 16 — Persistencia PostgreSQL (§4.4, §23)

## 1. Objetivo
Habilitar PostgreSQL como motor de persistencia manteniendo **una sola** capa de
repositorios, sin reescribir la lógica de negocio, y verificarlo con pruebas
reales contra un PostgreSQL 16 en contenedor.

## 2. Archivos creados
- `app/db/pg.py` — adaptador de conexión PostgreSQL (traducción de marcadores y
  `INSERT OR IGNORE`; filas tipo diccionario).
- `tests/test_postgres_persistence.py` — 4 pruebas de integración (gated por
  `SIREP_TEST_POSTGRES_URL`).
- `docs/test-runs/20261018-postgresql-persistence.md`.

## 3. Archivos modificados
- `app/db/database.py` — `Database` con dos dialectos (`is_postgres`,
  `is_ephemeral`, `label`), `_new_pg_connection`, migraciones con guardia de
  dialecto (`_column_names` por `information_schema`).
- `app/core/config.py` — `database_url` (`SIREP_DATABASE_URL`).
- `app/db/session.py` — `Database(database_url or database_path)`.
- `app/api/deps.py`, `app/core/rate_limit.py`, `app/worker.py`,
  `app/services/analysis_service.py` — cierre de conexión por `is_ephemeral`
  (uniforme entre dialectos).
- `backend/requirements.txt` — `psycopg[binary]==3.2.3`.
- `docker-compose.yml` — servicio `db` (perfil `postgres`) y passthrough
  `SIREP_DATABASE_URL`.
- `backend/.env.example`; `docs/{PROGRESS,LIMITATIONS,ARCHITECTURE,DEPLOYMENT}.md`.

## 4. Componentes reutilizados
- Toda la capa de repositorios (`repositories.py`) y los servicios existentes,
  **sin cambios**: el adaptador traduce el SQL existente.
- Cola externa (`worker` + `claim_next_job` con `UPDATE ... RETURNING`),
  rate limiter en base de datos (`ON CONFLICT ... RETURNING`), gestión de cambios.

## 5. Funcionalidades implementadas
- Selección de dialecto por `SIREP_DATABASE_URL` (`postgresql://`), con SQLite
  como valor por defecto (retrocompatible).
- Traducción automática: `?`→`%s`, `:name`→`%(name)s`,
  `INSERT OR IGNORE INTO`→`INSERT ... ON CONFLICT DO NOTHING`; filas
  `row["col"]` homogéneas con `sqlite3.Row`.
- Inicialización de esquema idempotente en ambos motores.
- Servicio `db` en Compose (perfil `postgres`).

## 6. Pruebas ejecutadas
- Suite por defecto (SQLite): `118 passed, 6 skipped` (sin regresiones).
- Suite con PostgreSQL: `122 passed, 2 skipped`
  (`docs/test-runs/20261018-192347`).
- Pruebas PG dentro de la imagen backend contra el servicio `db`: `4 passed`.

## 7. Resultados reales
- PostgreSQL 16: esquema creado; flujo vertical completo
  (registro→proyecto→artefacto→análisis→hallazgos/grafo→cambio
  aprobar/aplicar/validar) OK; rate limiter en BD OK; reclamo de trabajo del
  worker OK (`UPDATE ... RETURNING`).

## 8. Pruebas no ejecutadas
- Pooling de conexiones y réplicas de lectura: `PROPOSED_NOT_IMPLEMENTED`.
- Migración de datos SQLite→PostgreSQL: no implementada (esquemas compatibles).

## 9. Problemas pendientes
- Se usan credenciales de ejemplo (`sirep/sirep`) solo en pruebas; producción debe
  usar secretos gestionados.
- Cada petición abre una conexión (sin pool); suficiente para el MVP.

## 10. Riesgos
- Diferencias semánticas sutiles entre dialectos podrían aparecer con SQL futuro;
  mitigado por las pruebas de integración. Sin `SIREP_DATABASE_URL`, el
  comportamiento es idéntico al anterior (SQLite).

## 11. Instrucciones para reproducir
```bash
cd platform
docker compose --profile postgres up -d db
SIREP_TEST_POSTGRES_URL=postgresql://sirep:sirep@127.0.0.1:5432/sirep \
  (cd backend && python3 -m pytest tests/test_postgres_persistence.py -q)
```

## 12. Próxima fase
- **Verificación dinámica de código generado (§10/§14.1)**: requiere aprobación de
  seguridad para ejecutar código no confiable en sandbox aislado.
- Backend Redis opcional para el limitador; modelado de costes/facturación.
