# Backend Schema — Implementation Constructor REA

## Esquema de Base de Datos y API Oficial
### Fuente de verdad absoluta: SAAS REA.docx (Párrafos 113-123, 154-163, 184-194)

## 1. MOTOR DE PERSISTENCIA

- **Motor:** PostgreSQL (Fase 16 completada, adaptador de dialecto + flujo vertical operativo)
- **ORM:** SQLAlchemy 2.x (compatible con FastAPI existente)
- **Migraciones:** Alembic (versionado de esquema)
- **Conexión:** Configurada via `DATABASE_URL` en `.env` (Fase 16)

## 2. ESQUEMA SQL COMPLETO

### 2.1 Tabla: `requirements`

```sql
CREATE TABLE requirements (
    id                      SERIAL PRIMARY KEY,
    requirement_id          VARCHAR(20) UNIQUE NOT NULL,
    description_original    TEXT NOT NULL,
    source_document         VARCHAR(100) NOT NULL DEFAULT 'sas rea',
    section_reference       VARCHAR(100),
    page_number             INTEGER,
    acceptance_criteria     JSONB NOT NULL DEFAULT '[]',
    dependencies            JSONB DEFAULT '[]',
    related_components      JSONB DEFAULT '[]',
    required_tests          JSONB DEFAULT '[]',
    current_status          VARCHAR(20) NOT NULL DEFAULT 'NOT_RUN'
                            CHECK (current_status IN (
                                'NOT_RUN','RUNNING','PASS','FAIL',
                                'PARTIAL','BLOCKED','NOT_APPLICABLE'
                            )),
    evidence                JSONB DEFAULT '[]',
    limitations             TEXT,
    change_history          JSONB DEFAULT '[]',
    committed_hash          VARCHAR(64),
    tool_versions           JSONB DEFAULT '{}',
    config_snapshot         JSONB DEFAULT '{}',
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_requirements_status ON requirements(current_status);
CREATE INDEX idx_requirements_id ON requirements(requirement_id);
```

**Estructura JSONB de `acceptance_criteria`:**
```json
[
  {
    "id": "AC-001",
    "description": "Allow loading a valid ZIP file",
    "mandatory": true,
    "status": "PASS",
    "evidence_ref": "EV-001"
  }
]
```

**Estructura JSONB de `change_history`:**
```json
[
  {
    "timestamp": "2026-10-19T12:00:00Z",
    "action": "STATUS_CHANGE",
    "from": "NOT_RUN",
    "to": "RUNNING",
    "user": "system",
    "details": "Validation started"
  }
]
```

### 2.2 Tabla: `executions`

```sql
CREATE TABLE executions (
    id                  SERIAL PRIMARY KEY,
    requirement_id      VARCHAR(20) NOT NULL REFERENCES requirements(requirement_id),
    test_type           VARCHAR(50) NOT NULL,
    adapter_name        VARCHAR(100),
    status              VARCHAR(20) NOT NULL DEFAULT 'NOT_RUN'
                        CHECK (status IN ('NOT_RUN','PASS','FAIL')),
    execution_time      FLOAT,
    output              JSONB DEFAULT '{}',
    error_details       TEXT,
    ran_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    committed_hash      VARCHAR(64),
    tool_version        VARCHAR(50),
    environment         JSONB DEFAULT '{}',
    is_regression       BOOLEAN DEFAULT FALSE,
    attempt_number      INTEGER DEFAULT 1
);

CREATE INDEX idx_executions_requirement ON executions(requirement_id);
CREATE INDEX idx_executions_status ON executions(status);
CREATE INDEX idx_executions_ran_at ON executions(ran_at DESC);
```

### 2.3 Tabla: `evidences`

