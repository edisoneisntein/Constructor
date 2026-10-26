# Informe de Fases 5, 6, 7 y 8 — Reparación, Nuevas funciones, Reconstrucción y Binarios

> Documento de **estado y bloqueo**, no de entrega. Ninguna de estas fases está
> implementada. Se redacta según §23 para dejar constancia explícita y evitar que
> se confunda lo planificado con lo ejecutado. Estados permitidos (§23):
> `IMPLEMENTED`, `PARTIALLY_IMPLEMENTED`, `PROPOSED_NOT_IMPLEMENTED`,
> `TEST_PASSED`, `TEST_FAILED`, `TEST_NOT_RUN`, `BLOCKED`.

## 1. Objetivo

Dejar registro verificable del estado de las cuatro fases del roadmap (§21) que
aún no cuentan con motor implementado, con sus requisitos (§8/§9/§10/§6), causas
del bloqueo, dependencias afectadas y el siguiente paso necesario.

## 2. Correspondencia de fases (§21) con secciones del PDF

| Fase | Sección PDF | Motor | Estado |
|------|-------------|-------|--------|
| 5 | §9 | `RepairEngine` | `PROPOSED_NOT_IMPLEMENTED` |
| 6 | §10 | `FeatureDevelopmentEngine` | `PROPOSED_NOT_IMPLEMENTED` |
| 7 | §8 | `FunctionReconstructionEngine` | `PROPOSED_NOT_IMPLEMENTED` |
| 8 | §6 | `BinaryAnalysisEngine` | `PROPOSED_NOT_IMPLEMENTED` |

## 3. Archivos creados

| Archivo | Propósito |
|---------|-----------|
| `docs/reports/FASE_5_8_REPORT.md` | Este documento de estado/bloqueo |

## 4. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `docs/FASE_0_WBS.md` | Se referencia este informe en R-04, R-14, R-15, R-16 y en el roadmap |
| `docs/PROGRESS.md` | Fases 5–8 registradas como `PROPOSED_NOT_IMPLEMENTED` |

## 5. Componentes reutilizados (previstos para estas fases)

Ninguno se ha integrado aún. Cuando se implementen, deberían reutilizar:

- `engines/change_management` (§15): workspace aislado, hashes y diff para
  proponer/aplicar parches de reparación y reconstrucción con reversión.
- `core/execution_profiles` + `core/sandbox` (§14): ejecución de pruebas en
  entorno aislado con límites (pasos 8 de §8.2 y §9.2), hoy sin motor que ejecute
  código del cliente.
- `engines/analysis/source_analysis` y `engines/graph` (§5/§7): evidencia base
  para diagnóstico y para la especificación conocida.
- `adapters/ai_provider_layer` (§13, `PARTIALLY_IMPLEMENTED`): generación de
  propuestas con redacción de secretos y consentimiento de transmisión.
- `services/change_service` (§15): registro, aprobación y validación de cambios.

## 6. Funcionalidades implementadas

Ninguna. Cada fase queda **no implementada** en esta revisión.

## 7. Requisitos por fase (referencia exacta) y por qué no se abordan todavía

### Fase 5 — §9 RepairEngine
- §9.1 Defectos a abordar (sintaxis, compilación, imports rotos, dependencias,
  configuración, ejecución, lógica, APIs, errores, pruebas fallidas,
  vulnerabilidades, rendimiento reproducible).
- §9.2 Flujo de reparación en 11 pasos, incluido **reproducir el error cuando sea
  seguro** y **ejecutar las pruebas en workspace aislado**.
- §9.3 Límites: máximo **3 iteraciones** automáticas por tarea y cotas de tiempo,
  memoria, CPU, tokens, coste, procesos, tamaño de archivos y cambios por ciclo;
  no ampliar privilegios ni introducir dependencias de alto riesgo.
- **Bloqueo**: los pasos 3, 7, 8 y 9 exigen capacidad de **ejecutar el código del
  cliente en un entorno aislado**. Esa capacidad no existe (§14.1 perfiles sin
  motor de ejecución; §14.2 sin contenedor/VM). Sin ejecución aislada no es
  posible reproducir, aplicar y validar parches de forma honesta.

### Fase 6 — §10 FeatureDevelopmentEngine
- §10.1 Planificación (objetivo, requisitos, archivos, interfaces, dependencias,
  esquema, configuración, pruebas, riesgos, reversión, criterios de aceptación) y
  aprobación humana para cambios de riesgo.
- §10.2 Implementación: inspeccionar convenciones, localizar componentes,
  implementar, probar.
- 14 ejemplos de funcionalidad (endpoints, páginas, auth, exportación, APIs,
  proveedores de IA, tareas asíncronas, métricas, accesibilidad, pruebas, etc.).
- **Bloqueo**: depende de generación con proveedor de IA real (§13, hoy
  `PARTIALLY_IMPLEMENTED`; llamadas remotas `BLOCKED` por credenciales) y de un
  bucle de verificación que ejecute pruebas en entorno aislado (inexistente).

