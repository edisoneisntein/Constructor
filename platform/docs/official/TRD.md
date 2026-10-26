# TRD — Technical Requirements Document

## Technical Requirements Document para Implementation Constructor REA
### Fuente de verdad absoluta: SAAS REA.docx (Párrafos 108-122)

## 1. ARQUITECTURA DEL SISTEMA

### 1.1 Arquitectura General
El sistema se diseña con una arquitectura de microservicios modulares comunicados a través de APIs definidas, siguiendo el patrón cliente-servidor con separación clara de responsabilidades:

- **Capa de Presentación:** Frontend Next.js + TypeScript (panel de Implementation Validator)
- **Capa de Lógica:** Python + FastAPI (Orquestador de validaciones)
- **Capa de Adaptadores:** Pruebas, analizadores estáticos, verificadores de APIs, seguridad y comprobaciones de interfaz
- **Capa de Ejecución Aislada:** Contenedores o entornos efímeros con límites de CPU, memoria, tiempo, red y permisos
- **Capa de Persistencia:** PostgreSQL para requisitos, ejecuciones, evidencias, incidencias y trazabilidad

### 1.2 Componentes Principales (del doc SAAS REA)

1. **Implementation Validator (Módulo Obligatorio)**
   - Sistema independiente de validación de implementación para SOFTWARE INTELLIGENCE, RECONSTRUCTION & EVOLUTION PLATFORM
   - Objetivo: Verificar de forma reproducible y basada en evidencias que cada requisito del documento "sas rea" esté implementado correctamente
   - No considerar afirmaciones del agente desarrollador, comentarios del código, existencia de archivos ni apariencia de interfaz como pruebas suficientes

2. **Registro de Requisitos**
   - Extraer requisitos del documento, conservar sus referencias a secciones y páginas cuando estén disponibles
   - Asignar identificadores estables (formato REQ-xxx)
   - Para cada requisito registrar:
     - Descripción original
     - Criterios de aceptación verificables
     - Dependencias
     - Componentes y archivos relacionados
     - Pruebas requeridas
     - Estado actual
     - Evidencias y limitaciones
     - Historial de cambios y validaciones

3. **Motor de Validación**
   - Implementar adaptadores independientes para:
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
   - Cada adaptador debe devolver resultados estructurados, código de salida, duración, evidencias, errores y limitaciones
   - Distinguir fallos de una prueba de errores de infraestructura que impiden la ejecución

3. **Estados de Validación (Estados Mínimo Obligatorio):**
   - NOT_RUN: Estado por defecto antes de ejecutar cualquier prueba
   - RUNNING: Estado durante la ejecución de pruebas
   - PASS: Estado cuando todas las pruebas obligatorias aprueban
   - FAIL: Estado cuando alguna prueba obligatoria falla
   - PARTIAL: Estado cuando algunas pruebas aprueban pero otras fallan
   - BLOCKED: Estado cuando la ejecución está impedida por condiciones externas (sin recursos, sin permisos, etc.)
   - NOT_APPLICABLE: Estado cuando el requisito no aplica al contexto actual
   - Regla: Un requisito solo puede aprobarse cuando todos sus criterios obligatorios tienen evidencia suficiente
   - Prohibido: Calcular porcentaje de cumplimiento usando solo archivos existentes, pruebas omitidas o afirmaciones del agente

4. **Ejecución Segura (Requisito Crítico):**
   - Ejecutar código no confiable en entornos aislados con:
     - Permisos mínimos necesarios por operación
     - Límites de recursos (CPU, memoria, tiempo, red)
     - Directorios controlados por operación
     - Políticas de red restrictivas
   - No ejecutar automáticamente scripts del repositorio en el entorno principal
   - Inspeccionar dependencias y configurar entorno de prueba antes de ejecutar código potencialmente peligroso
   - Proteger credenciales, datos del usuario y secretos
   - Registrar los comandos ejecutados
   - Evitar operaciones destructivas sin autorización

5. **Independencia y Reproductibilidad:**
   - Separar el motor de validación del agente que modifica el código
   - Registrar el commit o hash del código validado
   - Registrar versiones de herramientas, configuración, resultados y evidencias
   - Si cambia el código, invalidar o volver a ejecutar las pruebas afectadas
   - No reutilizar resultados antiguos como prueba de la versión actual
   - Incluir pruebas negativas, valores límite y, cuando sea útil, pruebas de propiedades y mutation testing

