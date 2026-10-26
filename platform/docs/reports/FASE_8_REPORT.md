# Informe de Fase 8 — Análisis de aplicaciones compiladas, parte estática (§6.2, §23)

> Fase 8 (§21) cubre §6 completo. §6.2 (capacidades iniciales estáticas) está
> implementado y verificado. §6.3 (desensamblado, decompilación, ejecución
> dinámica controlada) permanece `PROPOSED_NOT_IMPLEMENTED` por depender de
> ejecución aislada real. Este informe declara ambos estados sin simular.

## 1. Objetivo

Según §21 Fase 8 y §6: identificar el formato de aplicaciones compiladas y extraer
hechos estáticos verificables (§6.2) —formato, arquitectura, bits, tipo de archivo,
secciones, hashes, símbolos importados/exportados, librerías enlazadas, cadenas
relevantes y firmas de versión— tratándolos como **evidencia contextual** y no como
prueba de funcionalidad (§6.2). Comenzar por los formatos con herramientas estándar
y pruebas adecuadas, sin ejecutar el binario (§6.3 fuera de alcance).

## 2. Archivos creados

| Archivo | Propósito |
|---------|-----------|
| `backend/app/engines/binary_analysis/models.py` | `Section` y `BinaryFacts` (+ `to_dict`) |
| `backend/app/engines/binary_analysis/utils.py` | `hash_bytes` (sha256/sha1/md5), `entropy`, `extract_strings` (ASCII + UTF-16LE), `find_version_signatures`, `StringLimits` |
| `backend/app/engines/binary_analysis/formats.py` | `detect_format` (ELF/PE/Mach-O/Mach-O fat/Java class/UNKNOWN) + tablas de máquinas y tipos |
| `backend/app/engines/binary_analysis/elf.py` | Cabecera, secciones+entropía, symtab/dynsym (import/export), `DT_NEEDED`, indicadores de depuración/Go |
| `backend/app/engines/binary_analysis/pe.py` | PE32/PE32+, secciones, `rva_to_offset`, import descriptors (DLLs + nombres/ordinales), exports, directorio de depuración y CLR |
| `backend/app/engines/binary_analysis/macho.py` | Mach-O fat y thin (LE/BE, 32/64), `LC_LOAD_DYLIB` y similares, `LC_SYMTAB`, secciones `LC_SEGMENT(_64)` |
| `backend/app/engines/binary_analysis/wasm.py` | WebAssembly: secciones, imports/exports (W8.3) |
| `backend/app/engines/binary_analysis/dex.py` | DEX de Android: cabecera, conteos y tabla de cadenas (W8.3) |
| `backend/app/engines/binary_analysis/pyc.py` | Bytecode CPython `.pyc`: magia/versión y flags (W8.3) |
| `backend/app/engines/binary_analysis/archive.py` | ZIP/JAR/APK: miembros, clases, DEX y `.so` nativas; inspección acotada del contenido interno (W8.3/W8.4) |
| `backend/app/engines/binary_analysis/coff.py` | Objetos COFF `.obj` y archivos `ar` `.a`/`.lib` (W8.3) |
| `backend/app/engines/binary_analysis/analyzer.py` | `BinaryLimits`, `analyze_binary`, `compare_binaries`, `_parse_java_class`, pistas de framework |
| `backend/app/engines/binary_analysis/__init__.py` | Exportaciones del motor |
| `backend/app/services/binary_service.py` | Ingesta de binario (`BINARY`) + análisis y persistencia de hechos + comparación |
| `backend/app/api/v1/binaries.py` | Endpoints de carga, análisis, listado, consulta y comparación |
| `backend/tests/test_binary_analysis.py` | 9 pruebas con fixtures ELF/PE/Mach-O/Java construidos en el test |
| `frontend/components/BinaryAnalysisPanel.tsx` | UI mínima: carga de binario, análisis y hechos (§18) |
| `docs/reports/FASE_8_REPORT.md` | Este informe |