### Fase 7 — §8 FunctionReconstructionEngine
- §8.2 Procedimiento de 12 pasos (uno de ellos, paso 8, **ejecutar pruebas en
  entorno aislado**; paso 9, comparar con requisitos/referencias).
- §8.3 Distinguir tipos de prueba (requisitos, caracterización, unitarias,
  regresión, aceptación, equivalencia) y usar referencias independientes.
- §8.4 Estados de resultado: `VALIDATED_WITHIN_TEST_SCOPE`,
  `PARTIAL_EQUIVALENCE`, `CANDIDATE_NOT_VALIDATED`, `INSUFFICIENT_EVIDENCE`,
  `BLOCKED`; nunca afirmar equivalencia universal por una suite limitada.
- **Bloqueo**: igualmente requiere ejecución aislada y, para equivalencia,
  referencias de comportamiento independientes. Implementable parcialmente como
  generación de candidatos, pero **no verificable** sin ejecución, por lo que se
  mantiene como no implementado según la regla de no declarar simulado como real.

### Fase 8 — §6 BinaryAnalysisEngine
- §6.1 Formatos: ELF, PE, Mach-O, .NET, Java empaquetado, Electron, paquetes,
  bibliotecas nativas; adaptadores especializados por formato.
- §6.2 Capacidades iniciales estáticas: formato, arquitectura, metadatos, hashes,
  símbolos, import/export, bibliotecas, recursos, cadenas, depuración,
  dependencias, frameworks, versiones/firmas y comparación entre artefactos.
- §6.3 Análisis avanzado (desensamblado, decompilación, dinámico controlado) con
  límites, contratos y pruebas.
- §6.4 Limitaciones: no prometer recuperar el código fuente; la extracción de
  cadenas es evidencia contextual, no prueba definitiva; prohibido robar
  credenciales o eludir licencias.
- **Bloqueo parcial**: las capacidades estáticas de §6.2 (magic bytes, hashes,
  strings) son implementables con librerías del sistema; las avanzadas de §6.3
  requieren aislamiento. Actualmente la ingesta **clasifica** binarios
  (`BINARY`, `classify_kind`) pero **no** existe `engines/binary_analysis`.

## 8. Pruebas ejecutadas

Ninguna para estas fases (no hay código que probar). La suite existente del
proyecto (**61 pruebas en verde**) cubre las fases 0–4, 9/10 y 11 y no incluye
estas cuatro fases.

```
cd platform/backend
python3 -m pytest        # 61 passed (fases implementadas; ninguna de 5–8)
```

## 9. Pruebas no ejecutadas

- Todas las pruebas funcionales de las Fases 5–8: `TEST_NOT_RUN`.
- Ejecución aislada de código del cliente (§8.2 paso 8, §9.2 pasos 7–9): `BLOCKED`.
- Llamadas a proveedores de IA para generación de código (§13): `BLOCKED`
  (requieren credenciales; consentimiento de transmisión desactivado por defecto).

## 10. Problemas pendientes y dependencias afectadas

- **Dependencia raíz**: capacidad de ejecución aislada del código del cliente
  (§14.1/§14.2). Bloquea Fases 5, 7 y la verificación de la 6.
- **Dependencia de IA**: integración real con proveedor (§13) para generación de
  candidatos. Bloquea Fase 6 y la generación de la 7.
- **Dependencia de binarios**: adaptadores por formato (§6.1). No requiere
  ejecución para §6.2, por lo que Fase 8 puede iniciarse antes que 5/6/7.

## 11. Riesgos

- Declarar estas fases como hechas sin ejecución ni verificación violaría §1
  (veracidad) y §23. Se mantienen explícitamente como no implementadas.
- Habilitar ejecución de código sin aislamiento reforzado introduce riesgo de
  escape; debe abordarse con contenedor/VM, seccomp/AppArmor y sin credenciales
  del host antes de usarse (§14.1 `HIGH_RISK_DYNAMIC_ANALYSIS`).

## 12. Instrucciones para reproducir el estado

```
cd platform/backend
python3 -m pytest                                   # 61 passed
ls ../docs/reports                                 # sin FASE_5..FASE_8 (no implementadas)
grep -n "PROPOSED_NOT_IMPLEMENTED" ../docs/FASE_0_WBS.md   # R-04, R-14, R-15, R-16
```

## 13. Próxima tarea concreta

Por dependencias, el orden desbloqueado sugerido es:

1. **Fase 8 (§6.2)** — análisis estático de binarios con adaptadores por formato
   (ELF primero si hay herramienta disponible), sin prometer recuperación de
   fuente. Verificable sin ejecución.
2. **Capacidad de ejecución aislada** (§14.1/§14.2, contenedor/VM) — desbloquea
   Fases 5 y 7 y la verificación de la 6.
3. Resto de Fase 11 (observabilidad, cuotas) y Fase 12 (preparación comercial).

Mientras no se aborden, cada fase permanece `PROPOSED_NOT_IMPLEMENTED` y sus
pruebas `TEST_NOT_RUN`.
