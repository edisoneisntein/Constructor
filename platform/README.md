# Plataforma de Análisis y Migración (SIREP)

Implementación incremental del producto descrito en `SAAS REA.pdf`. El primer
flujo vertical está operativo de extremo a extremo:

```
Artifact Ingestion → Safe Extraction → Static Analysis → Findings → Architecture Graph → Persisted Results
```

## Estructura

```
platform/
├── backend/      API FastAPI, motores de análisis, grafo, persistencia, pruebas
├── frontend/     Next.js + TypeScript + Tailwind (interfaz mínima)
├── bridges/      (dentro de backend) bridge Node para análisis TS/JS
└── docs/         WBS, arquitectura, threat model, limitaciones e informes de fase
```

## Documentación

- `docs/FASE_0_WBS.md` — WBS y trazabilidad a secciones del PDF.
- `docs/audit/REA_AUDIT.md` — auditoría de REA (Fase 1).
- `docs/ARCHITECTURE.md` — arquitectura por capas.
- `docs/THREAT_MODEL.md` — modelo de amenazas y mitigaciones.
- `docs/LIMITATIONS.md` — limitaciones conocidas y estado honesto.
- `docs/reports/FASE_1_REPORT.md`, `docs/reports/FASE_2_REPORT.md` — informes §23.

## Puesta en marcha rápida

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 npm run dev
```

Abrir `http://localhost:3000`, registrarse, crear un proyecto, subir un ZIP con
código fuente y ejecutar el análisis.

## Contenedores

`docker-compose.yml` define `backend` y `frontend`. Ver `docs/LIMITATIONS.md` para
el estado de verificación de los contenedores.

## Principios de trabajo (del PDF)

- Veracidad técnica y evidencia trazable; nada se afirma como hecho sin evidencia.
- Estados explícitos por fase y por requisito.
- No se envía código fuente a proveedores externos sin consentimiento explícito.
- No hay secretos en el código; toda credencial proviene del entorno.
