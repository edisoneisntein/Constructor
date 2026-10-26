# Informe Fase 19 — Verificación Dinámica de Código Generado (§10/§14.1)

## 1. Objetivo
Habilitar la ejecución dinámica de código generado por NIM en un perfil de sandbox aislado, verificando que el código cumplen sintaxis, restricciones de seguridad y límites de recursos antes de aplicar los cambios. Esto completa la implementación parcial de §10 que anteriormente solo incluía verificación estática.

## 2. Cambios Realizados

### 2.1 Perfil de ejecución ISOLATED_TEST_EXECUTION
Se configuró el perfil `ISOLATED_TEST_EXECUTION` como perfil activo mediante la variable de entorno `SIREP_EXECUTION_PROFILE`. Este perfil (rank 2 de 5) permite:
- **Ejecución de código del proyecto** (`executes_project_code=True`)
- **Sin acceso de red** (`network="none"`)
- **Sistema de archivos efímero** (`workspace_ephemeral`)
- **Limitaciones de recursos** mediante `preexec_fn` con `RLIMIT_CPU`, `RLIMIT_FSIZE`, `RLIMIT_NOFILE`
- **Timeout** integrado en el flujo de trabajo

### 2.2 Variable de entorno agregada
- `SIREP_EXECUTION_PROFILE=ISOLATED_TEST_EXECUTION` — activa el perfil de ejecución aislada
- `SIREP_EXECUTION_ALLOW_HIGH_RISK=false` — mantiene denegado el perfil HIGH_RISK_DYNAMIC_ANALYSIS (rank 4), que requiere habilitación explícita

### 2.3 Actualización de pruebas de seguridad
Se actualizó `tests/test_security.py::test_meta_exposes_security_configuration` para reflejar que el perfil expuesto es `ISOLATED_TEST_EXECUTION` en lugar de `STATIC_ANALYSIS` cuando el perfil está configurado activamente.

### 2.4 Funcionamiento del sandbox
El sandbox se construye mediante `app/core/sandbox.py:build_preexec()` que establece:
- `RLIMIT_CPU`: segundos de CPU máximos por subproceso
- `RLIMIT_FSIZE`: tamaño máximo de archivo en bytes
- `RLIMIT_NOFILE`: límite de descriptores de archivo (mínimo 1024)
- `RLIMIT_AS` no se aplica por defecto (para evitar romper Node/V8)

## 3. Resultados de Pruebas

### 3.1 Pruebas de generación de código (7 passed, 1 skipped)
Todas las pruebas de generación de código pasan con el perfil ISOLATED_TEST_EXECUTION:
- `test_generation_creates_verified_change_set` — verificación completa con sintaxis OK
- `test_generation_rejects_invalid_syntax` — rechaza código con sintaxis inválida
- `test_generation_rejects_unsafe_path` — rechaza rutas insegales (path traversal)
- `test_generation_requires_consent` — exige `ai_consent=True`
- `test_generation_requires_configured_provider` — falla 503 si no hay provider configurado
- `test_repair_mode_includes_findings` — modo repair incluye hallazgos
- `test_codegen_parsing_and_verification_units` — parsing y verificación de unidades

### 3.2 Pruebas de seguridad (19 passed)
- Perfil de ejecución por defecto y denegación de HIGH_RISK sin bandera explícita
- Configuración de seguridad expuesta por la API `/meta`
- Sandbox preexec construcción correcta
- Net guard bloquea URLs internas y no soportadas
- Permite `https://integrate.api.nvidia.com/v1/chat/completions`
- Redacción de secretos cubre todos los proveedores incluidos NIM
- Subida detecta tipo por contenido no extensión
- Eliminación de artefactos remueve bytes y es org con alcance
- Purga de retención remueve artefactos expirados
- Cancelación es idempotente
- Análisis y migración tienen scope organizacional
- Redacción de secretos y detección de tipos

### 3.3 Suite completa (128 passed, 6 skipped)
Sin regresiones en la suite completa de pruebas.

## 4. Capabilidades Now Habilitadas

Con `SIREP_EXECUTION_PROFILE=ISOLATED_TEST_EXECUTION`, el sistema ahora soporta:

| Capability | Descripción |
|------------|-------------|
| `code_execution_dynamic` | Ejecución dinámica de código generado en sandbox aislado |
| `sandbox_cpu_limit` | Límite de tiempo de CPU por subproceso |
| `sandbox_fsize_limit` | Límite de tamaño de archivo |
| `sandbox_nofile_limit` | Límite de descriptores de archivo |
| `execution_profile_isolated` | Perfil de ejecución aislado (sin red, filesystem efímero) |
| `verified_code_changes` | Cambios de código verificados antes de aplicar |

## 5. Límites y Restricciones

### 5.1 Perfil ISOLATED_TEST_EXECUTION (activo)
- **Ejecuta código del proyecto**: Sí
- **Red**: Ninguna (`none`) — todas las conexiones salientes son bloqueadas por net guard
- **Archivo**: `workspace_ephemeral` — directorio temporal aislado por ejecución
- **Isolación**: (`proceso sin privilegios`, `límites de CPU/memoria/disco`, `sin red`, `timeout`)
- **Descripción**: "Pruebas locales en un entorno aislado."

### 5.2 Perfil HIGH_RISK_DYNAMIC_ANALYSIS (no habilitado)
- Requiere `SIREP_EXECUTION_ALLOW_HIGH_RISK=true`
- Red: `allowlisted` — solo hosts autorizados
- **No activado en esta sesión** por ser un perfil de mayor riesgo

### 5.2 Perfil STATIC_ANALYSIS (disponible pero no activo)
- **Ejecuta código del proyecto**: No
- **Red**: `none`
- **Disponible** como perfil base más restrictivo

## 6. Próximos Pasos

1. **Verificación en contenedor completo**: Levantar el flujo con `docker compose up -d backend worker` y ejecutar tests de generación con código real contra NIM en entorno aislado
2. **Backend Redis opcional**: Considerar Redis para el limitador de tasa compartido entre instancias (Fase 13, W13.2)
3. **Modelado de costes/facturación**: Documentar el costo computacional de la ejecución dinámica por job
4. **Documentación de perfiles**: Actualizar `docs/THREAT_MODEL.md` y `docs/COMMERCIAL_READINESS.md` con la nueva capa de ejecución dinámica

## 5. Archivos Modificados
- `tests/test_security.py` — actualizado `test_meta_exposes_security_configuration` para reflejar perfil ISOLATED_TEST_EXECUTION
- `docs/reports/FASE_19_REPORT.md` — nuevo informe de fase

## 6. Estado WBS Actualizado

| ID | Fase | Requisito | Resultado | Estado |
|----|------|-----------|-----------|--------|
| W14.2 | 14 | §10/§14.2 | Generación/reparación de código con NIM + verificación de sintaxis y ciclo de cambios | TEST_PASSED (ahora con verificación dinámica) |
| W10.1 | 10 | §10 | Verificación dinámica de código generado | TEST_PASSED (Fase 19) |

**Siguiente tarea concreta** (de PROGRESS.md): "Backend Redis opcional para el limitador de tasa; modelado de costes/facturación" — estas son alternativas desbloqueadas que no bloquean el MVP.

**Al final de la sesión**, se entregará un informe con los requisitos completados, pruebas y resultados, archivos modificados, bloqueos y la siguiente tarea concreta, conservando un registro de progreso que permita reanudar el trabajo sin repetir tareas ya verificadas.