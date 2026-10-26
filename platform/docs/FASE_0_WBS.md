# FASE 0 — Análisis, Extracción y Mapeo del documento "SAAS REA"

> Fuente soberana: `/Users/edisonrodriguez/Documents/SAAS REA.pdf` (44 páginas).
> Texto extraído verificado: `platform/docs/source/SAAS_REA_clean.txt`.
> Este documento es el WBS/Roadmap derivado **literalmente** del PDF. Cada ítem cita la sección de origen.
> Estado permitido por el PDF (§23): `IMPLEMENTED`, `PARTIALLY_IMPLEMENTED`, `PROPOSED_NOT_IMPLEMENTED`, `TEST_PASSED`, `TEST_FAILED`, `TEST_NOT_RUN`, `BLOCKED`.

## WBS — Desglose estructurado

| ID | Sección PDF | Requisito | Artefacto entregable | Estado inicial |
|----|-------------|-----------|----------------------|----------------|
| R-00 | §0 Misión | Plataforma SaaS (análisis/reconstrucción/reparación/migración) con nombre configurable | `platform/` + `core/config` con nombre de producto parametrizable | PROPOSED_NOT_IMPLEMENTED |
| R-01 | §1 Principios | Veracidad técnica, evidencia trazable, cambios reversibles, incremental, justificación | `docs/`, Evidence model, ChangeManagement | PROPOSED_NOT_IMPLEMENTED |
| R-02 | §2.1 Análisis | Representación estructurada de arquitectura/componentes/dependencias | `engines/source_analysis` + `ArchitectureGraph` | PROPOSED_NOT_IMPLEMENTED |
| R-03 | §2.5/§12 Migración | Migración asistida Google Gemini → NVIDIA NIM | `adapters/gemini_detector`, `nim_compatibility`, `migration` | PROPOSED_NOT_IMPLEMENTED |
| R-04 | §2.6/§6 Compilados | Análisis de aplicaciones compiladas (ELF/PE/Mach-O/.NET/etc.) | `BinaryAnalysisEngine` (adaptadores por formato) | PROPOSED_NOT_IMPLEMENTED |
| R-05 | §3 Fase Cero | Auditoría empírica de REA + informe + integración desacoplada | `docs/audit/REA_AUDIT.md`, `adapters/rea` | PROPOSED_NOT_IMPLEMENTED |
| R-06 | §4.1 Frontend | Next.js/TS/React/Tailwind, auth, orgs, proyectos, diffs, historial | `frontend/` | PROPOSED_NOT_IMPLEMENTED |
| R-07 | §4.2 Backend | Python/FastAPI/Pydantic, REST versionada, OpenAPI | `backend/app` | PROPOSED_NOT_IMPLEMENTED |
| R-08 | §4.3 Async | Colas, estados persistentes, reintentos, timeouts, cancelación, heartbeats | `services/jobs` + worker | PROPOSED_NOT_IMPLEMENTED |
| R-09 | §4.4 Persistencia | PostgreSQL + migraciones + almacenamiento de objetos | `models/` DB + `storage/` | PROPOSED_NOT_IMPLEMENTED |
| R-10 | §4.5 Artifacts | Metadata, SHA-256, MIME, retención, procedencia | `models/Artifact` + `engines/ingestion` | PROPOSED_NOT_IMPLEMENTED |
| R-11 | §5 SourceAnalysisEngine | Python/TS/JS; AST; símbolos, deps, env, entradas, pruebas | `engines/source_analysis` | PROPOSED_NOT_IMPLEMENTED |
| R-12 | §6 BinaryAnalysisEngine | Estático: formato, arch, hashes, símbolos, import/export, strings | `engines/binary_analysis` | PROPOSED_NOT_IMPLEMENTED |
| R-13 | §7 ArchitectureGraphEngine | Grafo G=(V,E) con procedencia y nivel de evidencia | `engines/graph` | PROPOSED_NOT_IMPLEMENTED |
| R-14 | §8 FunctionReconstructionEngine | Reconstrucción con estados de equivalencia | `engines/reconstruction` | PROPOSED_NOT_IMPLEMENTED |
| R-15 | §9 RepairEngine | Diagnóstico, parches, ≤3 iteraciones, límites | `engines/repair` | PROPOSED_NOT_IMPLEMENTED |
| R-16 | §10 FeatureDevelopmentEngine | Solicitud en lenguaje natural → plan → implementación | `engines/feature_dev` | PROPOSED_NOT_IMPLEMENTED |
| R-17 | §11 MigrationEngine | Reglas versionadas por adaptador | `engines/migration` | PROPOSED_NOT_IMPLEMENTED |
| R-18 | §12 GeminiToNIM | Detección, matriz de compatibilidad, diffs, pruebas | `engines/migration/gemini_to_nim` | PROPOSED_NOT_IMPLEMENTED |
| R-19 | §13 AI Provider Layer | Abstracción de proveedores, consentimiento, redacción | `adapters/ai_providers` | PROPOSED_NOT_IMPLEMENTED |
| R-20 | §14 Seguridad | Perfiles de ejecución, aislamiento, archivos, red, agente, privacidad | `core/security`, sandbox | PROPOSED_NOT_IMPLEMENTED |
| R-21 | §15 ChangeManagementEngine | Workspace, hashes, manifiesto, diff, aprobación, reversión | `engines/change_management` | PROPOSED_NOT_IMPLEMENTED |
| R-22 | §16 Modelo de datos | 21 entidades mínimas | `models/` (SQLAlchemy/DB) | PROPOSED_NOT_IMPLEMENTED |
| R-23 | §17 API REST | Endpoints versionados + validación/autorización/errores/paginación | `api/v1` | PROPOSED_NOT_IMPLEMENTED |
| R-24 | §18 Dashboard/UX | 20 páginas mínimas + estados + SSE/WS | `frontend/` | PROPOSED_NOT_IMPLEMENTED |
| R-25 | §19 Testing | Unitarias, integración, seguridad, reconstrucción, migración | `backend/tests` + `frontend` tests | PROPOSED_NOT_IMPLEMENTED |
| R-26 | §20 MVP | Flujo estático completo (17 criterios) | flujo vertical Fase 2 | PROPOSED_NOT_IMPLEMENTED |
| R-27 | §21 Plan 12 fases | Secuencia de entrega | `docs/ROADMAP.md` | PROPOSED_NOT_IMPLEMENTED |
| R-28 | §22 Documentación | README, arquitectura, instalación, guías, threat model | `docs/` | PROPOSED_NOT_IMPLEMENTED |
| R-29 | §23 Informe por fase | 12 puntos + estados explícitos | `docs/reports/FASE_*.md` | PROPOSED_NOT_IMPLEMENTED |
| R-30 | UX/UI (§ anexo) | Sistema visual, tokens, AppShell, componentes, estados | `frontend/` | PROPOSED_NOT_IMPLEMENTED |

