# APPFLOW — Application Flow Document

## Application Flow para Implementation Constructor REA
### Flujo de Trabajo V.A.A. Basado en SAAS REA.docx (Párrafos 196-210 y flujo completo)

## 1. FLUJO OFICIAL DE TRABAJO

### PASO 1: INSPECCIÓN INICIAL

**Acción:** Leer y registrar un requisito

- Acceso al repositorio SAAS REA.docx como fuente de verdad absoluta
- Extraer requisito e identificar: descripción original, criterios de aceptación, dependencias, componentes relacionados
- Asignar identificador estable (formato REQ-xxx)
- Vincular requisito a criterio de aceptación verificables
- **Resultado:** Requisito registrado en base de datos con estado inicial NOT_RUN

**Acción:** Ejecutar una prueba real sobre el código

- Ejecutar pruebas del propio validador (no simuladas, ejecución real)
- Utilizar entornos aislados con límites de CPU, memoria, tiempo y permisos mínimos (Fase 6: ISOLATED_TEST_EXECUTION)
- Ejecutar contra código base real (Constructor REA, proyecto JARVIS, o repositorio especificado)
- **Resultado:** Ejecución registrada con status (PASS/FAIL/PARTIAL/BLOCKED/NOT_RUN), duración, output, error_details si los hay

**Acción:** Guardar el resultado

- Persistir resultado en base de datos PostgreSQL (Fase 16)
- Almacenar evidencias asociadas (logs, capturas, reportes generados)
- Registrar commit/hash del código validado
- Registrar versiones de herramientas usadas (pefile, FastAPI, pytest, etc.)
- **Resultado:** Registro oficial en tabla `executions` con trazabilidad completa

### PASO 2: MOSTRAR Y COMPARTIR

**Acción:** Mostrar en la interfaz por qué pasó o falló

- Consultar tabla `requirements` para obtener estado actual del requisito
- Consultar tabla `executions` para obtener historial de ejecuciones
- Mostrar evidencias asociadas (logs, reportes, capturas)
- **Formato de presentación:**
  - Estado actual (NOT_RUN/RUNNING/PASS/FAIL/PARTIAL/BLOCKED/NOT_APPLICABLE)
  - Criterios de aceptación y cuáles aprobaron/fallaron
  - Output de la ejecución (logs relevantes, no todo el volcado)
  - Error concreto si falló (contexto específico, no genérico)
  - Hallazgos de seguridad si corresponde
  - Hallazgos de calidad si corresponde

**Acción:** Enviar un fallo al agente para que proponga una corrección

- Si el estado es FAIL o PARTIAL, generar paquete de diagnóstico
- El paquete incluye: requisito ID, criterios fallados, output de pruebas, logs del entorno, diff si corresponde
- Enviar al agente de programación en rama o entorno aislado (no modificar código directo en producción)
- **Nota:** El agente propone una corrección en una rama o entorno aislado
- El validador vuelve a ejecutar las pruebas afectadas y las pruebas de regresión pertinentes
- **Conservar el historial** de intentos y resultados (para tracking a largo plazo)

### PASO 3: AMPLIAR COBERTURA

**Acción:** Ejecutar de nuevo la prueba y registrar el resultado

- Después de la corrección propuesta, volver a ejecutar las pruebas afectadas
- **Ejecutar pruebas de regresión** pertinentes (para asegurar que no se introdujo nueva degeneración)
- **Registrar el resultado** definitivo (puede ser PASS si la corrección fue exitosa, FAIL si no, PARTIAL si es mixto)
- **Actualizar el historial** con el nuevo intento y resultado

**Acción:** Ampliar cobertura por módulos

- Cuando el circuito extremo a extremo funcione (paso 1 → paso 2 → paso 3 exitoso), ampliaría los analizadores y las pruebas
- **Nuevo módulo:** Extender validación a siguiente requisito o componente
- **Nuevo analizador:** Agregar adaptador para nueva categoría de validación (integridad, estático, pruebas, etc.)
- **NO declarar terminada una integración** que esté simulada (todas las pruebas deben ejecutarse de verdad)
- **NO declarar una prueba** que no se haya ejecutado nunca (estado NOT_RUN es válido si está documentado por qué no se ejecutó)

