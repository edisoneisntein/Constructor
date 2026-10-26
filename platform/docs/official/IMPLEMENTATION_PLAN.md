# Implementation Plan — Implementation Constructor REA

## Plan de Implementación Oficial
### Fuente de verdad absoluta: SAAS REA.docx (Párrafos 196-210)

## 1. FILOSOFÍA DE IMPLEMENTACIÓN

**Principio rector (párrafo 207-208):** Empezar mínimo y crecer progresivamente. NO declarar integración terminada que esté simulada. NO declarar prueba que no se haya ejecutado.

**Criterio de ampliación (párrafo 206):** Cuando el circuito extremo a extremo funcione (registrar requisito → ejecutar prueba → guardar resultado → mostrar por qué pasó o falló), ampliar analizadores y pruebas.

## 2. FASES DE IMPLEMENTACIÓN

### FASE A: Fundamento y Preparación (Sprint 1)

**Objetivo:** Establecer la base de datos y modelos sin ejecutar código externo.

| Tarea | Descripción | Estado |
|-------|-------------|--------|
| A1 | Crear modelos SQLAlchemy para las 6 tablas | PENDIENTE |
| A2 | Generar migración Alembic inicial | PENDIENTE |
| A3 | Aplicar migración a PostgreSQL existente | PENDIENTE |
| A4 | Crear modelos Pydantic de entrada/salida | PENDIENTE |
| A5 | Implementar CRUD básico de requisitos (POST/GET/PUT) | PENDIENTE |
| A6 | Verificar persistencia con prueba real (no simulada) | PENDIENTE |

**Criterio de salida:**
- ✅ Tablas creadas en PostgreSQL
- ✅ Migración aplicada sin errores
- ✅ POST /api/v1/validator/requirements funciona con datos reales
- ✅ GET devuelve el requisito insertado con estado NOT_RUN

**Riesgo principal:** PostgreSQL Fase 16 puede requerir configuración adicional de adaptador de dialecto.

---

### FASE B: Primer Circuit Extremo a Extremo (Sprint 2)

**Objetivo:** Implementar el circuito mínimo: registrar → ejecutar → guardar → mostrar.

| Tarea | Descripción | Estado |
|-------|-------------|--------|
| B1 | Implementar adapter base (`adapters/base.py`) | PENDIENTE |
| B2 | Implementar structural_adapter (integridad de archivos) | PENDIENTE |
| B3 | Implementar endpoint POST /executions | PENDIENTE |
| B4 | Ejecutar primera prueba real sobre código Constructor REA | PENDIENTE |
| B5 | Persistir resultado en tabla executions | PENDIENTE |
| B6 | Crear endpoint GET /requirements/{id}/executions | PENDIENTE |
| B7 | Crear endpoint GET /dashboard con métricas reales | PENDIENTE |
| B8 | **NO simular resultados — ejecutar de verdad** | PENDIENTE |

**Criterio de salida (párrafo 206):**
- ✅ Requisito registrado con ID REQ-001
- ✅ Prueba ejecutada de verdad (no simulada, output real)
- ✅ Resultado persistido con committed_hash y tool_versions
- ✅ Dashboard muestra estado real del requisito
- ✅ Circuito completado extremo a extremo: registrar → ejecutar → guardar → mostrar

**Validación obligatoria:**
```bash
# 1. Registrar requisito
curl -X POST http://localhost:8001/api/v1/validator/requirements \
  -H "Content-Type: application/json" \
  -d '{"requirement_id":"REQ-001","description_original":"Validar integridad estructural","acceptance_criteria":[{"id":"AC-001","description":"Estructura correcta","mandatory":true}]}'

# 2. Ejecutar prueba
curl -X POST http://localhost:8001/api/v1/validator/executions \
  -H "Content-Type: application/json" \
  -d '{"requirement_id":"REQ-001","test_type":"structural"}'

# 3. Verificar resultado
curl http://localhost:8001/api/v1/validator/requirements/REQ-001/executions

# 4. Ver dashboard
curl http://localhost:8001/api/v1/validator/dashboard
```

---

### FASE C: Motor de Validación (Sprint 3)

**Objetivo:** Ampliar adaptadores y estados de validación.

