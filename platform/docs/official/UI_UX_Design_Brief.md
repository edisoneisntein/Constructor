# UI/UX Design Brief — Implementation Constructor REA

## User Interface and Experience Design Brief
### Fuente de verdad absoluta: SAAS REA.docx (Párrafos 69-79, 85-105, 119-120, 122-123)

## 1. VISIÓN DE INTERFAZ

**Producto:** Implementation Validator — Constructor REA
**Modulo:** Primera clase de la plataforma (según párrafo 71-72)
**Objetivo de la UI:** Panel de conformidad que permite al usuario consultar requisito por requisito qué se implementó, cómo se verificó y qué evidencia existe.

## 2. ARQUITECTURA DE INTERFAZ

### 1.1 Componentes de la Interfaz

1. **Implementation Validator Panel** (párrafo 71-72)
   - Integrado como módulo de primera clase de la plataforma
   - No como herramienta externa, sino nativo de Constructor REA

2. **Panel de Conformidad** (párrafo 71)
   - Conformidad por requisito y por módulo
   - Visualización general del estado del proyecto

3. **Panel de Requisito Individual** (párrafos 98-106)
   - Al seleccionar un requisito, mostrar automáticamente:
     - La página del PDF (sas rea) que lo origina
     - Los criterios de aceptación definidos
     - Los archivos relacionados (ruta, tipo, descripción)
     - Las pruebas ejecutadas y sus resultados (estado, output, duración)
     - El error concreto, si falla (no genérico, específico)
     - El cambio de código propuesto para corregirlo (diff)
     - El historial de revalidaciones (cuántas veces se intentó, cuándo, resultado)

4. **Panel de Estado General** (párrafos 85-84)
   - Panel superior con métricas globales:
     - 72 / 100 requisitos verificados (párrafo 85)
     - Pruebas fallidas (párrafo 78)
     - 8 requiriendo diagnóstico (párrafo 79)
     - 15 pendientes (párrafo 81)
     - 5 bloqueados (párrafo 82)
   - **Prohibido:** Declarar proyecto listo para producción únicamente porque las pruebas automatizadas pasen (párrafo 195)

### 2.2 Flujo de Interacción del Usuario

**Paso 1: Acceso e Inicio**
- Ingresar al panel Implementation Validator desde el menú principal
- Ver panel de estado general con métricas resumidas
- **Acceso directo:** Mostrar 72/100 requisitos verificados, 8 fallidos, 15 pendientes, 5 bloqueados

**Paso 2: Selección de Requisito**
- Navegar por lista de requisitos (filtrados por estado: PASS, FAIL, PARTIAL, BLOCKED, NOT_RUN)
- O usar barra de búsqueda por ID (REQ-001, REQ-002, etc.) o por descripción parcial
- **Al seleccionar un requisito:** Mostrar automáticamente todo el panel detallado (párrafo 98-106)

**Paso 3: Revisión de Requisito Individual**
El usuario ve en pantalla:

1. **La página del PDF que lo origina** (párrafo 99)
   - Referencia al documento SAAS REA.docx
   - Sección identificada (cuando esté disponible)
   - Número de página (cuando esté disponible)

2. **Los criterios de aceptación** (párrafo 100)
   - Lista completa de criterios de aceptación
   - Cuáles aprobaron y cuáles fallaron
   - Evidencia asociada a cada criterio

3. **Los archivos relacionados** (párrafo 101)
   - Ruta del archivo
   - Tipo de archivo
   - Descripción breve

4. **Las pruebas ejecutadas y sus resultados** (párrafo 102)
   - Lista de pruebas ejecutadas
   - Para cada prueba: status (PASS/FAIL), salida, duración, error si falló
   - No mostrar solo "aprueba" o "fallta" — mostrar concreto

5. **El error concreto, si falla** (párrafo 103)
   - No mensajes genéricos como "error en la prueba"
   - Mostrar el error específico: qué línea, qué función, qué condición falló
   - Incluir evidencia (captura de logs, output del comando)

