# Informe de Fase 3 — Grafo y análisis ampliado (§21, §23)

> Formato: los 12 puntos de §23 del PDF `SAAS REA.pdf`. Estados explícitos según §23.
> Fecha de ejecución: 2026-10-18.

## 1. Objetivo de la fase

Según §21 Fase 3: "Añadir navegación del grafo, más relaciones, mejores
diagnósticos y reglas de análisis." Sin dependencias de credenciales externas.

## 2. Archivos creados

- `backend/tests/test_analysis_rules.py`
- `backend/tests/test_graph_relations.py`
- `docs/reports/FASE_3_REPORT.md`

## 3. Archivos modificados

- `backend/app/engines/graph/architecture_graph.py`: nuevos tipos de nodo
  (manifest, symbol, env_var, integration, api_route, entrypoint, test), nuevos
  tipos de arista (depends_on, defines, reads_env, uses, exposes, is_entrypoint,
  is_test, configures), deduplicación de aristas y conteos por tipo.
- `backend/app/engines/analysis/facts.py`: `StringRef` y nuevos hechos
  (`provider_calls`, `model_refs`, `hardcoded_secrets`).
- `backend/app/engines/analysis/python_analyzer.py`: reglas de llamadas a SDK de
  proveedor, referencias a modelos y secretos embebidos (asignaciones y kwargs).
- `backend/app/engines/analysis/source_analysis.py`: manifiestos antes que el
  código, enlace de imports a dependencias declaradas, relaciones de grafo
  ampliadas y relaciones inferidas SDK↔entorno; summary con conteos por tipo.
- `backend/app/db/repositories.py`: `get_node`, `list_nodes_filtered`,
  `list_edges_filtered`, `count_nodes_by_type`, `count_edges_by_type`.
- `backend/app/schemas/models.py`: `NodeDetailOut`, `SubgraphOut` y conteos por
  tipo en `ArchitectureGraphOut`.
- `backend/app/api/v1/projects.py`: filtros en `/architecture`, `/subgraph` y
  `/architecture/node`.
- `backend/tests/test_api_flow.py`: aserción de relación inferida y prueba de
  endpoints de navegación.
- Frontend: `lib/api.ts` (tipos `NodeDetail`), `components/GraphView.tsx`
  (nodos por tipo, clicables), `app/projects/[id]/page.tsx` (inspector de nodo).

## 4. Componentes reutilizados

- `@babel/parser` (MIT) vía el bridge existente. No se añadieron dependencias
  nuevas de backend ni de frontend.

## 5. Funcionalidades implementadas

- Grafo enriquecido: nodos de archivo, manifiesto, dependencia, símbolo,
  variable de entorno, integración, ruta de API, entrypoint y prueba.
- Relaciones: `declares_dependency`, `depends_on`, `imports`,
  `imports_external`, `defines`, `reads_env`, `uses`, `exposes`,
  `is_entrypoint`, `is_test` y `configures` (inferida).
- Enlace de imports externos a dependencias declaradas (normalización de nombres).
- Relación inferida `env_var → integration` cuando el SDK se importa y una
  variable de entorno coincide con el proveedor, marcada `STATIC_INFERENCE`.
- Nuevas reglas: detección de llamadas a SDK de proveedor, referencias a modelos
  (`gemini-*`, etc.), secretos embebidos (heurística) y archivos de prueba.
- Navegación del grafo por API: filtros por tipo, detalle de nodo
  (entrantes/salientes/vecinos) y subgrafo por profundidad.
- Navegación del grafo en la UI: nodos coloreados por tipo y clicables, con
  inspector de nodo.
- `summary` con `node_type_counts` y `edge_type_counts`.

## 6. Pruebas ejecutadas

- `python3 -m pytest` → **27 passed** (incluye 5 nuevas de Fase 3).
- `npm run typecheck` → sin errores.
- `npm run build` → compilación correcta.

## 7. Resultados reales

**TEST_PASSED** para las relaciones de grafo, las nuevas reglas y los endpoints
de navegación. Verificado: nodos `integration`/`env_var`/`dependency`/`symbol`
presentes; arista `configures` siempre `STATIC_INFERENCE`; el nodo
`integ::google_gemini` es alcanzable y su subgrafo incluye la variable de
entorno; el detalle de nodo y los filtros por tipo responden 200, y un nodo
inexistente responde 404.

## 8. Pruebas no ejecutadas

- Proveedores de IA remotos y matriz de compatibilidad NIM → **PROPOSED_NOT_IMPLEMENTED /
  BLOCKED** (Fase 10, requiere credenciales).
- Análisis de binarios → **PROPOSED_NOT_IMPLEMENTED**.
- Pruebas de UI automatizadas (E2E de navegador) → **TEST_NOT_RUN**.

## 9. Problemas pendientes

- El enlace import→dependencia cubre nombres npm/PyPI por normalización; casos
  con paquetes sombra o alias no se resuelven (se registran como
  `imports_external`).
- Detección de modelos en JS/TS es un escaneo de contenido acotado (200 KB),
  marcado como `STATIC_INFERENCE`, no estructural.
- Volumen de nodos de símbolos acotado por archivo (500).

## 10. Riesgos

- Falsos positivos de secretos embebidos: mitigado con heurística y nivel
  `STATIC_INFERENCE` (no se afirma como hallazgo directo).
- Crecimiento del grafo en repos grandes: acotado por límites de archivos y de
  símbolos por archivo.

## 11. Instrucciones para reproducir la validación

```bash
cd platform/backend
python3 -m pytest tests/test_graph_relations.py tests/test_analysis_rules.py tests/test_api_flow.py -q
uvicorn app.main:app --port 8000   # /docs para probar /architecture, /subgraph, /architecture/node
cd ../frontend && npm run typecheck && npm run build
```

## 12. Próxima fase

Fase 4 (§15, §21): gestión de cambios — workspaces, hashes, manifiestos de
cambio, diff, aprobación y reversión. Independiente de credenciales. La detección
de SDK/modelos de esta fase es base directa para el detector Gemini de la Fase 10.