```sql
CREATE TABLE evidences (
    id                  SERIAL PRIMARY KEY,
    requirement_id      VARCHAR(20) NOT NULL REFERENCES requirements(requirement_id),
    execution_id        INTEGER REFERENCES executions(id),
    evidence_type       VARCHAR(50) NOT NULL
                        CHECK (evidence_type IN (
                            'code_output','test_report','screenshot',
                            'log_file','diff_proposal','binary_analysis',
                            'static_analysis','security_scan','other'
                        )),
    file_path           VARCHAR(500) NOT NULL,
    file_hash           VARCHAR(64),
    description         TEXT,
    uploaded_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_evidences_requirement ON evidences(requirement_id);
CREATE INDEX idx_evidences_execution ON evidences(execution_id);
```

### 2.4 Tabla: `audit_log`

```sql
CREATE TABLE audit_log (
    id                  SERIAL PRIMARY KEY,
    action              VARCHAR(100) NOT NULL,
    entity_type         VARCHAR(50) NOT NULL
                        CHECK (entity_type IN ('requirement','execution','evidence','validation_run')),
    entity_id           INTEGER NOT NULL,
    changed_by          VARCHAR(100) DEFAULT 'system',
    changed_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    old_value           JSONB,
    new_value           JSONB,
    client_ip           VARCHAR(45),
    user_agent          VARCHAR(255)
);

CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_changed_at ON audit_log(changed_at DESC);
```

### 2.5 Tabla: `validation_runs`

```sql
CREATE TABLE validation_runs (
    id                  SERIAL PRIMARY KEY,
    run_label           VARCHAR(200),
    status              VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
                        CHECK (status IN ('RUNNING','COMPLETED','FAILED','PARTIAL')),
    committed_hash      VARCHAR(64),
    tool_versions       JSONB DEFAULT '{}',
    config_snapshot     JSONB DEFAULT '{}',
    total_requirements  INTEGER DEFAULT 0,
    passed              INTEGER DEFAULT 0,
    failed              INTEGER DEFAULT 0,
    partial             INTEGER DEFAULT 0,
    blocked             INTEGER DEFAULT 0,
    not_run             INTEGER DEFAULT 0,
    started_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMP,
    notes               TEXT
);

CREATE INDEX idx_validation_runs_status ON validation_runs(status);
```

### 2.6 Tabla: `correction_attempts`

```sql
CREATE TABLE correction_attempts (
    id                  SERIAL PRIMARY KEY,
    requirement_id      VARCHAR(20) NOT NULL REFERENCES requirements(requirement_id),
    execution_id        INTEGER REFERENCES executions(id),
    attempt_number      INTEGER NOT NULL DEFAULT 1,
    diagnosis           TEXT NOT NULL,
    proposed_diff       TEXT,
    proposed_by         VARCHAR(100) DEFAULT 'agent',
    branch_name         VARCHAR(200),
    revalidation_status VARCHAR(20)
                        CHECK (revalidation_status IN ('NOT_RUN','PASS','FAIL','PARTIAL')),
    revalidated_at      TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_correction_requirement ON correction_attempts(requirement_id);
```

## 3. MODELOS PYDANTIC (FastAPI)

### 3.1 Modelos de Entrada