5. **El cambio de código propuesto para corregirlo** (párrafo 104)
   - Diff del código modificado (rama aislada, no directo a producción)
   - Qué cambió y por qué (según el diagnóstico)
   - Botón "Aplicar corrección en rama aislada" (no modificar producción directo)

6. **El historial de revalidaciones** (párrafo 105)
   - Cuántas veces se intentó validar este requisito
   - Cuándo se intentó cada vez
   - Resultado de cada intento (PASS/FAIL/PARTIAL)
   - Qué cambio se propuso cada vez
   - Quién aprobó/corregió cada intento

### 3. DISEÑO VISUAL

#### 3.1 Indicadores Visuales de Estado

| Estado | Color | Ícono | Descripción |
|--------|-------|-------|-------------|
| PASS | Verde | ✔️ | Requisito aprobado, todas las evidencias suficientes |
| FAIL | Rojo | ✘ | Requisito fallado, algunos criterios sin evidencia suficiente |
| PARTIAL | Naranja | ⚠️ | Algunos criterios aprobados, otros sin evidencia |
| BLOCKED | Gris | 🔒 | Requisito imposibilitado por condiciones externas |
| NOT_RUN | Gris claro | ⓘ | Requisito sin ejecutar aún |

#### 3.2 Distinción de Tipos de Conformidad (párrafo 194-195)

La interfaz debe diferenciar claramente por color/estilo:

- **Cumplimiento técnico:** Código compila, tests pass, estructura correcta
- **Calidad del código:** Complejidad, maintainability, style guides cumplidos
- **Seguridad:** Vulnerabilidades detectadas, exposure de secrets, permisos
- **Preparación para producción:** Escabilidad, monitoreo, fallback mechanisms

**Prohibido:** Declarar proyecto listo para producción únicamente porque las pruebas automatizadas pasen (párrafo 195).

#### 3.3 Flujo de Corrección Visual

1. Usuario selecciona requisito FAIL/PARTIAL
2. Pantalla muestra error concreto + diff de corrección propuesta
3. **Botón principal:** "Corregir y volver a validar"
   - Envía fallo al agente en rama aislada
   - El agente propone corrección en código
   - El validador vuelve a ejecutar pruebas afectadas
   - Resultado mostrado en misma pantalla
4. **Botón secundario:** "Ver historial de revalidaciones"
   - Expande panel lateral con historial completo
5. **Botón "Cancelar"** cierra panel sin acciones

## 4. FLUJO DE INTERACCION DETALLADO

### Paso 1: Acceso e Inicio (párrafo 71)
1. Usuario ingresa al panel Implementation Validator
2. Ve panel de estado general (72/100 verificados, estados por contar)
3. Opcional: Usar barra de búsqueda por ID requisito o filtrar por estado

### Paso 2: Selección de Requisito (párrafos 98-106)
1. Usuario hace clic en un requisito de la lista
2. Panel lateral/overlay se expande mostrando detalle completo
3. O usuario busca requisito específico por ID

### Paso 4: Revisión de Eviencias (párrafo 102)
1. Usuario revisa las pruebas ejecutadas
2. Ve output concreto, no resúmenes vagos
3. Si hay múltiples pruebas, muestra cada una con su estado
4. **Prohibido:** Mostrar solo "aprueba" o "falló" sin detalles

### Paso 5: Acción de Corrección (párrafos 104-105)
1. Si el requisito es FAIL o PARTIAL, se muestran opciones de acción
2. **Opción principal:** "Corregir y volver a validar"
   - Envía diagnóstico al agente de programación
   - El agente propone corrección en rama aislada
   - El sistema vuelve a ejecutar pruebas automáticamente
   - Resultado mostrado en pantalla (nuevo estado)
3. **Opción secundaria:** "Ver historial de revalidaciones"
   - Expande historial de intentos anteriores
   - Cada entrada muestra: fecha, resultado, cambio propuesto
4. **Botón "Cancelar"** cierra el panel detallado y regresa al listado

