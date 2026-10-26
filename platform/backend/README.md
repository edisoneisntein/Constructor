# Backend — Plataforma de Análisis y Migración

Backend del flujo vertical mínimo: ingestión de artefactos → extracción segura →
análisis estático → hallazgos → grafo de arquitectura → persistencia → informe.

## Requisitos

- Python 3.12+
- Node.js 20+ (solo para el analizador TS/JS mediante `@babel/parser`)
- `@babel/parser` disponible en el entorno de Node (se reutiliza el de REA si existe)

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # editar valores; nunca versionar secretos
```

## Ejecución

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Salud: `GET /health`
- Metadatos: `GET /api/v1/meta`
- OpenAPI: `GET /docs`

## Pruebas

```bash
python3 -m pytest
```

Cubre pruebas unitarias (extracción segura, analizador Python, orquestador),
de seguridad (path traversal, symlink, zip bomb, límites, IDOR/inter-organización,
roles) y el flujo vertical E2E por API.

## Configuración

Toda la configuración proviene de variables de entorno (ver `.env.example`).
El nombre del producto es parametrizable (`SIREP_PRODUCT_NAME`). No hay secretos
embebidos en el código.

## Analizador TS/JS

El bridge `bridges/js_analyze.mjs` se ejecuta en un subproceso Node aislado con
tiempo límite y salida NDJSON/JSON. La ruta a `@babel/parser` se resuelve por:

1. `SIREP_BABEL_PARSER` (variable de entorno),
2. `bridges/node_modules/@babel/parser`,
3. caché de `npx` (`~/.npm/_npx/*/node_modules/@babel/parser`).

Si Node o `@babel/parser` no están disponibles, el análisis continúa con los
analizadores disponibles y registra la limitación de forma explícita
(`COMPLETED_WITH_LIMITATIONS`), sin fallar el job.