```python
# app/models/validator.py

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class ValidationStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ExecutionStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"


class EvidenceType(str, Enum):
    CODE_OUTPUT = "code_output"
    TEST_REPORT = "test_report"
    SCREENSHOT = "screenshot"
    LOG_FILE = "log_file"
    DIFF_PROPOSAL = "diff_proposal"
    BINARY_ANALYSIS = "binary_analysis"
    STATIC_ANALYSIS = "static_analysis"
    SECURITY_SCAN = "security_scan"
    OTHER = "other"


class AcceptanceCriterion(BaseModel):
    id: str
    description: str
    mandatory: bool = True
    status: Optional[ExecutionStatus] = None
    evidence_ref: Optional[str] = None


class RequirementCreate(BaseModel):
    requirement_id: str = Field(..., pattern=r"^REQ-\d{3,}$")
    description_original: str
    source_document: str = "sas rea"
    section_reference: Optional[str] = None
    page_number: Optional[int] = None
    acceptance_criteria: list[AcceptanceCriterion]
    dependencies: list[str] = []
    related_components: list[str] = []
    required_tests: list[str] = []


class RequirementResponse(BaseModel):
    id: int
    requirement_id: str
    description_original: str
    source_document: str
    section_reference: Optional[str]
    page_number: Optional[int]
    acceptance_criteria: list[dict]
    dependencies: list[str]
    related_components: list[str]
    required_tests: list[str]
    current_status: ValidationStatus
    evidence: list[dict]
    limitations: Optional[str]
    change_history: list[dict]
    committed_hash: Optional[str]
    created_at: datetime
    updated_at: datetime


class ExecutionCreate(BaseModel):
    requirement_id: str
    test_type: str
    adapter_name: Optional[str] = None
    is_regression: bool = False


class ExecutionResponse(BaseModel):
    id: int
    requirement_id: str
    test_type: str
    adapter_name: Optional[str]
    status: ExecutionStatus
    execution_time: Optional[float]
    output: dict
    error_details: Optional[str]
    ran_at: datetime
    committed_hash: Optional[str]
    tool_version: Optional[str]
    is_regression: bool
    attempt_number: int


class CorrectionAttemptCreate(BaseModel):
    requirement_id: str
    diagnosis: str
    proposed_diff: Optional[str] = None
    branch_name: Optional[str] = None


class ValidationRunResponse(BaseModel):
    id: int
    run_label: Optional[str]
    status: str
    committed_hash: Optional[str]
    total_requirements: int
    passed: int
    failed: int
    partial: int
    blocked: int
    not_run: int
    started_at: datetime
    finished_at: Optional[datetime]
```

## 4. API ENDPOINTS

### 4.1 Endpoints de Requisitos

```
GET    /api/v1/validator/requirements              — Listar todos los requisitos
GET    /api/v1/validator/requirements/{req_id}     — Obtener requisito específico
POST   /api/v1/validator/requirements              — Registrar nuevo requisito
PUT    /api/v1/validator/requirements/{req_id}     — Actualizar requisito
DELETE /api/v1/validator/requirements/{req_id}     — Eliminar requisito (solo admin)
GET    /api/v1/validator/requirements?status=FAIL  — Filtrar por estado
```

### 4.2 Endpoints de Ejecuciones

```
GET    /api/v1/validator/executions                        — Listar todas las ejecuciones
GET    /api/v1/validator/executions/{exec_id}              — Obtener ejecución específica
POST   /api/v1/validator/executions                        — Registrar nueva ejecución
GET    /api/v1/validator/requirements/{req_id}/executions  — Ejecuciones por requisito
POST   /api/v1/validator/runs                              — Iniciar run de validación completo
```

### 4.3 Endpoints de Evidencias

```
GET    /api/v1/validator/evidences                          — Listar evidencias
GET    /api/v1/validator/evidences/{ev_id}                  — Obtener evidencia
POST   /api/v1/validator/evidences                          — Subir evidencia
GET    /api/v1/validator/requirements/{req_id}/evidences    — Evidencias por requisito
```

### 4.4 Endpoints de Corrección

```
GET    /api/v1/validator/corrections                        — Listar intentos de corrección
POST   /api/v1/validator/corrections                        — Crear intento de corrección
GET    /api/v1/validator/requirements/{req_id}/corrections  — Correcciones por requisito
POST   /api/v1/validator/corrections/{corr_id}/revalidate   — Revalidar corrección
```

### 4.5 Endpoints de Reportes

```
GET    /api/v1/validator/reports/conformity                 — Reporte de conformidad general
GET    /api/v1/validator/reports/conformity/{module}        — Conformidad por módulo
GET    /api/v1/validator/reports/export?format=json         — Exportar reporte (json/csv/pdf)
GET    /api/v1/validator/dashboard                          — Dashboard resumen (métricas)
```

### 4.6 Endpoints de Runs de Validación

```
GET    /api/v1/validator/runs                               — Listar runs de validación
GET    /api/v1/validator/runs/{run_id}                      — Detalle de run
POST   /api/v1/validator/runs                               — Iniciar nuevo run
```

