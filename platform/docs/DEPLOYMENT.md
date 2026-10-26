# Despliegue (§21 Fase 12, §22)

Guía operativa para ejecutar la plataforma. Estado honesto: el despliegue
validado es **local**; la ejecución end-to-end en contenedores está definida pero
marcada `TEST_NOT_RUN` (ver `docs/LIMITATIONS.md`).

## 1. Requisitos

- Python 3.12, Node.js 22 (para el frontend y el bridge TS/JS).
- Opcional: `@babel/parser` localizado automáticamente (o `SIREP_BABEL_PARSER`).
- Opcional: Docker 24+ para el despliegue en contenedores.

## 2. Configuración

Toda la configuración se toma del entorno con prefijo `SIREP_`. Copie
`backend/.env.example` a `backend/.env` y ajuste. Nunca incluya secretos reales en
el repositorio. Variables relevantes por área:

| Área | Variables |
|------|-----------|
| Producto | `SIREP_PRODUCT_NAME`, `SIREP_PRODUCT_SHORT_NAME`, `SIREP_PRODUCT_SLUG` |
| Persistencia | `SIREP_DATABASE_PATH`, `SIREP_DATABASE_URL` (PostgreSQL opcional), `SIREP_STORAGE_ROOT` |
| Ingesta | `SIREP_MAX_UPLOAD_BYTES`, `SIREP_MAX_EXTRACTED_BYTES`, ... |
| REA | `SIREP_REA_BINARY`, `SIREP_REA_ENABLED`, `SIREP_REA_TIMEOUT_SECONDS` |
| Seguridad (§14) | `SIREP_EXECUTION_PROFILE`, `SIREP_HIGH_RISK_*`, `SIREP_SANDBOX_*`, `SIREP_OUTBOUND_ALLOWED_HOSTS` |
| Cuotas (§14) | `SIREP_ORG_MAX_PROJECTS`, `SIREP_ORG_MAX_STORAGE_BYTES`, `SIREP_ORG_MAX_CONCURRENT_JOBS` |
| Tasa | `SIREP_RATE_LIMIT_API_PER_MINUTE`, `SIREP_RATE_LIMIT_AUTH_PER_MINUTE`, `SIREP_RATE_LIMIT_BACKEND` |
| Cola (§4.3) | `SIREP_JOB_QUEUE`, `SIREP_WORKER_*`, `SIREP_JOB_STALE_AFTER_SECONDS`, `SIREP_JOB_MAX_ATTEMPTS` |
| IA (NIM) | `SIREP_NIM_BASE_URL`, `SIREP_NIM_MODEL`, `SIREP_NIM_API_KEY`, `SIREP_NIM_TIMEOUT_SECONDS` |

La plataforma usa **NVIDIA NIM como único proveedor de IA** (no integra Gemini).
Las credenciales se cargan desde `backend/.env` (local, no versionado) o desde el
entorno de Compose; nunca se escriben en el código ni en los logs.

Verificación de la integración (real):

```
cd platform/backend
python -m scripts.verify_nim            # RESULT: TEST_PASSED
# o vía API autenticada: POST /api/v1/migrations/nim/verify
```

Generación/reparación de código con NIM (§10), con verificación de sintaxis:

```
# API (rol developer; requiere ai_consent=true):
#   POST /api/v1/analyses/{analysis_id}/generations
#   {"instruction": "...", "target_path": "src/app.py", "mode": "repair", "ai_consent": true}
# E2E en vivo (register→project→analysis→generación→aprobar→aplicar→validar):
SIREP_API_BASE_URL=http://127.0.0.1:8000 python -m scripts.verify_nim_generation
```

## 3. Arranque local

```
cd platform/backend
python3 -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Sonda de vida y preparación
curl -s localhost:8000/health
curl -s localhost:8000/health/ready     # {"status":"ready","checks":{"database":"ok"}}
# Metadatos (perfil de ejecución, cuotas)
curl -s localhost:8000/api/v1/meta
```

Frontend:

