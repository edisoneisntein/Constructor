# Informe de Fase 4 — Gestión de cambios (§15, §21, §23)

## 1. Objetivo

Según §21 Fase 4: "Implementar workspaces, diffs, aprobación, hashes y
reversión." El motor de cambios (§15) debe registrar, para cada modificación:
identificador, workspace, estado original, hashes, manifiesto de archivos,
añadidos/modificados/eliminados, diff unificado, motivo, regla o tarea que lo
produjo, pruebas asociadas, aprobaciones y resultado de validación. Antes de
aplicar un parche se verifica que el archivo destino no haya cambiado; se
conserva registro suficiente para comparar versiones y revertir modificaciones
locales; no se afirman reversibles los efectos sobre bases de datos o servicios
externos.

## 2. Archivos creados

| Archivo | Propósito |
|---------|-----------|
| `backend/app/engines/change_management/__init__.py` | Paquete del motor de cambios |
| `backend/app/engines/change_management/change_engine.py` | Lógica pura: rutas seguras, clasificación añadido/modificado/eliminado, SHA-256, diff unificado (`difflib`) |
| `backend/app/services/change_service.py` | Ciclo de vida PROPOSED → APPROVED → APPLIED → VALIDATED → ROLLED_BACK con verificación de hashes |
| `backend/app/api/v1/changes.py` | Endpoints REST de gestión de cambios |
| `backend/tests/test_change_management.py` | 9 pruebas: lógica pura + ciclo completo + conflictos |
| `frontend/components/ChangeSetPanel.tsx` | UI: crear/listar conjuntos, ver diffs y aprobar/aplicar/validar/revertir (§18) |
| `docs/reports/FASE_4_REPORT.md` | Este informe |

## 3. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `backend/app/db/database.py` | `SCHEMA_VERSION = 2`; tablas `change_sets`, `change_files`, `change_approvals` + índices |
| `backend/app/db/repositories.py` | `create/get/list/update_change_set`, `insert/list_change_files`, `set_change_file_applied`, `add/list_change_approvals` |
| `backend/app/schemas/models.py` | Enums `ChangeStatus`, `ChangeType`; modelos `FileEditIn`, `ChangeSetCreate`, `ChangeApprovalIn`, `ChangeFileOut`, `ChangeApprovalOut`, `ChangeSetOut`, `ChangeSetDetailOut` |
| `backend/app/api/v1/router.py` | Inclusión del router de cambios; capacidad `change_management: IMPLEMENTED` |
| `frontend/lib/api.ts` | Tipos `ChangeSet`/`ChangeFile`/`ChangeApproval` y funciones de la API de cambios |
| `frontend/app/projects/[id]/page.tsx` | Integración del panel de cambios en la vista de resultados |
| `docs/PROGRESS.md`, `docs/FASE_0_WBS.md` | W4.1/W4.2/W4.3 `TEST_PASSED`; R-21/R-25/R-01 actualizados |

## 4. Componentes reutilizados

- `engines/ingestion/safe_zip.safe_extract` + `ExtractionLimits`: materializa el
  workspace del cambio desde el artefacto almacenado (mismas defensas que la ingesta).
- `engines/ingestion/artifact_store.sha256_bytes`: hashes base/resultado/aplicado.
- `engines/analysis/source_analysis.run_source_analysis`: reejecuta el análisis
  estático sobre el workspace modificado durante la validación.
- `db/repositories` (patrón `new_id`/`utcnow_iso`/auditoría) y `api/deps`
  (`require_role`, aislamiento por `organization_id`).
- `adapters/rea_adapter.build_rea_adapter`: usado en la reejecución de validación.

## 5. Funcionalidades implementadas

- **Workspace aislado por cambio**: `storage_root/change_sets/{id}/workspace`
  (base extraída), más `before/` y `after/` con el contenido antes y después de
  cada archivo (permite comparar versiones y revertir).
- **Registro completo (§15)**: id, analysis/project/organization, workspace,
  hash del artefacto base, motivo, `produced_by_rule`, manifiesto de archivos,
  tipo de cambio, hashes base/nuevo/aplicado, diff unificado, pruebas asociadas
  (`associated_tests`), aprobaciones y `validation_result`.
- **Aprobación**: `POST /change-sets/{id}/approve` (rol `admin`+), decisión
  `approved`/`rejected`; se persiste cada aprobación en `change_approvals`.
