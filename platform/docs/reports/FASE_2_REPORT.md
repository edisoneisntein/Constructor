# Informe de Fase 2 — Primer flujo vertical (§21, §23)

> Formato: los 12 puntos de §23 del PDF `SAAS REA.pdf`. Estados explícitos según §23.
> Fecha de ejecución: 2026-10-18.

## 1. Objetivo de la fase

Implementar el primer flujo vertical funcional del PDF (§24 Paso 4):

```
Artifact Ingestion → Safe Extraction → Static Analysis → Findings → Architecture Graph → Persisted Results
```

Con los entregables exigidos por §21 Fase 2: API, persistencia, ingesta segura,
análisis estático inicial, hallazgos, grafo serializable, interfaz mínima y
pruebas automatizadas.

## 2. Archivos creados

Backend (`platform/backend`):
- `app/core/`: `config.py`, `security.py`, `errors.py`, `logging.py`, `ids.py`
- `app/db/`: `database.py`, `repositories.py`, `session.py`
- `app/schemas/`: `models.py`
- `app/engines/ingestion/`: `safe_zip.py`, `artifact_store.py`
- `app/engines/analysis/`: `facts.py`, `language_detect.py`, `python_analyzer.py`,
  `js_analyzer.py`, `manifest_parser.py`, `integrations.py`, `source_analysis.py`
- `app/engines/graph/`: `architecture_graph.py`
- `app/adapters/`: `rea_adapter.py`
- `app/services/`: `job_runner.py`, `auth_service.py`, `analysis_service.py`
- `app/api/`: `deps.py`, `v1/{auth,organizations,projects,router}.py`
- `app/main.py`, `bridges/js_analyze.mjs`, `requirements.txt`, `.env.example`, `pytest.ini`
- `tests/`: `conftest.py`, `test_safe_zip.py`, `test_python_analyzer.py`, `test_source_analysis.py`, `test_api_flow.py`

Frontend (`platform/frontend`): `package.json`, `tsconfig.json`, `next.config.mjs`,
`tailwind.config.ts`, `postcss.config.mjs`, `app/{layout,page,globals.css}`,
`app/dashboard/page.tsx`, `app/projects/[id]/page.tsx`,
`components/{FindingsTable,GraphView}.tsx`, `lib/api.ts`.

Documentación: `docs/ARCHITECTURE.md`, `docs/THREAT_MODEL.md`, `docs/LIMITATIONS.md`,
`backend/README.md`, `docs/reports/FASE_2_REPORT.md`.

## 3. Archivos modificados

- `app/engines/analysis/js_analyzer.py`: ruta al bridge corregida (`parents[3]` en
  lugar de `parents[2]`); sin esto el análisis TS/JS quedaba bloqueado.
- `app/engines/analysis/source_analysis.py`: evaluación de `from X import Y`
  como `X.Y` para detectar integraciones de IA.
- `app/services/analysis_service.py` y `app/api/v1/projects.py`: helper
  `job_public` (público entre módulos).
- `frontend/package.json`: `next` 15.5.28, `react`/`react-dom` 19, `postcss` con
  `overrides` a `^8.5.30`.

## 4. Componentes reutilizados (§3.4)

- `@babel/parser` de REA (MIT) mediante el bridge Node `js_analyze.mjs`.
- CLI de REA v6.5.0 como subproceso aislado (`REAAdapter`).
- `ast` de la biblioteca estándar de Python.
- FastAPI, Pydantic, Next.js, React, Tailwind CSS.

## 5. Funcionalidades implementadas

- Ingesta segura de ZIP con defensas: path traversal, symlink, zip bomb, profundidad,
  número de entradas, tamaño por archivo y total; detección de MIME por bytes mágicos;
  almacenamiento direccionado por contenido (SHA-256).
- Análisis estático de Python (AST) y de JavaScript/TypeScript (bridge Node):
  imports, símbolos, funciones, clases, variables de entorno, rutas de API,
  puntos de entrada, patrones inseguros.