| Tarea | Descripción | Estado |
|-------|-------------|--------|
| C1 | Implementar static_analysis_adapter (pefile, análisis estático) | PENDIENTE |
| C2 | Implementar unit_test_adapter (pytest integrado) | PENDIENTE |
| C3 | Implementar integration_adapter (endpoints FastAPI) | PENDIENTE |
| C4 | Implementar security_adapter (dependencias, secrets) | PENDIENTE |
| C5 | Implementar asignación automática de estados (PASS/FAIL/PARTIAL/BLOCKED) | PENDIENTE |
| C6 | Registrar committed_hash automáticamente (git rev-parse) | PENDIENTE |
| C7 | Registrar tool_versions automáticamente (pip show) | PENDIENTE |
| C8 | Crear tabla validation_runs y endpoint POST /runs | PENDIENTE |
| C9 | **NO reutilizar resultados si cambia el código** | PENDIENTE |

**Criterio de salida:**
- ✅ Mínimo 4 adaptadores operativos (estructural, estático, unitario, integración)
- ✅ Estados asignados automáticamente según resultados
- ✅ committed_hash registrado en cada ejecución
- ✅ Validación de que resultados antiguos se invalidan si cambia el código

---

### FASE D: Seguridad y Ejecución Aislada (Sprint 4)

**Objetivo:** Asegurar ejecución segura y aislada.

| Tarea | Descripción | Estado |
|-------|-------------|--------|
| D1 | Verificar ISOLATED_TEST_EXECUTION operativo para validator | PENDIENTE |
| D2 | Implementar límites de CPU/memoria/tiempo en adaptadores | PENDIENTE |
| D3 | Proteger credenciales (env vars, no hardcodear) | PENDIENTE |
| D4 | Registrar todos los comandos ejecutados | PENDIENTE |
| D5 | Implementar rate limiting en endpoints del validator | PENDIENTE |
| D6 | Verificar que no se ejecutan scripts del repositorio validado en entorno principal | PENDIENTE |

**Criterio de salida:**
- ✅ Todas las ejecuciones pasan por ISOLATED_TEST_EXECUTION
- ✅ Límites de recursos verificados con prueba de estrés
- ✅ Cero credenciales hardcodeadas (verificación manual + grep)
- ✅ Rate limiter activo en endpoints

---

### FASE E: Ciclo de Corrección (Sprint 5)

**Objetivo:** Implementar flujo fallo → diagnóstico → corrección → revalidación.

| Tarea | Descripción | Estado |
|-------|-------------|--------|
| E1 | Crear tabla correction_attempts + migración | PENDIENTE |
| E2 | Implementar endpoint POST /corrections | PENDIENTE |
| E3 | Generar paquete de diagnóstico automático (req_id, criterios fallados, output, logs) | PENDIENTE |
| E4 | Integrar con FunctionRepairEngine para reparaciones de patrón simple | PENDIENTE |
| E5 | Implementar endpoint POST /corrections/{id}/revalidate | PENDIENTE |
| E6 | Ejecutar pruebas de regresión automáticamente tras corrección | PENDIENTE |
| E7 | Limitar reintentos automáticos (máx. 3 por requisito) | PENDIENTE |
| E8 | Solicitar intervención humana ante riesgos elevados | PENDIENTE |

**Criterio de salida:**
- ✅ Fallo detectado genera diagnóstico completo
- ✅ Corrección propuesta registrada en tabla correction_attempts
- ✅ Revalidación ejecuta pruebas afectadas + regresión
- ✅ Historial de reintentos visible por requisito
- ✅ Máximo de reintentos respetado

---

### FASE F: Reportes y Dashboard (Sprint 6)

**Objetivo:** Construir interfaz de reportes y conformidad.

| Tarea | Descripción | Estado |
|-------|-------------|--------|
| F1 | Implementar GET /reports/conformity | PENDIENTE |
| F2 | Implementar GET /reports/conformity/{module} | PENDIENTE |
| F3 | Implementar GET /reports/export (JSON/CSV) | PENDIENTE |
| F4 | Diferenciar: cumplimiento técnico vs. calidad vs. seguridad vs. preparación producción | PENDIENTE |
| F5 | Implementar panel de métricas globales (72/100, fallidos, pendientes, bloqueados) | PENDIENTE |
| F6 | **NO declarar listo para producción solo por tests automatizados** | PENDIENTE |