### Paso 5: Acción Global (párrafo 196-210)
1. Usuario puede iniciar flujo de entrega incremental
2. "Registrar requisito" → "Ejecutar prueba real" → "Guardar resultado" → "Mostrar por qué pasó o falló"
3. **Nunca** permitir declarar integración terminada sin ejecutar pruebas reales
4. **Nunca** permitir declarar prueba que no se ejecutó

## 4. MAPA DE INTERFAZ (Wireframe Conceptual)

```
+======================================================================+
|  Implementation Validator - Constructor REA                          |
+======================================================================+
|  ESTADO GENERAL: 72/100 requisitos verificados                      |
|  [PASS] 58   [FAIL] 12   [PARTIAL] 5   [BLOCKED] 3   [NOT_RUN] 7  |
+----------------------------------------------------------------------+
|  SELECCIONAR UN REQUISITO PARA VER DETALLE                           |
|  Ingresar ID (REQ-001) o hacer clic en cualquier fila              |
+----------------------------------------------------------------------+
|  [ Req-001 ]  PASS                                     |  >> [Details] |
|  [ Req-002 ]  FAIL                                    |  >> [Details] |
|  [ Req-003 ]  PARTIAL                                |  >> [Details] |
+----------------------------------------------------------------------+
|  >> Details: Abre panel lateral/overlay con toda la información    |
+======================================================================+
|  DETAIL VIEW - Req-001                                                                 |
|  PDF Source: sas rea — Section 3, Page 1                              |
|                                                                       |
|  ACCEPTANCE CRITERIA:                                                     |
|  [PASS] Criterion 1: Allow loading a valid ZIP file                       |
|  [FAIL] Criterion 2: Reject non-compatible files                         |
|  [PASS] Criterion 3: Generate verifiable analysis results                  |
|                                                                       |
|  RELATED FILES:                                                         |
|  - /project/src/app.py (Python script, 2KB)                              |
|  - /project/data/test_samples/ (ZIP samples directory)                  |
|                                                                       |
|  EXECUTED TESTS:                                                        |
|  - Test 1: PASS — Time: 2.3s, Output: valid ZIP structure detected        |
|  - Test 2: FAIL — Time: 1.8s — Error: Unexpected file format at byte 50   |
|  - Test 3: PASS — Time: 3.1s — Output: SHA256 hash recorded              |
|                                                                       |
|  ERROR CONCRETE (if FAIL):                                                |
|  Unexpected file format at byte 50 — Expected PK signature, found 0x00     |
|                                                                       |
|  PROPOSED CODE CHANGE (diff):                                             |
|  --- Original ---                                                       |
|  function loadZip(file) { ... }                                          |
|  --- Modified ---                                                       |
|  function loadZip(file) { ... validSignatureCheck(...) ... }             |
|                                                                       |
|  VALIDATION HISTORY:                                                    |
|  2024-01-15: FAIL — Unexpected format — Agent proposed diff-001          |
|  2024-01-20: PASS — Valid ZIP structure detected after fix               |
|  2024-01-25: FAIL — New sample fails different criterion                  |
|                                                                       |
|  [  Corregir y volver a validar  ]   [ Ver historial  ]  [ Cancelar ] |
+======================================================================+
```

## 5. INTERACCIONES CON OTROS SISTEMAS Constructor REA