## 3. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `backend/app/db/database.py` | `SCHEMA_VERSION = 4`; tabla `binary_analyses` + índices |
| `backend/app/db/repositories.py` | `create_binary_analysis` / `get_binary_analysis` / `list_binary_analyses` (org-scoped) |
| `backend/app/core/config.py` | `binary_analysis_max_bytes` (+ env `SIREP_BINARY_ANALYSIS_MAX_BYTES`) |
| `backend/app/schemas/models.py` | `BinaryAnalysisOut`, `BinaryCompareOut`, `BinaryAnalyzeRequest`, `BinaryCompareRequest` |
| `backend/app/api/v1/router.py` | Monta `binaries.router`; `/meta` → `binary_analysis: PARTIALLY_IMPLEMENTED` |
| `backend/.env.example` | `SIREP_BINARY_ANALYSIS_MAX_BYTES` |
| `frontend/lib/api.ts` | Tipos `BinaryAnalysis`/`BinaryFacts` y funciones `uploadBinary`/`analyzeBinary`/`listBinaryAnalyses` |
| `frontend/app/projects/[id]/page.tsx` | Monta `BinaryAnalysisPanel` |
| `docs/PROGRESS.md`, `docs/FASE_0_WBS.md` | W8.1 `TEST_PASSED`; R-04/R-12 y roadmap actualizados |
| `docs/reports/FASE_5_8_REPORT.md` | Fase 8 §6.2 marcada como desbloqueada y completada |

## 4. Componentes reutilizados

- `engines/ingestion/artifact_store.py` (`store_artifact`) y clasificación de tipo
  por contenido para persistir el binario y detectar MIME.
- `services/usage_service.py` (`enforce_storage_quota`) para la cuota de
  almacenamiento por organización.
- `db/repositories.py` (`create_artifact`, `record_audit`, `record_usage`) y el
  modelo de auditoría/uso de fases previas.
- `core/errors.py` (`NotFoundError`, `ValidationAppError`, `PayloadTooLargeError`)
  y el sobre de error normalizado.
- Patrón de router/dependencias (`CurrentUser`, `ActiveOrganization`, `Connection`,
  `require_role`) de fases anteriores.

## 5. Funcionalidades implementadas

- **Detección de formato (§6.1)**: ELF, PE (PE32/PE32+), Mach-O thin y fat,
  Java class, WebAssembly, DEX, bytecode CPython (`.pyc`), ZIP/JAR/APK, COFF y `ar`;
  con desambiguación de `CAFEBABE` (Java vs Mach-O fat) por versión mayor y
  heurística estricta para COFF sin magia. Formatos desconocidos se etiquetan
  `UNKNOWN` con limitaciones explícitas. `/meta` publica `binary_formats`.
- **Hechos estáticos (§6.2)**: arquitectura, bits, tipo de archivo, punto de
  entrada, secciones con tamaño y entropía, `sha256`/`sha1`/`md5`, símbolos
  importados y exportados, librerías enlazadas, indicadores de depuración y de
  runtime (p. ej. `.NET`/CLI, Go, Java), cadenas relevantes (URLs/plantillas/
  rutas) y firmas de versión.
- **Inspección acotada de contenedores (W8.4)**: en ZIP/JAR/APK se leen `.class`,
  `.dex` y `.so` internos en memoria (≤4 MiB por miembro, ≤64 miembros), se
  detecta su formato y se registran en `facts.embedded`; los archivos anidados se
  marcan como `ARCHIVE` y **no** se descomprimen recursivamente (§14.3). Los
  miembros que exceden el límite se marcan `TRUNCATED` sin analizarse.
- **Comparación** entre dos análisis (formato, arquitectura, digest, delta de
  tamaño, altas/bajas de exportaciones y librerías).
- **Ingesta y persistencia**: carga de binario como artefacto `BINARY` bajo cuota
  de almacenamiento; análisis persistido en `binary_analyses` con `facts_json`,
  auditoría y métrica de uso `binary_analyses`.
- **API**: `POST /projects/{id}/binaries`, `POST /projects/{id}/binary-analyses`,
  `GET /projects/{id}/binary-analyses`, `GET /binary-analyses/{id}`,
  `POST /binary-analyses/compare` (roles viewer/developer; aislamiento por
  organización).