**Criterio de salida:**
- ✅ Reporte de conformidad generado con datos reales
- ✅ Exportación JSON/CSV funcional
- ✅ Diferenciación de tipos de conformidad visible
- ✅ Dashboard muestra métricas actualizadas en tiempo real

---

### FASE G: Ampliación de Cobertura (Sprint 7+)

**Objetivo:** Ampliar cobertura por módulos progresivamente.

| Tarea | Descripción | Estado |
|-------|-------------|--------|
| G1 | Extraer requisitos restantes de SAAS REA.docx | PENDIENTE |
| G2 | Registrar requisitos REQ-002 a REQ-0NN | PENDIENTE |
| G3 | Ejecutar validación sobre cada nuevo requisito | PENDIENTE |
| G4 | Ampliar adaptadores para cubrir nuevos tipos de requisito | PENDIENTE |
| G5 | Documentar resultados reales de cada ejecución | PENDIENTE |
| G6 | **NO declarar terminada integración simulada** | PENDIENTE |

**Criterio de salida:**
- ✅ Mínimo 10 requisitos registrados y validados
- ✅ Cobertura > 50% de requisitos del documento
- ✅ Cero integraciones simuladas
- ✅ Cero pruebas declaradas sin ejecutar

---

## 3. CRONOGRAMA RESUMIDO

| Sprint | Fase | Duración Estimada | Dependencias |
|--------|------|-------------------|--------------|
| 1 | A: Fundamento | 1 semana | PostgreSQL Fase 16 |
| 2 | B: Circuit E2E | 1 semana | Fase A completada |
| 3 | C: Motor Validación | 1.5 semanas | Fase B completada |
| 4 | D: Seguridad | 1 semana | Fase C completada |
| 5 | E: Ciclo Corrección | 1.5 semanas | Fase D completada |
| 6 | F: Reportes | 1 semana | Fase E completada |
| 7+ | G: Ampliación | Continuo | Fase F completada |

**Total estimado:** 7-8 sprints (7-8 semanas) para MVP completo.

## 4. RESTRICCIONES V.A.A. (Plan)

1. **Nunca** saltarse fases — cada fase depende de la anterior
2. **Nunca** declarar fase completada sin criterio de salida verificado
3. **Nunca** simular resultados para "cumplir" criterios de salida
4. **Siempre** ejecutar pruebas reales antes de marcar tarea como completada
5. **Siempre** registrar committed_hash y tool_versions en cada ejecución
6. **Siempre** usar ISOLATED_TEST_EXECUTION para código externo
7. **Siempre** ampliar cobertura solo después de circuito E2E funcional
8. **Nunca** declarar listo para producción solo por tests automatizados

## 5. VERIFICACIÓN FINAL OBLIGATORIA

Antes de declarar el Implementation Validator como operativo:

1. ✅ Mínimo 10 requisitos registrados con estado real
2. ✅ Mínimo 4 adaptadores ejecutando pruebas de verdad
3. ✅ Ciclo de corrección probado con al menos 1 fallo real
4. ✅ Reporte de conformidad generado con datos reales
5. ✅ Dashboard operativo con métricas actualizadas
6. ✅ Cero simulaciones en el código
7. ✅ Cero pruebas declaradas sin ejecutar
8. ✅ committed_hash registrado en 100% de ejecuciones
9. ✅ ISOLATED_TEST_EXECUTION usado en 100% de ejecuciones
10. ✅ Audit log registrando todas las acciones

---

## 6. CONCLUSIÓN V.A.A.

**Este plan de implementación establece la hoja de ruta oficial y no negociable para construir el Implementation Validator dentro de Constructor REA.**

**Principios innegociables:**
1. Verdad absoluta: SAAS REA.docx es la fuente
2. Ejecución real: Nunca simular
3. Progresión: Ampliar solo tras circuito E2E funcional
4. Seguridad: ISOLATED_TEST_EXECUTION obligatorio
5. Reproductibilidad: committed_hash + tool_versions siempre
6. Corrección: Ciclo estructurado, no aleatorio
7. **Prohibido:** Declarar listo para producción solo por tests automatizados

**Estado actual:** Documento construido. Próximo paso: iniciar Fase A (Fundamento) — crear modelos SQLAlchemy y migración Alembic.

---
**Fuente absoluta: SAAS REA.docx (220.5KB, 211 párrafos, 13,702 caracteres)**
**Documento construido bajo protocolo V.A.A. directiva no negociable.**
