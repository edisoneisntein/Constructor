# Informe de Fase 11 — Seguridad, aislamiento y escalabilidad (§14, §19.3, §19.6, §23)

## 1. Objetivo

Según §21 Fase 11 y §14: dotar a la plataforma de controles verificables de
seguridad y aislamiento —perfiles de ejecución diferenciados, límites de recursos
para el código no confiable, control de red saliente, redacción de secretos y
retención/eliminación de artefactos— y de un registro reproducible de resultados
de pruebas (§19.6), manteniendo la regla de veracidad técnica: nada se declara
ejecutado si no lo está.

## 2. Archivos creados

| Archivo | Propósito |
|---------|-----------|
| `backend/app/core/execution_profiles.py` | Cinco perfiles de ejecución (§14.1); `HIGH_RISK_DYNAMIC_ANALYSIS` nunca automático |
| `backend/app/core/sandbox.py` | `preexec_fn` con `RLIMIT_CPU`/`RLIMIT_FSIZE`/`RLIMIT_NOFILE` (§14.2) |
| `backend/app/core/net_guard.py` | Control de red saliente y defensa SSRF (§14.4) |
| `backend/app/core/rate_limit.py` | Limitador de tasa en proceso (§14 controles multiusuario) |
| `backend/app/core/observability.py` | Middleware de correlación (`X-Request-ID`), medición y límites por petición (§14/§19.6) |
| `backend/app/services/usage_service.py` | Cuotas, uso y métricas por organización (§14/§21 Fase 11/12) |
| `backend/app/api/v1/observability.py` | Endpoints `observability/metrics` y `observability/usage` |
| `backend/tests/test_security.py` | 19 pruebas de seguridad (§19.3) |
| `backend/tests/test_observability.py` | 8 pruebas de observabilidad, cuotas y límites |
| `backend/scripts/record_test_run.py` | Registro real de ejecuciones de pruebas (§19.6) |
| `docs/DEPLOYMENT.md`, `docs/COMMERCIAL_READINESS.md` | Despliegue y preparación comercial (§21 Fase 12) |
| `docs/reports/FASE_11_REPORT.md` | Este informe |
| `docs/test-runs/*` (generados) | Registros JSON/Markdown + `INDEX.md` por ejecución |

## 3. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `backend/app/core/config.py` | Nuevos ajustes: `execution_profile`, `execution_allow_high_risk`, `sandbox_cpu_seconds`, `sandbox_max_memory_mb`, `sandbox_max_file_bytes`, `outbound_allowed_hosts`, `org_max_projects`, `org_max_storage_bytes`, `org_max_concurrent_jobs`, `rate_limit_api_per_minute`, `rate_limit_auth_per_minute` (+ lectura de entorno) |
| `backend/app/core/errors.py` | `QuotaExceededError` (403 `quota_exceeded`) y `RateLimitedError` (429 `rate_limited`) |
| `backend/app/core/observability.py` (nuevo) | — |
| `backend/app/core/rate_limit.py` (nuevo) | — |
| `backend/app/main.py` | Middleware de observabilidad/tasa; `GET /health/ready` |
| `backend/app/services/usage_service.py` (nuevo) | — |
| `backend/app/api/v1/observability.py` (nuevo) | — |
| `backend/app/db/repositories.py` | Agregados por organización (`count_projects`, `storage_bytes_used`, `count_active_jobs`, `count_jobs_by_status`, `usage_totals`, ...) |
| `backend/app/schemas/models.py` | `QuotaItem`, `UsageOut`, `MetricsOut` |
| `backend/tests/conftest.py` | Reset del limitador de tasa por test |
| `backend/app/core/logging.py` | Redacción ampliada: AWS, GitHub, Slack, JWT, claves privadas PEM, `private_key` GCP, `passwd/pwd/access_key` |
| `backend/app/core/net_guard.py` (nuevo) | — |
| `backend/app/services/analysis_service.py` | Borrado explícito y purga por retención de artefactos; propagación de límites de sandbox a REA y bridge Node |
| `backend/app/services/change_service.py` | Límites de sandbox en la reejecución de validación |
| `backend/app/engines/analysis/js_analyzer.py` | `run_js_bridge(..., limits=...)` → `preexec_fn` en el subproceso Node |
| `backend/app/engines/analysis/source_analysis.py` | Pasa `sandbox_limits` al bridge |
| `backend/app/adapters/rea_adapter.py` | `limits` en `REAAdapter`/`build_rea_adapter` → `preexec_fn` en la invocación de REA |
| `backend/app/db/repositories.py` | `mark_artifact_deleted`, `list_retained_artifacts` (filtra `deleted_at`) |
| `backend/app/api/v1/projects.py` | `DELETE /projects/{id}/artifacts/{artifact_id}` (rol developer) |
| `backend/app/api/v1/router.py` | Router de observabilidad; `/meta` publica perfil activo, límites, cuotas y capacidades (incl. `observability`, `organization_quotas`, `rate_limiting`, `billing`) |
| `backend/app/services/analysis_service.py` | Enforcimiento de cuotas (proyecto/almacenamiento/jobs) y registro de uso (`storage_bytes`, `analysis_runs`) |
| `backend/.env.example` | Perfiles, límites de sandbox y lista blanca de red |
| `docs/THREAT_MODEL.md`, `docs/ARCHITECTURE.md`, `docs/PROGRESS.md`, `docs/FASE_0_WBS.md` | Actualizados (R-20, R-25, R-29; Fase 11) |