```
cd platform/frontend
npm install
npm run build
npm run start        # o: npm run dev
```

## 4. Contenedores

```
cd platform
docker compose config          # validado
docker compose up --build      # TEST_PASSED (docs/test-runs/20261018-container-e2e.md)
```

Servicios definidos: `backend` (python:3.12-slim) y `frontend` (node:22-slim).
Build y ejecución verificados: `/health` y `/health/ready` 200, flujo vertical
`COMPLETED` en contenedor.

- Puertos y origen CORS parametrizables (evitan conflictos con otros servicios
  del host):
  ```
  FRONTEND_PORT=3100 SIREP_ALLOWED_ORIGINS=http://localhost:3100 docker compose up -d
  ```
- E2E de UI con navegador real (Playwright):
  ```
  cd frontend && npm install && npx playwright install chromium
  E2E_BASE_URL=http://localhost:3100 npx playwright test
  ```

### PostgreSQL opcional (§4.4)

Por defecto la plataforma usa SQLite. Para usar PostgreSQL:

```
cd platform
docker compose --profile postgres up -d db
export SIREP_DATABASE_URL=postgresql://sirep:sirep@db:5432/sirep
docker compose up -d backend worker
```

La misma capa de repositorio se ejecuta sobre PostgreSQL (adaptador de dialecto).
Verificado contra PostgreSQL 16 dentro del contenedor:
```
docker compose run --rm -T \
  -e SIREP_DATABASE_URL=postgresql://sirep:sirep@db:5432/sirep \
  -e SIREP_TEST_POSTGRES_URL=postgresql://sirep:sirep@db:5432/sirep \
  backend python -m pytest tests/test_postgres_persistence.py -q
# TEST_PASSED (docs/test-runs/20261018-postgresql-persistence.md)
```
  Resultado: `TEST_PASSED` (`docs/test-runs/20261018-ui-e2e-playwright.md`).

## 5. Observabilidad operativa

- Cada respuesta incluye `X-Request-ID` (se propaga el entrante si existe).
- Logs estructurados JSON por petición: `method`, `path`, `status`,
  `duration_ms`, `request_id`; secretos redactados (§14.6).
- `GET /health` (vida) y `GET /health/ready` (preparación con comprobación de BD).
- `GET /api/v1/observability/metrics` — estados de jobs y duración media.
- `GET /api/v1/observability/usage` — uso y cuotas de la organización.

## 6. Copias de seguridad y retención

- La base SQLite vive en `SIREP_DATABASE_PATH`; el almacenamiento de artefactos
  en `SIREP_STORAGE_ROOT`. Haga copia de ambos de forma consistente.
- La retención de artefactos se controla con `SIREP_WORKSPACE_RETENTION_SECONDS`.
  La purga se ejecuta de forma periódica en el servicio `worker`
  (`SIREP_RETENTION_PURGE_INTERVAL_SECONDS`, <=0 la desactiva). En modo `inline`
  debe invocarse `purge_expired_artifacts` manualmente (§14.6).

## 7. Escalado

- **Cola de trabajos externa** (`SIREP_JOB_QUEUE=external`, predeterminado en
  `docker-compose.yml`): la API encola y el servicio `worker`
  (`python -m app.worker`) ejecuta. Se pueden añadir réplicas del worker
  (`docker compose up -d --scale worker=3`) sobre la misma base. El reclamo es
  atómico y los trabajos huérfanos se reencolan
  (`SIREP_JOB_STALE_AFTER_SECONDS`, `SIREP_JOB_MAX_ATTEMPTS`).
  En modo `inline` los jobs corren en un `ThreadPoolExecutor` del proceso de la API.
- **Límites de tasa**: `SIREP_RATE_LIMIT_BACKEND=memory` (una instancia) o
  `database` (compartido entre instancias; predeterminado en compose).
- La persistencia SQLite soporta el escenario multi-proceso en WAL, pero para
  concurrencia alta debe migrarse a PostgreSQL; la capa de repositorios ya abstrae
  el acceso (pendiente el adaptador de dialecto).