### PASO 3B: Verificación de Circuitos Completos

Antes de ampliar cobertura, verificar que el circuito completo funciona:

1. ✅ Paso 1 completado: Requisito registrado con estado NOT_RUN → RUNNING → estado final
2. ✅ Paso 2 completado: Prueba ejecutada, resultado registrado, fallo diagnosticado si corresponde
3. ✅ Paso 2B completado: Corrección propuesta y nueva ejecución de pruebas realizada
4. ✅ **Criterio de salida:** Cuando ese circuito funcione de extremo a extremo, ampliaría los analizadores y las pruebas

### PASO 3: ENTREGA INCREMENTAL

**Acción:** Empezar mínimo y crecer progresivamente

- **Primero:** Inspeccionar repositorio y herramientas existentes (¿Qué analyzers ya vienen integrados? ¿Qué tests vienen definidos?)
- **Después:** Implementar flujo vertical funcional:
  1. Registrar un requisito
  2. Ejecutar una prueba real
  3. Guardar el resultado
  4. Mostrar por qué pasó o fallar
- **Ejecutar las pruebas propio validador**, documentar resultados reales
- **Ampliar cobertura por módulos** (comenzar por uno crítico y crecer)
- **No declarar terminada una integración** que esté simulada (todas las pruebas deben ejecutarse de verdad)
- **No declarar una prueba** que no se haya ejecutado nunca (estado NOT_RUN está bien si está documentado por qué no se ejecutó)

### PASO 4: Integración con Constructor REA (Casos de Uso)

El flujo APPFLOW se integra con Constructor REA de las siguientes maneras:

1. **Artifact Ingestion → Safe Extraction → Static Analysis → Findings → Architecture Graph → Persisted Results** (flujo documentado en README.md)

2. **Health Checks:** Ejecutar `curl http://localhost:8001/health` y `curl http://localhost:8001/health/ready` antes y después de cada circuito de validación para asegurar que el sistema está en estado operativo.

3. **Rate Limiting:** Respetar el rate limiter Redis configurado en la Fase 12/13 al ejecutar múltiples validaciones en corto tiempo.

4. **ISOLATED_TEST_EXECUTION:** Ejecutar todas las pruebas de validación bajo el perfil ISOLATED_TEST_EXECUTION para asegurar límites de CPU, memoria y tiempo.

5. **Persistencia PostgreSQL:** Guardar todos los resultados en la base de datos de la Fase 16 con el adaptador de dialecto y flujo vertical configurado.

6. **FunctionRepairEngine Integración:** Si el circuito detecta fallo, el sistema puede invocar a FunctionRepairEngine para aplicar reparaciones de patrón simple, seguida de nueva validación.

7. **BinaryAnalysisEngine Integración:** Los resultados del análisis binario (ZIP/PE/JAVA/Mach-O) pueden servir como evidencia para requisitos relacionados con integridad estructural y detección de formatos.

## 2. FLUO DIAGRAMA OFICIAL (Representación Textual)

```
START
  │
├── PASO 1: Leer y registrar un requisito
│   ├── Extraer del PDF SAAS REA.docx
│   ├── Asignar ID REQ-xxx
│   ├── Definir criterios aceptación
│   └── Estado → NOT_RUN
│
├── PASO 2: Ejecutar prueba real
│   ├── Entorno aislado (ISOLATED_TEST_EXECUTION)
│   ├── Ejecutar tests del validador
│   ├── Registrar output, duración, error
│   └── Estado → PASS/FAIL/PARTIAL/BLOCKED
│
├── PASO 3: ¿Estado es FAIL o PARTIAL?
│   ├── NO → Ir a PASO 5
│   ├── YES → Generar paquete diagnóstico
│   │   ├── Requiesto ID
│   │   ├── Criterios fallados
│   │   ├── Output y logs
│   │   └── Enviar agente (rama aislada)
│
├── PASO 4: Agente propone corrección
│   ├── Diff inspeccionado
│   ├── Pruebas afectadas re-ejecutadas
│   ├── Pruebas de regresión re-ejecutadas
│   └── Nuevo resultado registrado
│
├── PASO 4B: ¿Circuitos completos?
│   ├── Sí → Ir a PASO 3B (ampliar cobertura)
│   └── NO → Continuar con siguiente requisito
│
├── PASO 4B: Ampliar cobertura por módulos
│   ├── Nuevo módulo/analizador agregado
│   ├── Cobertura progresiva
│   └── Documentar resultados reales
│
├── PASO 4B: ¿Circuiticos completos otra vez?
│   ├── Sí → Continuar con siguiente fase
│   └── NO → Documentar y finalizar circuito actual
│
├── PASO 4: Entrega Incremental
│   ├── Registrar requisito → Ejecutar prueba → Guardar → MostrarResultado
│   ├── Ampliar cobertura por módulos
│   ├── NO declarar simuladaNINGUNA integración
│   └── NO declarar prueba no ejecutada
│
└── END: Implementación incremental completada, cobertura ampliada, sistema validado
```