## 4. Componentes reutilizados

- `api/deps.py`: `require_role` y aislamiento por `organization_id`.
- `core/errors.py`: `ForbiddenError` (nuevo uso para perfiles y red), `ValidationAppError`.
- `db/repositories`: patrón `new_id`/`utcnow_iso`/auditoría (`record_audit`).
- `engines/ingestion/artifact_store`: ruta de almacenamiento por hash para el borrado de bytes.
- `services/analysis_service`/`job_runner`: ejecución en segundo plano y cancelación ya existentes.

## 5. Funcionalidades implementadas

- **Perfiles de ejecución (§14.1)**: `STATIC_ANALYSIS` (por defecto), `CONTROLLED_DEPENDENCY_SETUP`,
  `ISOLATED_TEST_EXECUTION`, `RESTRICTED_NETWORK_INTEGRATION`, `HIGH_RISK_DYNAMIC_ANALYSIS`.
  `assert_profile_allowed` rechaza perfiles no habilitados; el de alto riesgo exige
  `SIREP_EXECUTION_ALLOW_HIGH_RISK=true` y **nunca** se habilita solo. Visibles en `/meta`.
- **Sandbox de recursos (§14.2)**: los subprocesos de REA y del bridge Node se lanzan con
  `RLIMIT_CPU`, `RLIMIT_FSIZE` y `RLIMIT_NOFILE`; `RLIMIT_AS` solo si se configura memoria
  (evita romper Node/V8). En plataformas sin `resource` los límites se omiten de forma explícita.
- **Control de red / SSRF (§14.4)**: se rechazan esquemas distintos de http/https, hosts
  loopback/privados/enlace local, rangos RFC1918/CGNAT/ULA y la IP de metadatos
  (169.254.169.254). Con lista blanca configurada, solo se permiten los hosts autorizados.
- **Redacción de secretos (§14.6)**: patrones para claves de Google, NVIDIA, AWS, GitHub,
  Slack, `Bearer`, JWT, claves privadas PEM y `private_key` de cuentas de servicio.
- **Retención y eliminación (§14.6)**: `DELETE /projects/{id}/artifacts/{artifact_id}` borra
  los bytes del almacenamiento, marca baja lógica (`deleted_at`, `validation_state=REJECTED`)
  y audita; `purge_expired_artifacts` elimina artefactos caducados según
  `workspace_retention_seconds`. El listado excluye los eliminados.
- **Registro de pruebas (§19.6)**: `scripts/record_test_run.py` ejecuta pytest, parsea el
  reporte JUnit XML real y escribe `docs/test-runs/<timestamp>.{json,md}` + `INDEX.md` con
  comando, versión de Python/pytest, plataforma, commit/rama/dirty y cola de salida.
- **Observabilidad (§14/§19.6)**: middleware que genera/propaga `X-Request-ID`, mide la
  duración y emite log estructurado por petición; `GET /health` y `GET /health/ready`
  (comprobación real de BD); `GET /api/v1/observability/metrics` (jobs por estado y
  duración media observable) y `GET /api/v1/observability/usage` (uso y cuotas).
- **Cuotas multiusuario (§14/§21 Fase 11/12)**: `403 quota_exceeded` al superar proyectos,
  almacenamiento o análisis concurrentes de la organización; límite de tasa en proceso
  con `429 rate_limited` y `Retry-After`. Uso acumulado en `usage_records`
  (`storage_bytes`, `analysis_runs`, `files_analyzed`).

## 6. Pruebas ejecutadas

```
cd platform/backend
python3 -m pytest                                   # suite completa
python3 scripts/record_test_run.py --label "Fase 11 — seguridad y escalabilidad"
```

- 19 pruebas nuevas (`tests/test_security.py`) + 8 (`tests/test_observability.py`).
- Total del proyecto: **69 passed** en ~11 s.
- Registro generado en `docs/test-runs/` (JSON + `.md` + `INDEX.md`).

## 7. Resultados reales

- Perfiles: el perfil por defecto es `STATIC_ANALYSIS`; `HIGH_RISK_DYNAMIC_ANALYSIS`
  queda fuera de `enabled_profiles` y `assert_profile_allowed` lanza `ForbiddenError`;
  con la bandera explícita se habilita. `/meta` refleja el perfil y los límites.