## 6. Pruebas ejecutadas

- Comando backend: `cd platform/backend && python3 -m pytest`
- Comando frontend: `cd platform/frontend && npm run typecheck && npm run build`
- Herramientas: Python 3.12.3, pytest 9.1.1, FastAPI 0.139.0 (TestClient); Node
  v22.23.2, Next.js 15.5.28, TypeScript.
- Registro reproducible: `platform/docs/test-runs/20261018-164041.{json,md}`.

## 7. Resultados reales

- `91 passed, 0 failed, 0 errors, 0 skipped` (W8.1 + W8.3 + W8.4). Registro más
  reciente: `docs/test-runs/20261018-174226.{json,md}`.
- W8.1: 9 pruebas (detección, ELF/PE/Mach-O/Java, desconocido con `limitations`,
  comparación, flujo API, rechazo de formato y aislamiento por organización).
- W8.3: 8 pruebas nuevas — detección de los 6 formatos añadidos; WASM (import
  `env.foo`, export `run`); DEX (`Dalvik/ART`, cadena `Lcom/example/Main;`); PYC
  (`Python 3.12`, firma de magia); COFF (`.text`, i386); AR (`main.o`,
  `STATIC_LIBRARY`); ZIP→JAR/APK/ZIP por contenido (clases, `classes.dex`, `.so`);
  carga+análisis WASM por API; y `/meta` con `binary_formats` y capacidades.
- Corrección en W8.3: las firmas propias del parser se perdían al sobrescribir
  `signatures` con las versiones; ahora se combinan sin duplicados.
- W8.4: 2 pruebas nuevas — el archivo anidado no se expande (`format=ARCHIVE`) y
  el límite de bytes por miembro se respeta (`format=TRUNCATED`). El JAR expone el
  `.class` interno (`JAVA_CLASS`, major=52) y el APK expone `classes.dex` (`DEX`)
  y `libnative.so` (`ELF`).
- Frontend: `npm run typecheck` sin errores; `npm run build` OK.
- Integración en contenedor: tras reconstruir la imagen, `/meta` publica los 11
  formatos; un `.wasm` real devuelve `format=WASM` con export `run`; y un `.apk`
  real devuelve `format=APK` con contenido interno `classes.dex` (DEX v035) y
  `lib/arm64-v8a/libnative.so` (ELF).
- Estado §23: **§6.2 `TEST_PASSED`**; §6.3 `PROPOSED_NOT_IMPLEMENTED`.

## 8. Pruebas no ejecutadas

- Análisis sobre binarios reales de gran tamaño y casos límite de cada formato
  (fixtures sintéticos únicamente): `TEST_NOT_RUN`.
- §6.3 desensamblado/decompilación/ejecución dinámica controlada: `BLOCKED`
  (requiere ejecución aislada real, `docs/reports/FASE_5_8_REPORT.md`).

## 9. Problemas pendientes

- Cobertura de formatos acotada a los implementados; otros formatos (§6.1)
  devuelven `UNKNOWN` de forma honesta.
- El contenido interno de ZIP/JAR/APK se inspecciona de forma acotada y no
  recursiva; no se extrae a disco ni se analiza en profundidad.
- El motor es de solo lectura: no firma, no parchea ni ejecuta el binario.

## 10. Riesgos

- Falsos positivos en cadenas/firmas: se mitiga tratándolas como evidencia
  contextual (§6.2) y no como prueba de funcionalidad.
- Parsers frente a entradas malformadas: se evita el crash devolviendo
  `limitations` en lugar de excepciones; sin fuzzing sistemático aún.

## 11. Instrucciones para reproducir

```bash
cd platform/backend
python3 -m pytest                      # 78 pruebas en verde
python3 scripts/record_test_run.py --label "Fase 8 W8.1"
```

## 12. Próxima fase

- Fase 12 (preparación comercial): build/run de contenedores ya `TEST_PASSED`
  (`docs/reports/FASE_12_REPORT.md`). §6.3 avanzado y Fases 5/7 siguen bloqueadas
  por ejecución aislada; Fase 8 puede ampliarse con más formatos de §6.1.