## 3. ETAPAS DE EJECUCIÓN

### Etapa 1: Fundamento (Sprint 1)
- Leer y validar SAAS REA.docx como verdad absoluta
- Establecer documento como fuente de consulta permanente
- Definir estructura de requisito REQ-xx
- **Resultado:** PRD y TRD alineados, autoridad técnica establecida

### Etapa 2: Registro de Requisitos (Sprint 2)
- Extraer requisitos del PDF y asignar identificadores
- Definir criterios de aceptación verificables
- Relacionar cada requisito con sección/página del PDF
- **Resultado:** Base de datos requirements con primeros registros

### Etapa 3: Motor de Validación (Sprints 2-3)
- Implementar adaptadores independientes por categoría
- Configurar estados de validación (NOT_RUN/RUNNING/PASS/FAIL/PARTIAL/BLOCKED/NOT_APPLICABLE)
- Establecer reglas de asignación de estados
- **Resultado:** Motor de validación operable con adaptadores mínimos

### Etapa 4: Entorno Aisladored (Sprints 3-4)
- Configurar entornos con límites de CPU, memoria, tiempo y permisos
- Proteger credenciales y registrar comandos
- **Resultado:** Entorno de ejecución seguro y trazable

### Etapa 5: Reproductividad (Sprint 4)
- Registrar commit/hash, versiones de herramientas, configuración
- Invalidar resultados si cambia el código
- **Resultado:** Resultados reproducibles y auditables

### Etapa 6: Ciclo de Corrección (Sprints 4-5)
- Implementar flujo fallo→informe→corrección→revalidación
- Limitar intentos automáticos
- Solicitar intervención humana cuando corresponda
- **Resultado:** Ciclo de corrección operable y documentado

### Etapa 7: Informe y Aceptación (Sprints 5-6)
- Construir interfaz de consultas por requisito y módulo
- Generar informes exportables de conformidad
- Diferenciar cumplimiento técnico vs. calidad vs. seguridad
- **Resultado:** Reportes operables y diferenciados

### Etapa 8: Entrega Incremental (Sprints 5-6 y posteriores)
- Implementar flujo vertical: registrar requisito → ejecutar prueba → guardar → mostrar resultado
- Ampliar cobertura por módulos progresivamente
- **Nunca** declarar integración simulada ni prueba no ejecutada
- **Resultado:** Constructor REA con validación incrementada y documentada

## 3. INTEGRACIÓN CON CONSTRUCTOR REA EXISTENTE

| Componente Constructor REA | Integración APPFLOW |
|--------------------------|--------------------|
| **Health Checks (Fase 6)** | Validar sistema operativo antes y después de cada circuito |
| **Rate Limiter (Fase 12/13)** | Respetar límites de ejecuciones por minuto/hora |
| **ISOLATED_TEST_EXECUTION (Fase 6)** | Ejecutar todos los tests de validación bajo perfil aislado |
| **BinaryAnalysisEngine (Fase 8§6.3)** | Usar resultados como evidencia para requisitos de integridad/formatos |
| **FunctionRepairEngine (Fase 7)** | Aplicar reparaciones simples tras diagnóstico de fallo, seguir de nueva con validación |
| **PostgreSQL (Fase 16)** | Persistir todos los resultados, estados, evidencias e historial |
| **Audit Logs** | Registrar todas las acciones para trazabilidad completa |