| Sistema Constructor REA | Tipo de Interacción |
|------------------------|---------------------|
| **Health Checks** (Fase 6) | Validar sistema antes de abrir panel — si health fail, mostrar advertencia y bloquear acceso hasta resolver |
| **Rate Limiter** (Fase 12/13) | Limitar accesos al panel Implementation Validator (máx. 20 requests/minuto por usuario) |
| **ISOLATED_TEST_EXECUTION** (Fase 6) | Todos los tests del panel se ejecutan bajo perfil aislado — si perfil no configurado, mostrar advertencia |
| **BinaryAnalysisEngine** (Fase 8§6.3) | Resultados del análisis binario sirven como evidencia para requisitos de integridad/formatos — los datos se pasan al panel como evidencias |
| **FunctionRepairEngine** (Fase 7) | Si usuario selecciona "Corregir y volver a validar", el sistema puede invocar FunctionRepairEngine para aplicar reparación de patrón simple, seguida de nueva validación automática |
| **PostgreSQL (Fase 16)** | Todos los datos del panel (estados, evidencias, historial) se persisten en base de datos — consultas optimizadas por requisito ID |
| **Audit Logs** | Cada acción en el panel (selección de requisito, vista de detalles, corrección propuesta, nueva validación) se registra en tabla audit_log para trazabilidad |

## 5. RESTRICTIONS V.A.A. (Diseño)

1. **Nunca** mostrar "aprueba" o "falló" sin evidencia concreta y específica
2. **Nunca** permitir declarar proyecto listo para producción solo por tests automatizados (párrafo 195)
3. **Nunca** simular resultados — todo debe basarse en pruebas ejecutadas de verdad
4. **Nunca** reutilizar resultados antiguos sin invalidar por cambio de código (commit/hash)
5. **Siempre** distinguir: cumplimiento técnico vs. calidad vs. seguridad vs. preparación producción
6. **Siempre** registrar commit/hash, versiones de herramientas, configuración, resultados y evidencias
7. **Siempre** invalidar resultados si cambia el código validado
8. **Siempre** ejecutar pruebas en entorno aislado con permisos mínimos (ISOLATED_TEST_EXECUTION)

## 6. KRITERIOS DE DISEÑO VÁLIDO

Un diseño de interfaz está válido cuando:

1. ✅ Cada estado de requisito (PASS/FAIL/PARTIAL/BLOCKED/NOT_RUN) se muestra con indicador visual consistente
2. ✅ Al seleccionar un requisito, toda la información necesaria está disponible en una vista (sin necesidad de navegar a páginas externas)
3. ✅ Los errores concretos muestran línea/condición específica, no mensajes genéricos
4. ✅ El diff de corrección propuesta es legible y accionable
5. ✅ El historial de revalidaciones muestra fecha, resultado y cambio propuesto para cada intento
6. ✅ El panel diferencia: cumplimiento técnico vs. calidad vs. seguridad vs. preparación producción
7. ✅ **Prohibido:** Cualquier indicador que sugiera "listo para producción" basándose solo en tests automatizados

## 7. KRITERIOS DE RECHAZO DE DISEÑO

Un diseño de interfaz es RECHAZADO cuando:

1. ❌ Muestra "aprueba" o "falló" sin evidencia concreta
2. ❌ Permite declarar proyecto listo para producción solo por tests automatizados
3. ❌ Simula resultados sin ejecución real de pruebas
4. ❌ No distingue entre cumplimiento técnico, calidad, seguridad y preparación producción
5. ❌ No permite inspeccionar diff de corrección propuesta
6. ❌ No registra historial de revalidaciones por requisito
7. ❌ No distingue estados por indicadores visuales consistentes

## 7. CONCLUSIÓN V.A.A.

**El UI/UX Design Brief establece el diseño oficial y no negociable para la interfaz del Implementation Validator dentro de Constructor REA.**

**Principios innegociables:**
1. Verdad absoluta: SAAS REA.docx es la fuente
2. Evidencia concreta: No resúmenes, datos específicos
3. Corregibilidad: Diff propuesto y accionable
4. Historial: Seguimiento completo por requisito
5. Distinción: Técnico vs. calidad vs. seguridad vs. producción
6. **Prohibido:** Simular, asumir o declarar listo sin evidencia

**Estado de implementación actual:** Documento construido. Próximo paso: integración con la interfaz de Constructor REA y verificación de coherencia con código existente.

---
---
**Fuente absoluta: SAAS REA.docx (220.5KB, 211 párrafos, 13,702 caracteres)**
**Documento construido bajo protocolo V.A.A. directiva no negociable.**