# Índice de ejecuciones de pruebas (§19.6)

| Fecha (UTC) | Estado | Etiqueta | Resultado | Registro |
|---|---|---|---|---|
| 2026-10-18T16:10:59Z | TEST_PASSED | Fase 11 — seguridad y escalabilidad | 61p/0f/0e/0s | [20261018-161059.json](20261018-161059.json) |
| 2026-10-18T16:26:43Z | TEST_PASSED | Fase 11 (observabilidad/cuotas) + Fase 12 (uso/docs) | 69p/0f/0e/0s | [20261018-162643.json](20261018-162643.json) |
| 2026-10-18T16:40:41Z | TEST_PASSED | Fase 8 W8.1: analisis binario estatico (§6.2) | 78p/0f/0e/0s | [20261018-164041.json](20261018-164041.json) |
| 2026-10-18T17:18:58Z | TEST_PASSED | Fase 12 W12.2: build/run contenedores + fix borde transaccional | 80p/0f/0e/0s | [20261018-171858.json](20261018-171858.json) |
| 2026-10-18T17:34:16Z | TEST_PASSED | Fase 8 W8.3: formatos §6.1 (WASM/DEX/PYC/ZIP-JAR-APK/COFF/AR) | 89p/0f/0e/0s | [20261018-173416.json](20261018-173416.json) |
| 2026-10-18T17:42:26Z | TEST_PASSED | Fase 8 W8.4: inspeccion acotada de contenido interno ZIP/JAR/APK | 91p/0f/0e/0s | [20261018-174226.json](20261018-174226.json) |
| 2026-10-18T18:05:13Z | TEST_PASSED | Fase 12 W12.4 + fix grafo (PK compuesta) | 92p/0f/0e/0s | [20261018-180513.json](20261018-180513.json) |
| 2026-10-18T18:27:57Z | TEST_PASSED | Fase 13 W13.1/W13.2 cola externa + rate limit compartido | 104p/0f/0e/0s | [20261018-182757.json](20261018-182757.json) |
| 2026-10-18T18:31:04Z | TEST_PASSED | Fase 13 W13.1-W13.3 cola externa, rate limit compartido, purga programada | 105p/0f/0e/0s | [20261018-183104.json](20261018-183104.json) |
| 2026-10-18T18:48:57Z | TEST_PASSED | Fase 14 integracion NVIDIA NIM (proveedor unico de IA) | 111p/0f/0e/1s | [20261018-184857.json](20261018-184857.json) |
| 2026-10-18T19:03:13Z | TEST_PASSED | Fase 15 generación NIM (§10) + verificación | 118p/0f/0e/2s | [20261018-190313.json](20261018-190313.json) |
| 2026-10-18T19:23:47Z | TEST_PASSED | Fase 16 PostgreSQL (§4.4): adaptador de dialecto + flujo vertical en PG | 122p/0f/0e/2s | [20261018-192347.json](20261018-192347.json) |

## Verificaciones manuales (E2E / en vivo)

| Fecha | Estado | Descripción | Registro |
|---|---|---|---|
| 2026-10-18 | TEST_PASSED | Contenedores: build/run + flujo vertical | [20261018-container-e2e.md](20261018-container-e2e.md) |
| 2026-10-18 | TEST_PASSED | UI E2E con navegador real (Playwright) | [20261018-ui-e2e-playwright.md](20261018-ui-e2e-playwright.md) |
| 2026-10-18 | TEST_PASSED | Worker externo + rate limit + purga | [20261018-external-worker-e2e.md](20261018-external-worker-e2e.md) |
| 2026-10-18 | TEST_PASSED | NVIDIA NIM en vivo (proveedor de IA) | [20261018-nim-live-verification.md](20261018-nim-live-verification.md) |
| 2026-10-18 | TEST_PASSED | Generación de código con NIM en vivo (§10) | [20261018-nim-generation-live.md](20261018-nim-generation-live.md) |
| 2026-10-18 | TEST_PASSED | Persistencia PostgreSQL (§4.4) | [20261018-postgresql-persistence.md](20261018-postgresql-persistence.md) |
