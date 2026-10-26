# PRD — Product Requirements Document

## Product Requirements Document para Implementation Constructor REA
### Fuente de verdad absoluta: SAAS REA.docx (Párrafos 122-165)

## 1. VISION DEL PRODUCTO

**Nombre:** Implementation Validator Module — Constructor REA
**Visión:** Sistema independiente de validación de implementación para Software Intelligence Platform, conforme al documento SAAS REA.docx
**Objetivo:** Verificar de forma reproducible y basada en evidencias que cada requisito del documento de especificación "sas rea" esté implementado correctamente

## 2. PÚBLICO OBJETIVO

- Agentes de programación dentro de Constructor REA
- Validadores independientes que inspeccionan código generado por agentes
- Módulo interno de la plataforma Constructor REA para conformidad de implementación

## 3. PROBLEMA A RESOLVER

Validar reproduciblemente que cada requisito del documento base "sas rea" esté implementado correctamente, sin confiar en afirmaciones del agente desarrollador, comentarios del código, existencia de archivos ni apariencia de interfaz.

## 4. MÉTRICAS DE ÉXITO

- 100% de requisitos del PDF mapeados y asignados identificador REQ-xx
- Estado por requisito (PASS/FAIL/PARTIAL/BLOCKED/NOT_RUN) registrado estructuradamente
- Evidencias reproducibles para cada requisito verificado
- Cálculo de cumplimiento diferenciado: cumplimiento técnico vs. calidad del código vs. seguridad vs. preparación para producción
- No declarar proyecto listo para producción solo por tests automatizados

## 5. ALCANCE (SCOPE)

### SCOPE IN (Dentro de los límites del producto):

1. **Registro de requisitos** con identificadores estables (REQ-001, REQ-002, etc.)
   - Descripción original del requisito
   - Criterios de aceptación verificables
   - Dependencias identificadas
   - Componentes y archivos relacionados
   - Pruebas requeridas
   - Estado actual (NOT_RUN, RUNNING, PASS, FAIL, PARTIAL, BLOCKED, NOT_APPLICABLE)
   - Evidencias y limitaciones registradas
   - Historial de cambios y validaciones

2. **Motor de validación** con adaptadores independientes por categoría:
   - Integridad estructural y archivos
   - Análisis estático y calidad
   - Compilación y comprobación de tipos
   - Pruebas unitarias
   - Pruebas de integración
   - Pruebas de extremo a extremo
   - Contratos y comportamiento de APIs
   - Persistencia y migraciones de base de datos
   - Seguridad y dependencias
   - Interfaz gráfica y accesibilidad
   - Cada adaptador devuelve: resultados estructurados, código de salida, duración, evidencias, errores y limitaciones

3. **Estados de validación** estructurados con reglas claras:
   - Estados mínimos: NOT_RUN, RUNNING, PASS, FAIL, PARTIAL, BLOCKED, NOT_APPLICABLE
   - Regla: Un requisito solo puede aprobarse cuando todos sus criterios obligatorios tienen evidencia suficiente
   - Prohibido: Calcular porcentaje de cumplimiento usando solo archivos existentes o afirmaciones del agente

4. **Entorno de ejecución aislado:**
   - Código no confiable en entornos aislados
   - Permisos mínimos por operación
   - Límites de recursos (CPU, memoria, tiempo, red)
   - Directorios controlados por operación
   - Protección de credenciales y datos del usuario
   - Registro de comandos ejecutados
   - Prohibido operaciones destructivas sin autorización

5. **Independencia y reproducibilidad:**
   - Separar motor de validación del agente que modifica código
   - Registrar commit/hash del código validado
   - Registrar versiones de herramientas y configuración
   - Registrar resultados y evidencias
   - Invalidar resultados si cambia el código
   - No reutilizar resultados antiguos como prueba de la versión actual

6. **Ciclo de corrección estructurado:**
   - Fallo → generar informe con evidencias reproducibles
   - Identificar requisito y criterios incumplidos
   - Preparar paquete de diagnóstico para agente desarrollador
   - Permitir agente proponga corrección en rama/entorno aislado
   - Inspeccionar diff y ejecutar de nuevo pruebas afectadas y de regresión
   - Conservar historial de intentos y resultados
   - Solicitar intervención humana ante riesgos elevados, decisiones ambiguas o cambios sensibles
   - Limitar intentos automáticos para evitar ciclos infinitos

