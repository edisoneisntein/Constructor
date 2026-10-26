# Arquitectura (trazada a SAAS REA.pdf)

## Capas (§4)

```
API (§4.1)  →  Servicios  →  Motores (§4.2)  →  Persistencia (§4.4)
                                  │
                                  └─ Adaptador REA (subproceso aislado)
```

- **API** (`app/api/v1`): FastAPI. Autenticación por token opaco, organización
  activa por cabecera `X-Organization-Id`, autorización por rol.
- **Servicios** (`app/services`): `analysis_service` orquesta el pipeline;
  `job_runner` ejecuta en segundo plano con cancelación cooperativa y estado
  persistido; `auth_service` gestiona identidades y sesiones.
- **Cola de trabajos (§4.3/§21)**: los análisis viven en `analysis_jobs` con
  reclamo atómico. En modo `external`, `app/worker.py` los consume con heartbeat y
  recuperación de huérfanos (escala horizontal); en modo `inline` los ejecuta el
  `job_runner` del proceso de la API.
- **Motores** (`app/engines`):
  - `ingestion`: `safe_zip` (defensas) y `artifact_store` (almacenamiento
    direccionado por contenido, detección de MIME por bytes mágicos).
  - `analysis`: detectores de lenguaje, `python_analyzer` (AST), `js_analyzer`
    (bridge Node + `@babel/parser`), `manifest_parser` (dependencias),
    `integrations` (clasificador de proveedores de IA), `source_analysis`
    (orquestador determinista).
  - `graph`: `architecture_graph` con niveles de evidencia.
  - `change_management`: `change_engine` (rutas seguras, clasificación
    añadido/modificado/eliminado, hashes, diff unificado) descrito en §15.
  - `migration`: motor de migración tecnológica (§11) y adaptador Gemini → NVIDIA
    NIM (§12): `gemini_detector` (AST/patrones), `nim_compat` (matriz), `planner`
    (plan y diffs), `rules` (reglas versionadas) y `sources` (fuentes oficiales).
  - `features`: `nim_codegen` — construcción del prompt de generación (§10),
    parseo de la respuesta JSON del modelo y **verificación** de los archivos
    propuestos (ruta segura, contenido no vacío, sintaxis comprobable).
  - `binary_analysis`: análisis estático de binarios (§6.2) — `formats` (detección
    y formatos soportados), parsers `elf`/`pe`/`macho`/`wasm`/`dex`/`pyc`/
    `archive`/`coff`, `utils` (hashes, entropía, cadenas) y `analyzer`
    (orquestación y comparación). Solo lectura; no ejecuta el binario.
- **Persistencia** (`app/db`): una misma capa de repositorios sobre dos dialectos.
  SQLite (WAL) por defecto y **PostgreSQL** cuando `SIREP_DATABASE_URL` es una URL
  `postgresql://`. `pg.py` traduce marcadores (`?`→`%s`, `:name`→`%(name)s`) y
  `INSERT OR IGNORE`→`ON CONFLICT DO NOTHING`, y devuelve filas tipo diccionario
  homogéneas con `sqlite3.Row`; `database.py` selecciona el dialecto y expone
  `is_ephemeral`/`label`.

## Gestión de cambios (§15)

`change_service` implementa el ciclo `PROPOSED → APPROVED → APPLIED →
VALIDATED → ROLLED_BACK`. Cada conjunto materializa su propio workspace desde el
artefacto (`storage_root/change_sets/{id}/workspace`) y conserva `before/` y
`after/` por archivo. Antes de aplicar o revertir se verifica el hash del archivo
destino (`409 change_conflict` si cambió). La validación reejecuta el análisis
  estático sobre el workspace. La reversibilidad se declara solo para archivos
  locales; los efectos externos se documentan como no reversibles.

## Generación de código con IA (§10)

`generation_service` (W14.2/W14.3) usa NVIDIA NIM para proponer código. El flujo:
extrae el artefacto a un workspace de contexto acotado, construye el prompt
(árbol de archivos, archivo objetivo y, en modo `repair`, los hallazgos), consulta
el modelo, **verifica** cada archivo (sintaxis `ast`/JSON y ruta segura) y solo si
todo es válido lo registra como un conjunto de cambios `PROPOSED` reutilizando
§15. Requiere consentimiento de transmisión (`ai_consent`, §14). Un fallo de
verificación impide persistir el cambio (`generation_verification_failed`).

## Seguridad y aislamiento (§14)

- `core/execution_profiles.py`: cinco perfiles ordenados por riesgo; el más
  permisivo (`HIGH_RISK_DYNAMIC_ANALYSIS`) exige `SIREP_EXECUTION_ALLOW_HIGH_RISK`
  y nunca se habilita automáticamente. El perfil activo se publica en `/api/v1/meta`.
- `core/sandbox.py`: `preexec_fn` que aplica `RLIMIT_CPU`, `RLIMIT_FSIZE` y
  `RLIMIT_NOFILE` a los subprocesos (REA, bridge Node). `RLIMIT_AS` solo si se
  configura memoria (evita romper Node/V8).
- `core/net_guard.py`: valida conexiones salientes (esquema http/https, bloqueo de
  loopback/privado/metadatos, lista blanca de hosts; resolución opcional).
- `core/logging.py`: redacción de secretos de múltiples proveedores (§14.6).
- Retención (§14.6): borrado explícito de artefactos y purga por caducidad con baja
  lógica, eliminación de bytes y auditoría.

## Integración con REA (§4.3)

- Se invoca REA como **subproceso externo** (aislamiento, evitar acoplar licencias).
- Operaciones permitidas por lista blanca (`ALLOWED_OPERATIONS`).
- Resultados normalizados a NDJSON/JSON propio (`REAAdapter`).
- REA es opcional: si está deshabilitado o falla, el análisis estático propio
  sigue funcionando y la limitación se registra.

## Niveles de evidencia (§ evidencia y trazabilidad)

- `DIRECT_EVIDENCE`: hallazgo derivado de una observación directa del código
  (import, uso de variable de entorno, dependencia declarada).
- `STATIC_INFERENCE`: hallazgo inferido del grafo (p. ej. archivo que usa un
  proveedor y archivo que declara su clave, correlacionados estáticamente).

Cada hallazgo conserva `file_path`, `line_start`/`line_end`, `language`,
`snippet`, `detection_method` y `tool`.

## Modelo de grafo

Nodos: archivo, módulo/símbolo, dependencia, variable de entorno, integración,
punto de entrada. Aristas: `IMPORTS`, `DEPENDS_ON`, `CONFIGURES`, `USES`,
`ENTRYPOINT`. El grafo distingue aristas confirmadas de inferidas.