- **Aplicación con guarda de integridad**: si el archivo destino no coincide con
  el hash base registrado → `409 change_conflict`.
- **Reversión con guarda de integridad**: si el archivo no coincide con el hash
  aplicado → `409 change_conflict`; si coincide, restaura el contenido original
  (o elimina los añadidos).
- **Reversibilidad honesta**: `reversible = true` para archivos locales y
  `external_effects` declarando que no se tocan bases de datos ni servicios
  externos (§15).
- **Capacidad expuesta** en `/api/v1/meta`.
- **UI (§18, W4.2)**: `ChangeSetPanel` permite crear conjuntos (motivo, regla y
  ediciones con añadir/modificar/eliminar), listarlos por análisis, ver el diff
  unificado por archivo y ejecutar aprobar/rechazar/aplicar/validar/revertir
  según el estado, mostrando `validation_result`, aprobaciones y la nota de
  reversibilidad/external_effects.

## 6. Pruebas ejecutadas

```
cd platform/backend
python3 -m pytest
```

- 9 pruebas nuevas (`tests/test_change_management.py`).
- Total del proyecto: **36 passed** en ~6.5 s.

## 7. Resultados reales

- `classify_change` produce `ADDED`/`MODIFIED`/`DELETED` con diff unificado y
  hashes correctos; devuelve `None` sin diferencia efectiva.
- `safe_relative_path` rechaza `../`, rutas absolutas, `~` y nulos.
- Ciclo completo por API verificado: crear (PROPOSED) → aprobar (APPROVED) →
  aplicar (APPLIED, verificado leyendo el workspace real en disco) → validar
  (VALIDATED con `validation_result.files_analyzed ≥ 1`) → revertir
  (ROLLED_BACK, contenido original restaurado en disco).
- Aplicar sin aprobar → 409. Aplicar con hash base alterado → 409 `change_conflict`.
  Cambio rechazado no aplicable (409). Cambio sin diferencias → 422.
- Listado por análisis devuelve el conjunto creado.

Frontend (W4.2):

```
cd platform/frontend
npm run typecheck   # sin errores
npm run build       # compilación correcta (ruta /projects/[id] generada)
```

## 8. Pruebas no ejecutadas

- E2E por `uvicorn` real (la Fase 3 lo hizo para el grafo); aquí la cobertura es
  vía `TestClient`, que ejerce la misma pila (DB, extracción y análisis reales).
- **E2E de navegador de la UI de cambios**: solo se verificó `typecheck` + `build`;
  no hay test automatizado de navegador (limitación conocida del MVP).
- Validación de que la reejecución del análisis en la nube NIM funcione (W9.1).

## 9. Problemas pendientes

- **Cambios en capas**: cada conjunto parte del artefacto original, no del
  resultado de otro conjunto. Documentado como limitación del MVP.
- El workspace del cambio se conserva; no hay recolector de espacios huérfanos.

## 10. Riesgos

- Aplicar/revertir toca el sistema de archivos: las guardas de hash cubren el
  caso de modificación concurrente externa, pero no hay bloqueo de exclusión.
- `associated_tests` se deriva por heurística de nombre de archivo.
- Los efectos externos (BD/servicios) están declarados como no reversibles; si en
  el futuro un cambio los toca, deberá añadirse procedimiento de compensación (§15).

## 11. Instrucciones para reproducir

```
cd platform/backend
python3 -m pytest tests/test_change_management.py -v
python3 -m pytest            # 36 passed
uvicorn app.main:app --reload
# Flujo: registrar → proyecto → subir ZIP → analizar →
#   POST /api/v1/analyses/{id}/change-sets   (motivo, regla, edits)
#   POST /api/v1/change-sets/{id}/approve    {decision:"approved"}
#   POST /api/v1/change-sets/{id}/apply
#   POST /api/v1/change-sets/{id}/validate
#   POST /api/v1/change-sets/{id}/rollback
```

## 12. Próxima fase

**W9.1 — Detector Gemini → NVIDIA NIM (§12)**: detector de uso del SDK de Google
Gemini, matriz de compatibilidad con NVIDIA NIM y generación de diffs de
migración (reutilizando el motor de cambios §15). El detector y la matriz se
implementan sin credenciales; solo las pruebas remotas contra NIM quedan
`BLOCKED`.