## 4. RESTRICTIONS V.A.A. (No Negociables)

1. **Nunca** declarar integración terminada que esté simulada
2. **Nunca** declarar una prueba que no se haya ejecutado
3. **Nunca** calcular porcentaje de cumplimiento usando solo archivos existentes o afirmaciones del agente
4. **Nunca** reutilizar resultados antiguos sin invalidar por cambio de código
5. **Siempre** ejecutar pruebas en entorno aislado con permisos mínimos
6. **Siempre** registrar evidencia reproducible para cada resultado
7. **Siempre** invalidar resultados si cambia el código validado
8. **Nunca** considerar afirmaciones del agente desarrollador como evidencia suficiente

## 5. KRITERIOS DE VALIDACIÓN DE ENTREGABLES

Un entregable del flujo APPFLOW está validado cuando:

1. ✅ Requisito registrado con ID estable (REQ-xxx)
2. ✅ Criterios de aceptación definidos y documentados
3. ✅ Prueba ejecutada de verdad (no simulada)
3. ✅ Resultado registrado con estado (PASS/FAIL/PARTIAL/BLOCKED/NOT_RUN)
4. ✅ Evidencias almacenadas (logs, output, capturas según corresponda)
5. ✅ Commit/hash del código registrado
6. ✅ Versión de herramientas registrada
7. ✅ Si hay fallo: paquete de diagnóstico generado, agente notificado, nuevas pruebas ejecutadas
8. ✅ Si hay éxito: estado PASS registrado con evidencias
9. ✅ Historial de intentos conservado
10. ✅ Informe diferencia cumplimiento técnico vs. calidad vs. seguridad vs. preparación producción

## 5. KRITERIOS DE RECHAZO DE ENTREGABLE

Un entregable del flujo APPFLOW es RECHAZADO cuando:

1. ❌ No hay registro de requisito con ID estable
2. ❌ No hay criterios de aceptación definidos
3. ❌ La prueba fue simulada, no ejecutada de verdad
4. ❌ No hay estado registrado (solo se afirma "aprueba" sin dato)
5. ❌ No hay evidencias asociadas
6. ❌ No hay commit/hash registrado
7. ❌ No hay versión de herramientas registrada
8. ❌ No hay historial de intentos conservado
9. ❌ Se declara "listo para producción" basándose solo en tests automatizados sin más

## 6. MAPA DE RIESGOS V.A.A.

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| Probar sin entorno aislado | Alta | Siempre usar ISOLATED_TEST_EXECUTION perfil |
| Afirmaciones tomadas como verdad | Alta | Solo aceptar evidencia de pruebas ejecutadas |
| Reutilizar resultados antiguos | Media | Invalidar si cambia commit/hash del código |
| Ampliar cobertura sin circuito completado | Media | Verificar circuito extremo a extremo primero |
| Declarar listo sin evidencia | Alta | Requerir todas las validaciones arriba especificadas |
| Saltarse circuitos extremos | Media | Verificar circuito completo antes de ampliar |

## 6. CONCLUSIÓN V.A.A.

**El flujo APPFLOW establece el método oficial y no negociable para la operación de Implementation Validator dentro de Constructor REA.**

**Principios innegociables:**
1. Verdad absoluta: SAAS REA.docx es la fuente
2. Pruebas de verdad: Ejecutar, no simular
3. Reprodicibilidad: Registrar, no asumir
4. Independencia: Separar validador del agente modificador
5. Corrección: Ciclo estructurado, no aleatorio
6. Entrega: Incremental, nunca simulado

**Estado de implementación actual:** Fase de inicio. Los 6 documentos oficiales están construidos y alineados. Próximo paso: integración con código base existente y verificación de coherencia.

---
---
**Fuente absoluta: SAAS REA.docx (220.5KB, 211 párrafos, 13,702 caracteres)**
**Todos los documentos oficiales construidos bajo protocolo V.A.A. directiva no negociable.**