6. **Integración con Constructor REA:**
   - El Implementation Validator es un módulo más de la plataforma Constructor REA
   - Está sujeto a verificar sus capacidades reales, nunca como juez único
   - Los adaptadores deben ser compatibles con los engines existentes:
     - BinaryAnalysisEngine (ZIP/PE/JAVA/Mach-O)
     - FunctionRepairEngine (patrones de reparación)
     - Rate limiter Redis (job_queue_backend='external')
     - ISOLATED_TEST_EXECUTION perfil habilitado
     - PostgreSQL adapter (§4.4): adaptador de dialecto + flujo vertical

## 2. ESPECIFICACIONES TÉCNICAS

### 2.1 Base de Datos (PostgreSQL)

**Tabla: requirements**
| Campo | Tipo | Restricciones |
|-------|------|---------------|
| id | INTEGER | Auto-increment, PK |
| requirement_id | VARCHAR(20) | UNIQUE, formato REQ-xxx |
| description_original | TEXT | NOT NULL |
| source_document | VARCHAR(100) | default 'sas rea' |
| section_reference | VARCHAR(100) | nullable |
| page_number | INTEGER | nullable |
| acceptance_criteria | JSON | NOT NULL (arreglo de strings) |
| dependencies | JSON | nullable |
| related_components | JSON | nullable |
| required_tests | JSON | nullable |
| current_status | VARCHAR(20) | CHECK: NOT_RUN, RUNNING, PASS, FAIL, PARTIAL, BLOCKED, NOT_APPLICABLE |
| evidence | JSON | nullable (arreglo de objetos: ruta, tipo, descripción) |
| limitations | TEXT | nullable |
| change_history | JSON |nullable (arreglo de objetos: fecha, acción, usuario) |
| created_at | TIMESTAMP | DEFAULT NOW() |
| updated_at | TIMESTAMP | DEFAULT NOW() |

**Tabla: executions**
| Campo | Tipo | Restricciones |
|-------|------|---------------|
| id | INTEGER | Auto-increment, PK |
| requirement_id | VARCHAR(20) | FK → requirements.requirement_id |
| test_type | VARCHAR(50) | NOT NULL |
| status | VARCHAR(20) | CHECK: NOT_RUN, PASS, FAIL |
| execution_time | FLOAT | nullable |
| output | JSON | nullable |
| error_details | TEXT | nullable |
| ran_at | TIMESTAMP | DEFAULT NOW() |
| committed_hash | VARCHAR(64) | nullable (git commit SHA) |
| tool_version | VARCHAR(50) | nullable |

**Tabla: evidences**
| Campo | Tipo | Restricciones |
|-------|------|---------------|
| id | INTEGER | Auto-increment, PK |
| requirement_id | VARCHAR(20) | FK → requirements.requirement_id |
| evidence_type | VARCHAR(50) | NOT NULL (code_output, test_report, screenshot, etc.) |
| file_path | VARCHAR(255) | NOT NULL |
| description | TEXT | nullable |
| uploaded_at | TIMESTAMP | DEFAULT NOW() |

**Tabla: audit_log**
| Campo | Tipo | Restricciones |
|-------|------|---------------|
| id | INTEGER | Auto-increment, PK |
| action | VARCHAR(100) | NOT NULL |
| entity_type | VARCHAR(50) | NOT NULL (requirement, execution, evidence) |
| entity_id | INTEGER | NOT NULL |
| changed_by | VARCHAR(100) | nullable |
| changed_at | TIMESTAMP | DEFAULT NOW() |
| old_value | JSON | nullable |
| new_value | JSON | nullable |

### 2.2 Entorno de Ejecución

- **Contenedores o entornos efímeros** con límites de:
  - CPU (cantidad máxima en núcleos o porcentaje)
  - Memoria (Límitos en MB/GB con política OOM Kill)
  - Tiempo (timeout máximo en segundos por ejecución)
  - Red (políticas de red restrictivas, sin acceso saliente a menos que sea estrictamente necesario)
  - Permisos (usuario mínimo, sin privilegios de root, directorios de escritura controlados)
- **No ejecutar automáticamente scripts del repositorio** en el entorno principal
- **Inspeccionar dependencias** y configurar entorno de prueba antes de ejecutar código potencialmente peligroso
- **Proteger credenciales, datos del usuario y secretos** (usar variables de entorno, nunca hardcodeado)
- **Registrar los comandos ejecutados** para auditoría completa
- **Evitar operaciones destructivas** sin autorización explícita

