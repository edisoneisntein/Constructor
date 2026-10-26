# FASE 1 — Informe de Auditoría Empírica de REA

> Corresponde a §3.2 del PDF "SAAS REA".
> Componente auditado: `morluto/rea` v6.5.0.
> Artefacto verificado: paquete publicado instalado en
> `/Users/edisonrodriguez/.npm/_npx/af752b90495482d7/node_modules/rea-agents`
> (y árbol de fuentes `rea-main` extraído localmente, inspeccionado 2026-10-18).
> Método: lectura directa de `README.md`, `package.json`, `LICENSE`,
> `THIRD_PARTY_NOTICES.md`, `docs/architecture.mermaid`, `docs/*`, árbol `src/`,
> y **ejecución real** del CLI sobre un fixture local.

## 1. Arquitectura actual

REA es una herramienta **local-only** de ingeniería inversa con dos adaptadores de
entrada que comparten flujos: un CLI (`scripts/rea.mjs` → `src/cli.ts`) y un
servidor MCP stdio (`src/main.ts`). Arquitectura en capas estricta
(`docs/architecture.mermaid`):

```
Entry Points (cli/main) → Composition → Server/Adapters → Application
  → Provider Layers (hopper/ghidra/ida/wasm/evm/…) → Contracts → Domain
  → Process foundation (src/process, src/windows)
```

- **Dominio puro** sin efectos (`src/domain/`, evidencia, comparaciones, grafos).
- **Contratos** de caller visibles en `src/contracts/` (schemas Zod).
- **Composición** en `src/composition/` (factories tipadas, carga opcional por proveedor).
- **155 comandos CLI** verificados (`rea --help | grep -c`).

## 2. Capacidades confirmadas (verificadas)

| Capacidad | Evidencia |
|-----------|-----------|
| CLI ejecutable y funcional | `node .../scripts/rea.mjs --version` → `6.5.0`; `--help` → 155 comandos |
| Inventario de capacidades/proveedores | `rea capabilities --json` → JSON con `groups[].available` y `effects[]` |
| Análisis estático JS/Electron | **Ejecutado con éxito** sobre fixture: `analyze-javascript-application <dir> --json`, exit 0, produce `evidence_id`, `subject.digest.sha256`, `normalized_result` |
| Metodología de evidencia | Salida con `confidence`, `authority`, `environment`, `limitations`, `evidence_links` |
| Supervisión de procesos con límites | `src/process/ProviderProcess.ts:206` `spawnOwnedProviderProcess`, `:295` `ProviderProcessSupervisor`, opción `memoryLimitBytes` (`:42`) |
| Lectura de fuentes de referencia acotada | `src/reference/` (`parseReferenceSourceImports`) |
| Extracción de artefactos con defensas | `src/artifacts/` (lector ZIP con bloqueo de zip-slip y bombas; dependencia `@zip.js/zip.js`) |
| Parsers AST JS/TS | Depende de `@babel/parser` 8.0.4 y `@babel/types` 8.0.4 |
| Diffs | Depende de `diff` 9.0.0 |
| Config validada | Dependencia `zod` 4.4.3; `src/config/` |

## 3. Capacidades NO encontradas (no inventar)

- **No existe** un detector de uso del SDK de Google Gemini (GenAI / Vertex / `@google/generative-ai`).
  Todas las referencias a "Gemini" en REA corresponden a **Gemini CLI como cliente
  MCP** (`src/application/GeminiClientSettings.ts`: parsea `~/.gemini`, `mcpServers`),
  es decir, REA *usándose dentro* de Gemini CLI — **lo inverso** a nuestro caso.
- **No existe** un motor de análisis de código fuente en Python (REA es TS/JS y binarios).
- **No existe** un motor de migración de proveedores de IA ni matriz de compatibilidad.
- `src/application/GeminiClientSettings.ts` y `ClientConfigurationDocument.ts`
  son **contrarios a reutilizar** para detección de SDK: detectan el propio registro MCP de REA.

## 4. Componentes reutilizables

**Estrategia: integración desacoplada por proceso (REAAdapter), no por enlace de código.**

- Toda la funcionalidad se consume mediante `rea <comando> --json` (CLI público).
- Se reutiliza conceptualmente: modelo de evidencia, cobertura explícita
  (`complete`/`partial`), digest SHA-256 del sujeto, descarte de resultados no
  verificados (análogo al detector Flutter `identify_flutter_build`).
- Se reutiliza concretamente: **`@babel/parser`** del árbol de `node_modules` de
  REA para el bridge TS/JS (dependencia MIT, ya presente en disco).

## 5. Componentes que requieren adaptación