- Detección de integraciones de IA (Google Gemini detectado) con `DIRECT_EVIDENCE`.
- Parser de manifiestos (dependencias npm/pip) y grafo de arquitectura con
  distinción de aristas confirmadas vs inferidas.
- API REST versionada con autenticación por token opaco, organizaciones, roles
  (owner/admin/developer/viewer), scoping por organización, paginación y errores
  normalizados; OpenAPI en `/docs`.
- Jobs en segundo plano con estado persistido, progreso medible y cancelación.
- Exportación de informe en JSON y Markdown.
- Interfaz mínima: registro/login, organizaciones, proyectos, subida de ZIP,
  ejecución y seguimiento del análisis, hallazgos, grafo y exportación.

## 6. Pruebas ejecutadas

- `python3 -m pytest` → **22 passed** (unitarias, seguridad y E2E por API).
- E2E real con `uvicorn` y `curl`: registro → proyecto → subida → análisis →
  hallazgos → grafo → exportación. Salida observada: estado `COMPLETED`,
  `files_analyzed=2`, `languages={javascript, python}`, `finding_count=4`,
  `node_count=2`, `edge_count=2`.
- `npm run typecheck` → sin errores.
- `npm run build` → compilación correcta (4 rutas).
- `npm audit --omit=dev` → **0 vulnerabilidades**.

## 7. Resultados reales

Estados: **TEST_PASSED** para el análisis estático Python y JS/TS, la ingesta
segura, el flujo vertical E2E, la construcción del grafo y la interfaz.
**IMPLEMENTED** para API, persistencia y jobs. La detección de integración de IA
funciona de extremo a extremo con evidencia directa.

## 8. Pruebas no ejecutadas

- Suite de pruebas propia de REA → **TEST_NOT_RUN**.
- Llamadas remotas a proveedores de IA (NVIDIA NIM / Google) → **BLOCKED / TEST_NOT_RUN**
  (requieren credenciales; no se envían datos por defecto).
- Análisis de binarios (ELF/PE/Mach-O/.NET) → **PROPOSED_NOT_IMPLEMENTED**.
- Migración Gemini→NIM y gestión de cambios → **PROPOSED_NOT_IMPLEMENTED** (Fases 4, 10).

## 9. Problemas pendientes

- Cobertura de lenguajes limitada a Python y JS/TS.
- Persistencia en SQLite; falta migración a Postgres (§4.4).
- Jobs solo en proceso; no sobreviven a reinicio ni escalan horizontalmente (§4.3).
- Set de páginas del dashboard incompleto respecto a §18/UX (§24).
- Sin SSE/WebSockets (la UI usa sondeo); el PDF exige usar el mecanismo real
  disponible y no simular progreso: se documenta el sondeo.

## 10. Riesgos

- **Seguridad de ingesta**: mitigada y probada; riesgo residual en formatos no ZIP.
- **Dependencia de terceros**: `next`/`postcss` fueron actualizados por avisos de
  seguridad; se fijó `postcss` con `overrides`.
- **Ejecución de código**: se evitó por diseño (solo análisis estático).
- **Falsos positivos/negativos** en detección por AST: se mitiga con niveles de
  evidencia y trazabilidad por hallazgo.

## 11. Instrucciones para reproducir la validación

```bash
# Backend
cd platform/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest                     # 22 pruebas
uvicorn app.main:app --port 8000      # API + /docs

# Frontend
cd ../frontend
npm install
npm run typecheck && npm run build
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 npm run dev
```

## 12. Próxima fase

Fase 3 (PDF §21): navegación del grafo, más relaciones, mejores diagnósticos y
reglas de análisis. En paralelo se habilitará la Fase 10 (Gemini→NVIDIA NIM) con
su matriz de compatibilidad y diffs revisables, condicionada a credenciales.