### 2.3 Independencia y Reproductibilidad

- **Separar el motor de validación** del agente que modifica el código
- **Registrar el commit o hash** del código validado (longitud SHA-256 o similar)
- **Registrar versiones de herramientas** (versiones exactas de pytest, pefile, FastAPI, etc.)
- **Registrar configuración** utilizada en cada ejecución (archivo .env, parámetros de entorno, etc.)
- **Registrar resultados y evidencias** (archivos de salida, reportes generados, logs capturados)
- **Si cambia el código, invalidar o volver a ejecutar** las pruebas afectadas
- **No reutilizar resultados antiguos** como prueba de la versión actual
- **Incluir pruebas negativas, valores límite** y, cuando sea útil, pruebas de propiedades y mutation testing

### 2.4 Estados de Validación (Implementación)

Utilizar como mínimo los siguientes estados:

| Estado | Significado | Cuándo usar |
|--------|-------------|-------------|
| NOT_RUN | Estado por defecto | Antes de ejecutar cualquier prueba sobre el requisito |
| RUNNING | Durante ejecución | Cuando las pruebas están en curso de ejecución |
| PASS | Aprobado | Cuando todas las pruebas obligatorias aprueban (todos los criterios críticos tienen evidencia suficiente) |
| FAIL | Fallado | Cuando alguna prueba obligatoria falla (algún criterio crítico sin evidencia suficiente) |
| PARTIAL | Parcial | Cuando algunas pruebas aprueban pero otras fallan (algunos criterios tienen evidencia, otros no) |
| BLOCKED | Bloqueado | Cuando la ejecución está impedida por condiciones externas (sin recursos, sin permisos, dependencia no disponible) |
| NOT_APPLICABLE | No aplicable | Cuando el requisito no aplica al contexto actual del proyecto |

**Regla de oro:** Un requisito solo puede aprobarse (estado PASS) cuando todos sus criterios obligatorios tienen evidencia suficiente registrada.

**Prohibido:** Calcular porcentaje de cumplimiento usando únicamente archivos existentes, pruebas omitidas o afirmaciones del agente sin evidencia de prueba ejecutada.

### 2.5 Ciclo de Corrección (Flujo Obligatorio)

Cuando un requisito falle (estado FAIL o PARTIAL):

1. **Generar informe de fallo** con evidencias reproducibles (no capturas subjetivas, datos medibles)
2. **Identificar el requisito y los criterios incumplidos** (mostrar cuál exactamente y por qué)
3. **Preparar paquete de diagnóstico** para el agente desarrollador (includes: requisito ID, criterios fallados, output de pruebas, logs del entorno)
4. **Permitir que el agente proponga una corrección** en una rama o entorno aislado (no modificar código directo en producción)
5. **Inspeccionar el diff** (diferencia de código) y ejecutar de nuevo las pruebas afectadas
6. **Ejecutar de nuevo las pruebas de regresión** pertinentes (para asegurar que no se introdujo nueva degeneración)
7. **Conservar el historial de intentos y resultados** (para tracking a largo plazo y análisis de patrones)
8. **Solicitar intervención humana** ante riesgos elevados, decisiones ambiguas o cambios sensibles (no automatizar todo)
9. **Limitar intentos automáticos** para evitar ciclos infinitos de corrección sin supervisión (establecer máximo de reintentos)

### 2.6 Informe y Aceptación (Formato de Salida)

Construir una interfaz para consultar:

- **Conformidad por requisito y por módulo** (matriz visual o tabla)
- **Pruebas aprobadas, fallidas, parciales y no ejecutadas** (por requisito y en resumen)
- **Evidencias y registros** (accesibles por fila, downloadables)
- **Defectos detectados** (listado con descripción y gravedad)
- **Cambios pendientes de revalidación** (requisitos que fueron modificados y necesitan nueva verificación)
- **Historial de correcciones** (qué se corrigió, cuándo, por quién, resultados después de corrección)
- **Bloqueos y limitaciones** (condiciones que impiden avanzar en ciertos requisitos)
- **Informe exportable de conformidad** (formato JSON/CSV/PDF para partes interesadas)