## Contratos mínimos del primer flujo vertical (PDF §24 Paso 4)

```
Artifact Ingestion → Safe Extraction → Static Analysis → Findings → Architecture Graph → Persisted Results
```

## Dependencias y control de bloqueo

- **Sin dependencias circulares** detectadas en el PDF.
- **Datos críticos faltantes** (el PDF los delega explícitamente al entorno / §3.2 y §21):
  1. Motor de colas: el PDF permite Celery/ARQ+Redis *"después de evaluar las necesidades reales"*. → Decisión: MVP con ejecución asíncrona en proceso + persistencia de estado; Redis/Celery se añade en Fase 11 cuando haya necesidad demostrable.
  2. Persistencia: Postgres de referencia; el PDF permite adaptar al entorno (§4.4). → Decisión MVP: SQLite con capa de repositorio abstraída para migrar a Postgres.
  3. Proveedores de IA: requieren credenciales (bloqueo externo). → Se implementa la abstracción y mocks; pruebas remotas marcadas `BLOCKED`/`NOT_RUN`.
  4. NVIDIA NIM remoto: requiere API key + endpoints reales. → Configurable; validación remota opcional.

## Roadmap de fases (PDF §21) → mapeo a ejecución

| Fase PDF | Contenido | Estado de ejecución |
|----------|-----------|---------------------|
| 1 | Auditoría de REA | Completada |
| 2 | Primer flujo vertical | Completada |
| 3 | Grafo y análisis ampliado | Completada |
| 4 | Gestión de cambios | Completada (§15 backend + UI) |
| 5 | Reparación automatizada | Pendiente (§9; bloqueada por ejecución aislada; ver `FASE_5_8_REPORT.md`) |
| 6 | Desarrollo de nuevas funciones | Pendiente (§10; bloqueada por IA real + verificación) |
| 7 | Reconstrucción de funciones | Pendiente (§8; bloqueada por ejecución aislada) |
| 8 | Análisis de aplicaciones compiladas | En curso (§6.2 estático `TEST_PASSED`; §6.3 avanzado bloqueado por ejecución aislada) |
| 9 | Migración tecnológica | En curso (§11 reglas versionadas + plan + UI) |
| 10 | Gemini → NVIDIA NIM | En curso (detector+matriz+plan+UI; integración remota pendiente) |
| 11 | Seguridad y escalabilidad | Completada (perfiles, sandbox, red, redacción, retención, observabilidad, cuotas, §19.6) |
| 12 | Preparación comercial | En curso (docs + uso/cuotas por API + build/run de contenedores `TEST_PASSED`; facturación propuesta) |

## Estado consolidado (actualizado tras Fase 11)