7. **Informe y aceptación diferenciados:**
   - Conformidad por requisito y por módulo
   - Pruebas aprobadas, fallidas, parciales y no ejecutadas
   - Evidencias y registros consolidados
   - Defectos detectados identificados
   - Cambios pendientes de revalidación
   - Historial de correcciones aplicadas
   - Bloqueos y limitaciones documentados
   - Informe exportable de conformidad (formato estructurado)
   - Diferenciar: cumplimiento técnico vs. calidad del código vs. seguridad vs. preparación producción
   - Prohibido: Declarar proyecto listo para producción solo por tests automatizados

8. **Entrega incremental:**
   - Empezar mínimo: leer requisito, vincular a criterio aceptación, ejecutar prueba real, guardar resultado, mostrar por qué pasó o fallar
   - Ejecutar pruebas propio validador, documentar resultados reales
   - Ampliar cobertura por módulos progresivamente
   - NO declarar integración terminada que esté simulada
   - NO declarar prueba que no se haya ejecutado nunca

### SCOPE OUT (Fuera de los límites del producto):

- Afirmaciones del agente desarrollador como evidencia suficiente
- Porcentaje de cumplimiento calculado con datos incompletos
- Declarar proyecto listo para producción únicamente por tests automatizados
- Validación sin entorno aislado y permisos mínimos
- Reutilizar resultados antiguos sin invalidación por cambio de código

## 5. REQUERISTOS CRÍTICOS (del documento SAAS REA)

| ID | Requisito | Fuente |
|----|-----------|--------|
| REQ-001 | Registro de requisitos con referencias seccionales y páginas | Párrafo 127-136 |
| REQ-002 | Motor de validación con adaptadores independientes por categoría | Párrafos 139-153 |
| REQ-003 | Estados de validación estructurados con reglas claras | Párrafos 154-163 |
| REQ-004 | Entorno de ejecución aislado con permisos mínimos | Párrafos 165-168 |
| REQ-005 | Independencia y reproducibilidad con registro de commit/hash | Párrafos 169-173 |
| REQ-005 | Ciclo de corrección con intervención humana cuando corresponda | Párrafos 174-183 |
| REQ-007 | Informe y aceptación diferenciados (technical vs quality vs security vs production) | Párrafos 184-194 |
| REQ-008 | Entrega incremental empezando por circuito extremo a endo funcional | Párrafos 196-210 |

## 6. LIMITACIONES CONOCIDAS

- No se pueden considerar afirmaciones del agente desarrollador como evidencia de cumplimiento
- No se puede calcular porcentaje de cumplimiento con datos incompletos
- No se debe declarar proyecto listo para producción solo por tests automatizados
- La integración requiere entorno aislado con permisos mínimos configurados

## 7. LIMITACIONES DE LA FASE ACTUAL (Constructor REA vs. PRD)

| Requerimiento | Estado Constructor REA | Brecha |
|--------------|----------------------|--------|
| Registro de requisitos REQ-xx | ⚠️ Estructura básica (fases WBS) | Falta ficha de requisito formal REQ-001 en diante |
| Motor de validación adaptadores | ⚠️ Componentes parciales (BinaryAnalysis, FunctionRepair) | Faltan adaptadores por categoría completa |
| Estados de validación formales | ⚠️ Tests passing/falling básicos | Falta estructura NOT_RUN/PASS/FAIL/PARTIAL/BLOCKED por requisito |
| Entorno aislado | ✅ ISOLATED_TEST_EXECUTION | Cumplido parcialmente |
| Independencia/reproductividad | ⚠️ Git hash tracking disponible | Falta registro formal de herramientas y configuración por ejecución |
| Ciclo de corrección | ⚠️ Reparaciones simples automatizadas | Falta ciclo fallo→informe→corrección→revalidación automatizado |
| Informe diferenciados | ❌ No implementado | Falta panel de conformidad por requisito/módulo |
| Entrega incremental | ✅ Fase 15 completada | Comienza ahora con esta base de requisitos |

# NOTA DE ACTUALIZACIÓN
**Fuente absoluta: SAAS REA.docx (220.5KB, 211 párrafos, 13,702 caracteres)**
**Este PRD reemplaza cualquier versión anterior y establece la autoridad técnica para todas las fases subsiguientes de Constructor REA.**