**Diferenciar claramente:**
- Cumplimiento técnico (código compila, tests pass)
- Calidad del código (complejidad, maintainability, style guides)
- Seguridad (vulnerabilidades, exposure de secrets, permisos)
- Preparación para producción (escabilidad, monitoreo, fallback mechanisms)

**Prohibido:** Declarar un proyecto listo para producción únicamente porque las pruebas automatizadas pasen.

### 2.7 Entrega Incremental (Flujo de Trabajo)

**Paso 1: Inspeccionar repositorio y herramientas existentes**
- Revisar qué herramientas ya están integradas (pytest, pefile, FastAPI, etc.)
- Identificar qué analizadores estáticos están disponibles
- Revisar la estructura del código base

**Paso 2: Implementar flujo vertical funcional**
- **Registrar un requisito** (con ID, descripción, criterios de aceptación, relación con PDF)
- **Ejecutar una prueba real** sobre el código (no simulada)
- **Guardar el resultado** (estado, salida, evidencia, hora de ejecución)
- **Mostrar en la interfaz** por qué pasó o falló (evidencias concretas, no descripciones vagas)

**Paso 2B: Ampliar cobertura por módulos**
- **Ejecutar las pruebas propio validador** y documentar resultados reales
- **Ampliar cobertura por módulos** progresivamente (no intentar cubrir todo de una vez)
- **NO declarar integración terminada** que esté simulada (todas las pruebas deben ejecutarse de verdad)
- **NO declarar prueba** que no se haya ejecutado nunca (registro estado NOT_RUN es válido, pero documentar por qué)

### 2.8 Integración con Constructor REA (Casos de Uso Específicos)

El Implementation Validator se integra con los engines existentes de Constructor REA de las siguientes maneras:

1. **Validación de BinaryAnalysis:** Los resultados del BinaryAnalysisEngine (ZIP/PE/JAVA/Mach-O análisis) sirven como evidencia para requisitos relacionados con integridad estructural, detección de formatos y extracción de metadatos.

2. **Validación de FunctionRepair:** Las reparaciones aplicadas por FunctionRepairEngine deben ser seguidas de validación de que los criterios de aceptación siguen cumpliéndose (no solo que "el engine hizo una reparación").

3. **Validación con ISOLATED_TEST_EXECUTION:** Todos los tests de validación deben ejecutarse bajo el perfil ISOLATED_TEST_EXECUTION configurado en la Fase 6, asegurando límites de CPU, memoria y tiempo.

4. **Validación contra PostgreSQL:** Los resultados de validación deben persistirse en la base de datos PostgreSQL de la Fase 16, con el adaptador de dialecto y flujo vertical configurado.

5. **Validación con Rate Limiter:** Los tests de validación deben respetar el rate limiter Redis configurado en la Fase 12/13, no ejecutando un número excesivo de validaciones en corto tiempo.

## 3. MAPEADO SAAS REA → TRD

| Saas REA Section | TRD Section | Status |
|-----------------|-------------|--------|
| Párrafos 108-112 | 1. Arquitectura del Sistema | ✅ Definido |
| Párrafos 113-118 | 2. Componentes Principales | ✅ Definido |
| Párrafos 119-122 | 2.1-2.7 Especificaciones Técnicas | ✅ Definido |
| Párrafos 122-123 | Módulo Obligatorio: Implementation Validator | ✅ Definido |
| Párrafos 124-136 | Registro de Requisitos | ✅ Definido |
| Párrafos 139-153 | Motor de Validación (adaptadores) | ✅ Definido |
| Párrafos 154-163 | Estados de Validación | ✅ Definido |
| Párrafos 165-168 | Ejecución Segura | ✅ Definido |
| Párrafos 169-173 | Independencia y Reproductibilidad | ✅ Definido |
| Párrafos 174-183 | Ciclo de Corrección | ✅ Definido |
| Párrafos 184-194 | Informe y Aceptación | ✅ Definido |
| Párrafos 196-210 | Entrega Incremental | ✅ Definido |

# NOTA DE ACTUALIZACIÓN
**Fuente absoluta: SAAS REA.docx (220.5KB, 211 párrafos, 13,702 caracteres)**
**Este TRD es la especificación técnica que guiará la implementación del Implementation Validator en Constructor REA.**
**Cualquier desviación de estos requisitos debe documentarse y justificarse técnicamente, aceptando limitaciones conocidas.**