| ID | Estado | Evidencia |
|----|--------|-----------|
| R-00 | IMPLEMENTED | `backend/app/core/config.py` (nombre parametrizable) |
| R-01 | PARTIALLY_IMPLEMENTED | Modelo de evidencia y niveles; reversibilidad local en `change_service.py` (§15); efectos externos documentados |
| R-02 | PARTIALLY_IMPLEMENTED | Análisis estático Python + JS/TS + binarios §6.2 (`engines/binary_analysis/`) |
| R-03 | PARTIALLY_IMPLEMENTED | `engines/migration/` (detector AST/patrones, matriz §12.2, plan+diffs, fuentes §12.3); integración remota `BLOCKED` |
| R-04 | PARTIALLY_IMPLEMENTED | ELF/PE/Mach-O/Java estático; §6.3 (desensamblado/decompilación/ejecución controlada) pendiente (ver `docs/reports/FASE_8_REPORT.md`) |
| R-05 | IMPLEMENTED | `docs/audit/REA_AUDIT.md`, `backend/app/adapters/rea_adapter.py` |
| R-06 | PARTIALLY_IMPLEMENTED | `frontend/` (auth, proyectos, subida, resultados, diffs de cambios); faltan historial y páginas restantes |
| R-07 | IMPLEMENTED | `backend/app/api/v1` + OpenAPI en `/docs` |
| R-08 | PARTIALLY_IMPLEMENTED | `services/job_runner.py` (estado persistido, cancelación); sin cola distribuida |
| R-09 | PARTIALLY_IMPLEMENTED | SQLite + capa de repositorios; sin Postgres/objetos |
| R-10 | IMPLEMENTED | `engines/ingestion`, `models/Artifact` |
| R-11 | PARTIALLY_IMPLEMENTED | Python + TS/JS; sin más lenguajes |
| R-12 | PARTIALLY_IMPLEMENTED / TEST_PASSED | `engines/binary_analysis/` (ELF/PE/Mach-O/Java/WASM/DEX/PYC/ZIP-JAR-APK/COFF/ar; formato, arch, hash, símbolos, libs, strings, comparación §6.2); §6.3 pendiente |
| R-13 | IMPLEMENTED | `engines/graph/architecture_graph.py` |
| R-14 | PROPOSED_NOT_IMPLEMENTED | §8; bloqueada por falta de ejecución aislada (`docs/reports/FASE_5_8_REPORT.md`) |
| R-15 | PROPOSED_NOT_IMPLEMENTED | §9; bloqueada por falta de ejecución aislada (`docs/reports/FASE_5_8_REPORT.md`) |
| R-16 | PROPOSED_NOT_IMPLEMENTED | §10; bloqueada por IA real + verificación (`docs/reports/FASE_5_8_REPORT.md`) |
| R-17 | PARTIALLY_IMPLEMENTED | `engines/migration/rules.py` (reglas versionadas §11); resto de tecnologías pendiente |
| R-18 | PARTIALLY_IMPLEMENTED | `engines/migration/{gemini_detector,nim_compat,planner}.py`; pruebas de integración NIM `BLOCKED` |
| R-19 | PARTIALLY_IMPLEMENTED | `engines/analysis/integrations.py` (clasificación) + config |
| R-20 | PARTIALLY_IMPLEMENTED | Perfiles (`core/execution_profiles.py`), límites (`core/sandbox.py`), guard de red/SSRF (`core/net_guard.py`), redacción, retención/borrado, observabilidad (`core/observability.py`) y cuotas/tasa (`services/usage_service.py`, `core/rate_limit.py`); ejecución dinámica aislada real (contenedor/VM) pendiente |
| R-21 | PARTIALLY_IMPLEMENTED | §15: workspaces/hashes/diffs/aprobación/reversión vía `services/change_service.py`; UI en W4.2 |
| R-22 | PARTIALLY_IMPLEMENTED | Subconjunto de entidades persistidas |
| R-23 | IMPLEMENTED | Endpoints versionados, errores normalizados, paginación |
| R-24 | PARTIALLY_IMPLEMENTED | 3 vistas funcionales; faltan páginas del set completo |
| R-25 | TEST_PASSED | `backend/tests` (89 pruebas en verde); registro de ejecuciones en `docs/test-runs/` |
| R-26 | IMPLEMENTED / TEST_PASSED | Flujo vertical E2E verificado |
| R-27 | IMPLEMENTED | Este roadmap |
| R-28 | IMPLEMENTED | `docs/ARCHITECTURE.md`, `THREAT_MODEL.md`, `LIMITATIONS.md`, `DEPLOYMENT.md`, `COMMERCIAL_READINESS.md`, READMEs |
| R-29 | IMPLEMENTED | `docs/reports/FASE_{1,2,3,4,5_8,8,9_10,11}_REPORT.md` |
| R-30 | PARTIALLY_IMPLEMENTED | Tokens visuales y componentes base en `frontend/components` |

---

## Implementation Validator — Avance (2026-10-22)

- Motor de validación operativo: adaptadores `file_exists` y `pytest` (JUnit XML + exit-code parsing robusto).
- `verify_validator.py` usa `get_settings()` y acepta `--profile` para seleccionar `ISOLATED_TEST_EXECUTION`.
- Tests unitarios añadidos para `_interpret_pytest`, `_read_junit_counts` y casos borde (códigos 0,1,5, señales, salida sin resumen).
- Entorno VS Code/Pylance configurado (`.vscode/settings.json` con `python-envs.pythonProjects`).
- Ejecución en perfil aislado: **11 PASS / 1 BLOCKED** (REQ-010 requiere PostgreSQL). Suite completa backend **155 passed, 6 skipped**.
- Próximo: modelos SQLAlchemy y migración Alembic para tablas del validator (Fase A).
