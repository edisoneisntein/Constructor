# Limitaciones conocidas (§30)

Estado honesto de lo no implementado o dependiente de terceros.

## Dependencias externas no verificadas en esta fase

- **Análisis profundo con proveedores de IA remotos**: proveedor único =
  **NVIDIA NIM**. Verificado en vivo y en contenedor
  (`docs/test-runs/20261018-nim-live-verification.md`): `TEST_PASSED`. **Gemini no
  se integra**; la clave Gemini aportada resultó inválida (`API_KEY_INVALID`) y no
  se usa. Las llamadas NIM cubren verificación de credenciales, disponibilidad de
  modelo, inferencia de chat y **generación/reparación de código (§10)** verificada
  en vivo (`docs/test-runs/20261018-nim-generation-live.md`). La verificación de
  los cambios generados es **estática** (sintaxis comprobable + reanálisis al
  aplicar); los lenguajes sin comprobador disponible se marcan como «sintaxis no
  verificada» en lugar de afirmar validez. No se ejecutan pruebas dinámicas del
  código generado (requiere ejecución aislada, §14.1).
- **Suite de pruebas de REA**: no ejecutada en esta fase. Estado: `TEST_NOT_RUN`.
- **Exportación PDF**: no implementada; se entregan JSON y Markdown.

## Limitaciones funcionales de la fase

- **Análisis estático, no dinámico**: no se ejecuta el código del cliente; los
  hallazgos son de código fuente y manifiestos, no de comportamiento en runtime.
- **Binarios (§6.2)**: análisis estático de solo lectura para ELF, PE (PE32/PE32+),
  Mach-O (thin/fat), Java class, WebAssembly, DEX, bytecode CPython (`.pyc`),
  ZIP/JAR/APK, COFF y `ar`, verificado con fixtures sintéticos. En ZIP/JAR/APK se
  inspecciona el contenido interno (`.class`/`.dex`/`.so`) de forma acotada
  (≤4 MiB/miembro, ≤64 miembros) y no recursiva, sin extraer a disco. El
  desensamblado, la decompilación y la ejecución dinámica controlada (§6.3)
  permanecen `PROPOSED_NOT_IMPLEMENTED` (requieren ejecución aislada). Cadenas,
  símbolos y firmas son evidencia contextual, no prueba de funcionalidad.
- **Persistencia**: SQLite por defecto (adecuada para el MVP) y **PostgreSQL**
  soportada mediante un adaptador de dialecto tras la capa de repositorio
  (`SIREP_DATABASE_URL`, §4.4). Verificado contra PostgreSQL 16
  (`docs/test-runs/20261018-postgresql-persistence.md`). No se ha probado con
  pooling de conexiones (se abre una conexión por petición) ni con réplicas de
  lectura; ambos quedan como trabajo futuro.
- **Jobs en proceso**: `ThreadPoolExecutor` con estado persistido; no sobrevive a
  reinicios del proceso ni escala horizontalmente (Celery/Redis previstos).
- **Analizador TS/JS**: depende de Node y `@babel/parser`. Si no están presentes,
  el análisis continua sin cobertura TS/JS y lo declara explícitamente.
- **Cobertura de lenguajes**: actualmente Python y JavaScript/TypeScript. Otros
  lenguajes quedan como no analizados (se detectan y se reportan como limitación).
- **Cifrado en reposo y multi-tenant físico**: no implementados; el aislamiento
  es lógico por `organization_id`.
- **Contenedores**: `Dockerfile` de backend/frontend y `docker-compose.yml`
  definidos. Build y ejecución E2E verificados (`TEST_PASSED`, ver
  `docs/test-runs/20261018-container-e2e.md`): health y flujo vertical en
  contenedor. La UI se ejercitó con navegador real (Playwright/Chromium) con el
  escenario principal (`TEST_PASSED`,
  `docs/test-runs/20261018-ui-e2e-playwright.md`); no hay cobertura de accesos
  alternativos (roles distintos, errores de red, etc.).
- **Ejecución de trabajos (§4.3/§21)**: la API puede delegar los análisis en un
  proceso trabajador externo (`SIREP_JOB_QUEUE=external`, servicio `worker`), con
  reclamo atómico, heartbeat y recuperación de huérfanos
  (`docs/test-runs/20261018-external-worker-e2e.md`). La cola es la tabla
  `analysis_jobs` de la base de datos; no es un broker dedicado. Con SQLite y
  varios workers aumenta la contención de escritura; está previsto migrar a
  PostgreSQL o a un broker (Redis/ARQ/Celery) sin cambiar los contratos.
- **Limitación de tasa (§14/§21)**: dos backends por configuración — `memory`
  (una instancia, predeterminado) y `database` (compartido entre instancias).
  No hay backend Redis todavía; el contador de base de datos añade una escritura
  por petición.
- **Aislamiento de ejecución**: los perfiles (§14.1) y límites de recursos
  (§14.2) existen como control, pero **no hay ejecución dinámica del código del
  cliente**: no se lanza ningún proceso del cliente y por tanto no hay aislamiento
  por contenedor/VM en uso. El `preexec_fn` con `RLIMIT_*` se aplica a las
  herramientas externas (REA/bridge Node), no a código del cliente.
- **Guard de red (§14.4)**: valida host literal y lista blanca; no resuelve DNS
  por defecto (`resolve=False`), por lo que el DNS rebinding no queda cubierto.
- **Purga por retención (§14.6)**: programada en el worker
  (`SIREP_RETENTION_PURGE_INTERVAL_SECONDS`, <=0 la desactiva); con
  `SIREP_JOB_QUEUE=inline` debe invocarse `purge_expired_artifacts` manualmente,
  ya que no hay planificador en el proceso de la API.
- **Registro de pruebas (§19.6)**: registros en `docs/test-runs/` corresponden a
  ejecuciones locales de `pytest`; el entorno no es un repositorio Git, por lo que
  los campos de commit/rama figuran como `n/d`.
- **Límite de tasa (§14)**: implementado en proceso (`core/rate_limit.py`); no
  protege varias instancias a la vez ni bloquea por IP de forma distribuida.
- **Cuotas (§14/§21)**: almacenamiento y análisis concurrentes se calculan sobre el
  estado actual (artefactos no eliminados / jobs activos); la cuota de proyectos es
  acumulativa. Costes y facturación no están implementados (§21 Fase 12).