- Sandbox: `build_preexec` devuelve un `preexec_fn` invocable y `subprocess_limits`
  produce `{"preexec_fn": ...}` en POSIX (o `{}`/`None` donde no se soporta).
- SSRF: bloqueadas `localhost`, `127.0.0.1`, `169.254.169.254`, `10.0.0.5`,
  `192.168.1.10`, `[::1]`, `ftp://` y `file://`; permitida
  `https://integrate.api.nvidia.com/...`; la lista blanca rechaza hosts no autorizados.
- Redacción: los 10 ejemplos de secretos se sustituyen por `[REDACTED]`.
- Ingesta por contenido: un ZIP renombrado `logo.png` (MIME declarado `image/png`) se
  detecta como `application/zip`; bytes PNG declarados `application/zip` se rechazan (422).
- IDOR de artefactos: otra organización recibe 404; el propietario elimina el artefacto,
  sus bytes desaparecen del disco y el listado queda vacío.
- Retención: `purge_expired_artifacts` (retención 1 s, `now` futuro) elimina el artefacto
  exacto y lo retira del listado, con auditoría.
- Cancelación idempotente: dos `POST /cancel` devuelven 200; análisis/hallazgos/change-sets
  de otra organización devuelven 404.
- Observabilidad: `/health/ready` responde 200 con `database: ok`; toda respuesta incluye
  `X-Request-ID` (y se propaga el entrante); `/observability/usage` refleja proyectos,
  artefactos, bytes y cuotas consumidas; `/observability/metrics` suma estados de jobs.
- Cuotas: con límites bajos, `enforce_project_quota`/`enforce_storage_quota`/
  `enforce_concurrent_jobs_quota` lanzan `QuotaExceededError` (403) con el `resource`
  correcto; el limitador de tasa permite N y bloquea N+1 con `retry_after ≥ 1`; el
  middleware devuelve 429 `rate_limited` con `Retry-After` al exceder el límite de auth.

## 8. Pruebas no ejecutadas

- Ejecución dinámica real del código del cliente en contenedor/VM aislado: no existe
  motor que ejecute código aún; los perfiles y límites son control, no ejecución.
- Aplicación efectiva de `RLIMIT_*` sobre subprocesos reales: se verifica la construcción
  del `preexec_fn`, no el efecto del kernel (requiere binario externo que consuma recursos).
- `resolve=True` de `net_guard` (resolución DNS): implementado pero no cubierto por prueba
  por depender de DNS externo.
- E2E de navegador de la UI y build/run de Docker: `TEST_NOT_RUN` (limitación del MVP).

## 9. Problemas pendientes

- No hay recolección programada de la purga por retención (se invoca; sin planificador).
- El guard de red no resuelve DNS por defecto (riesgo de DNS rebinding documentado).
- `sandbox_max_memory_mb=0` por defecto: no hay límite de memoria hasta configurarlo.
- El `preexec_fn` no aplica en plataformas sin `resource` (p. ej. Windows).

## 10. Riesgos

- El aislamiento proporcionado es de proceso, no de contenedor: si en el futuro se
  habilita ejecución de código, debe añadirse aislamiento reforzado (§14.1/§14.2) antes.
- La lista blanca de red exige mantenimiento; una entrada comodín ampliaría superficie SSRF.
- El borrado de artefactos no elimina copias ya incorporadas a workspaces de cambios.

## 11. Instrucciones para reproducir

```
cd platform/backend
python3 -m pytest tests/test_security.py -v
python3 -m pytest                                            # 61 passed
python3 scripts/record_test_run.py --label "Fase 11"
uvicorn app.main:app --reload
curl -s localhost:8000/api/v1/meta | jq '.security'
# Perfil de alto riesgo (solo con bandera explícita):
SIREP_EXECUTION_ALLOW_HIGH_RISK=true SIREP_EXECUTION_PROFILE=HIGH_RISK_DYNAMIC_ANALYSIS uvicorn app.main:app
# Borrado de artefacto:
#   DELETE /api/v1/projects/{project_id}/artifacts/{artifact_id}
```

## 12. Próxima fase

**Fase 12 — Preparación comercial (§21)**: gestión de uso y cuotas ya expuestas por
API; quedan `PARTIALLY_IMPLEMENTED` el despliegue (verificar build/run de imágenes) y
`PROPOSED_NOT_IMPLEMENTED` costes y facturación (ver `docs/COMMERCIAL_READINESS.md`).

Pendientes técnicos de escalabilidad: sustituir el ejecutor en proceso por cola
externa (Celery/Redis), migrar SQLite→PostgreSQL y compartir el limitador de tasa
entre instancias. Alternativa de producto: monitor de tareas y panel de uso en la UI
(§18). No deben simularse reconstrucción/reparación/features (§8/§9/§10) mientras sus
motores no existan (`docs/reports/FASE_5_8_REPORT.md`).