## 5. INTEGRACIÓN CON CÓDIGO EXISTENTE

### 5.1 Estructura de Directorios Propuesta

```
platform/backend/app/
├── api/
│   └── v1/
│       └── validator.py           # Endpoints FastAPI
├── models/
│   ├── validator.py               # Modelos Pydantic
│   └── validator_db.py            # Modelos SQLAlchemy
├── services/
│   ├── validator_service.py       # Lógica de negocio
│   ├── execution_service.py       # Gestión de ejecuciones
│   └── report_service.py          # Generación de reportes
├── adapters/
│   ├── base.py                    # Adaptador base
│   ├── structural_adapter.py      # Integridad estructural
│   ├── static_analysis_adapter.py # Análisis estático
│   ├── unit_test_adapter.py       # Pruebas unitarias
│   ├── integration_adapter.py     # Pruebas integración
│   ├── security_adapter.py        # Seguridad
│   └── ui_adapter.py              # Interfaz gráfica
└── engines/
    ├── binary_analysis/           # Fase 8§6.3 (EXISTENTE)
    └── function_repair/           # Fase 7 (EXISTENTE)
```

### 5.2 Integración con Engines Existentes

| Engine Existente | Integración con Validator |
|-----------------|--------------------------|
| `BinaryAnalysisEngine` (Fase 8§6.3) | Resultados de `analyze_binary()` se persisten como `evidences` con `evidence_type='binary_analysis'` |
| `FunctionRepairEngine` (Fase 7) | Cuando `POST /corrections` se invoca, FunctionRepairEngine aplica reparaciones de patrón simple; resultado se registra en `correction_attempts` |
| `ISOLATED_TEST_EXECUTION` (Fase 6) | Todas las ejecuciones del adapter se ejecutan bajo este perfil de aislamiento |
| Rate Limiter Redis (Fase 12/13) | Endpoints del validator respetan rate limit (20 req/min por usuario) |
| Health Checks (Fase 6) | Antes de cada run de validación, verificar `GET /health` y `GET /health/ready` |

### 5.3 Migraciones Alembic

```bash
# Crear migración inicial
alembic revision --autogenerate -m "create validator tables"

# Aplicar migración
alembic upgrade head

# Rollback si es necesario
alembic downgrade -1
```

**Migraciones requeridas:**
1. `create_requirements_table` — Tabla requirements
2. `create_executions_table` — Tabla executions
3. `create_evidences_table` — Tabla evidences
4. `create_audit_log_table` — Tabla audit_log
5. `create_validation_runs_table` — Tabla validation_runs
6. `create_correction_attempts_table` — Tabla correction_attempts

## 6. RESTRICCIONES V.A.A.

1. **Nunca** persistir un resultado de ejecución sin `committed_hash` — si no hay hash, el resultado no es reproducible
2. **Nunca** marcar un requisito como PASS sin que todos los criterios obligatorios tengan evidencia registrada en tabla `evidences`
3. **Nunca** reutilizar un resultado de ejecución si `committed_hash` difiere del hash actual del código
4. **Siempre** registrar `tool_versions` y `config_snapshot` en cada `validation_run`
5. **Siempre** escribir en `audit_log` cada cambio de estado de requisito
6. **Siempre** usar `ISOLATED_TEST_EXECUTION` para ejecutar código del repositorio validado
7. **Nunca** ejecutar scripts del repositorio validado en el entorno principal del servidor

## 7. CONCLUSIÓN V.A.A.

**Este esquema de backend establece la estructura oficial de persistencia y API para el Implementation Validator.**

**Estado:** Documento construido. Pendiente: implementación de modelos SQLAlchemy, endpoints FastAPI y migraciones Alembic sobre la base PostgreSQL existente (Fase 16).

---
**Fuente absoluta: SAAS REA.docx (220.5KB, 211 párrafos, 13,702 caracteres)**
**Documento construido bajo protocolo V.A.A. directiva no negociable.**