- Salida de REA: JSON NDJSON con eventos `rea_progress` + un objeto final de
  Evidence anidado (`normalized_result`). Requiere un **normalizador** que lo
  convierta a contratos internos del SaaS (`REAResultNormalizer`).
- `analyze-javascript-application` es intensivo y produce grafos ricos; para el
  MVP se usa un bridge propio mínimo (imports/funciones/env vía babel) y REA queda
  como proveedor **opcional** de análisis profundo.

## 6. Dependencias y requisitos

- Node.js `^22.19.0 || ^24.11.0 || >=26.0.0` (equipo: v22.23.2 ✔), npm.
- Proveedores nativos opcionales: Hopper/Ghidra/IDA/JADX/Binwalk… (bring-your-own).
- Build propio de REA requiere `npm ci` + `turbo` (pesado). **No es necesario**:
  se usa el paquete publicado ya instalado.

## 7. Compatibilidad de licencias

- Código propio de REA: **MIT** (`LICENSE`).
- Terceros con copyleft presentes en `licenses/`: `GPL-3.0`, `LGPL-2.0 (+WxWindows exception)`,
  `GCC-Runtime-Library-Exception`, MinGW, y para herramientas *bring-your-own*
  (pwntools con componentes GPL, Unicorn GPL-2.0, GDB GPL-3.0, OpenJDK GPLv2+CE).
- **Consecuencia legal/arquitectónica:** el addon nativo de Windows (MinGW/GCC runtime)
  y las herramientas GPL **no deben reempaquetarse** en nuestro SaaS. Por eso la
  integración es **por proceso externo** (el usuario aporta su instalación de REA),
  lo que preserva las licencias y evita redistribución copyleft. `THIRD_PARTY_NOTICES.md`
  y `licenses/` se conservan sin modificar.

## 8. Riesgos de seguridad

| Riesgo | Mitigación adoptada |
|--------|---------------------|
| Código/binario analizado es **no confiable** | Perfil `STATIC_ANALYSIS` por defecto; sin ejecución del código del proyecto |
| REA puede lanzar procesos/GUI (Hopper, navegador) | En MVP solo se permiten comandos **estáticos**; allowlist de operaciones |
| Fuga de rutas/secretos de REA al núcleo SaaS | `REAResultNormalizer` + redacción; excepciones capturadas por el adaptador |
| Extracción de archivos (zip-slip/bomba) | Validación propia en ingesta (independiente de REA) |
| Inyección de instrucciones en repos | Contenido tratado como datos; nunca ejecutado ni interpretado como política |
| Dependencias nativas por plataforma | REA es opcional; el MVP funciona sin REA salvo análisis profundo JS |

## 9. Coste aproximado de complejidad (sin precisión inventada)

- Integración REA como subproceso + normalizador: **baja** (contrato JSON estable, verificado).
- Análisis Python nativo (`ast`): **baja**.
- Bridge TS/JS con babel: **baja-media**.
- Detección Gemini + matriz NIM + diffs: **media** (reglas versionadas + fixtures).

## 10. Diseño de integración

```
SaaS core
  └── adapters/rea/
        REAAdapter          → localiza binario, verifica versión/requisitos
        REAExecutionManager → timeout, límites, aislamiento de proceso, allowlist
        REAResultNormalizer → NDJSON/Evidence → contratos internos (Findings/Graph)
```

REA **no** es dependencia rígida: si no está disponible, el flujo vertical sigue
funcionando con los analizadores nativos y marca el análisis profundo como `BLOCKED`.

## 11. Pruebas existentes y resultados reales

- REA trae un gate extenso (`vitest`, Stryker, conformance) con `package.json` scripts.
  **No ejecutado** en este entorno (requiere `npm ci` de ~400 MB; el paquete publicado no
  incluye `src/` ni `tests/`). Estado: `TEST_NOT_RUN` — se declara, no se simula.
- Prueba **sí ejecutada**: `analyze-javascript-application` sobre fixture local → exit 0. `TEST_PASSED`.

## 12. Plan de trabajo del primer flujo funcional

`Artifact Ingestion → Safe Extraction → Static Analysis (Python + TS/JS) → Findings
→ Architecture Graph → Persisted Results`, con API FastAPI, persistencia y pruebas.
REA se integra como proveedor opcional en la fase de análisis profundo.

## Decisiones técnicas registradas

1. **Integración REA por subproceso** (licencia + aislamiento). `IMPLEMENTED` (adaptador).
2. **Persistencia MVP: SQLite** con repositorio abstraído → Postgres en Fase 11 (§4.4 permite adaptar).
3. **Colas: async en proceso con estado persistido** en MVP; Redis/Celery cuando exista necesidad demostrable (§4.3).
4. **Nombre del producto parametrizable** por configuración (§0).
5. **Sin secretos en fixtures**; `.env.example` con valores ficticios.
