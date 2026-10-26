# Informe Fase 14 — Integración con NVIDIA NIM (§12, §13, §23)

## 1. Objetivo
Convertir en real la integración de IA de la plataforma usando **NVIDIA NIM como
proveedor único** (sin Gemini): cliente OpenAI-compatible, verificación en vivo de
credenciales/modelo/inferencia, endpoint de estado y evidencia de ejecución real.

## 2. Archivos creados
- `platform/backend/app/engines/migration/nim_client.py` — cliente NIM
  (`/models`, `/chat/completions`), errores tipados, transporte inyectable.
- `platform/backend/tests/test_nim_client.py` — 6 pruebas + 1 en vivo (gated).
- `platform/backend/scripts/verify_nim.py` — verificación reproducible.
- `platform/docs/test-runs/20261018-nim-live-verification.md`.
- `platform/.gitignore`, `platform/backend/.env`, `platform/.env` (locales, no
  versionados).

## 3. Archivos modificados
- `app/core/config.py` — carga de `.env` local (`python-dotenv`, `override=False`),
  `nim_timeout_seconds`, modelo por defecto `nvidia/nemotron-3-super-120b-a12b`.
- `app/services/migration_service.py` — `build_nim_client`, `verify_nim_connection`.
- `app/api/v1/migrations.py` — `POST /api/v1/migrations/nim/verify`.
- `app/schemas/models.py` — `NimStatusOut`.
- `app/api/v1/router.py` — `/meta`: `capabilities.nim_integration` y bloque `ai`.
- `backend/requirements.txt` (+`python-dotenv==1.2.2`), `backend/.env.example`.
- `docker-compose.yml` — env NIM en `backend`/`worker`; `dns` (1.1.1.1, 8.8.8.8).
- `docs/{PROGRESS,LIMITATIONS,DEPLOYMENT}.md`.

## 4. Componentes reutilizados
- `httpx` (ya presente) como transporte HTTP; `Settings` para configuración;
  motor de migración (§12) sin cambios de contrato.

## 5. Funcionalidades implementadas
- Cliente NIM real con listado de modelos e inferencia de chat.
- Endpoint autenticado de verificación (rol developer).
- Capacidad declarada en `/meta` y modelo por defecto corregido a uno realmente
  servido por la cuenta.
- Resolución DNS en contenedores (necesaria para llamadas salientes).

## 6. Pruebas ejecutadas
- `pytest` → `docs/test-runs/20261018-184857.{json,md}` (**111 passed, 1 skipped**).
- Verificación en vivo → `docs/test-runs/20261018-nim-live-verification.md`.
- `python -m scripts.verify_nim` → `TEST_PASSED`.

## 7. Resultados reales
- NIM: `configured=true, reachable=true, model_available=true, models_count=81,
  completion_ok=true` (latencia ≈0.9–1.7 s), tanto en local como en contenedor.
- `POST /api/v1/migrations/nim/verify` → 200; `GET /api/v1/meta` →
  `nim_integration=IMPLEMENTED`, `ai.provider=nvidia_nim`.

## 8. Pruebas no ejecutadas
- Uso de NIM dentro de los motores generativos (§6/§10) más allá de la
  verificación: `PROPOSED_NOT_IMPLEMENTED`.
- Gemini: no aplica (proveedor no soportado por decisión del proyecto).

## 9. Problemas pendientes
- Especificar y probar el uso de NIM en generación/reparación de código con
  verificación de resultados (§10).
- PostgreSQL (Fase 13 pendiente).

## 10. Riesgos
- Dependencia de un proveedor externo: sin `SIREP_NIM_API_KEY` la capacidad queda
  `DISABLED` (degradación honesta). Coste por tokens aún no modelado (§costes).

## 11. Instrucciones para reproducir
```bash
cd platform/backend
python3 -m pip install -r requirements.txt
printf 'SIREP_NIM_API_KEY=nvapi-...\n' >> .env
python -m scripts.verify_nim
cd ../.. && docker compose up -d --build
# POST /api/v1/migrations/nim/verify (con token)
```

## 12. Próxima fase
- Uso de NIM en generación de cambios (§6/§10) con verificación de resultados.
- PostgreSQL tras la capa de repositorio (Fase 13).

---

# Anexo — W14.2/W14.3: Generación de código con NIM (§10/§15/§18)

## Objetivo
Usar NIM para **generar o reparar** código con verificación real y registrar el
resultado como un cambio propuesto §15.

## Archivos creados
- `app/engines/features/__init__.py`, `app/engines/features/nim_codegen.py` —
  prompt, parseo de la respuesta JSON y verificación (ruta segura, contenido,
  sintaxis `ast`/JSON).
- `app/services/generation_service.py` — flujo completo y persistencia vía §15.
- `app/api/v1/generations.py` — `POST /api/v1/analyses/{analysis_id}/generations`.
- `tests/test_generation.py` — 7 pruebas (transporte NIM falso) + 1 en vivo (gated).
- `scripts/verify_nim_generation.py` — E2E en vivo.
- `frontend/components/GenerationPanel.tsx` + `createGeneration` en `lib/api.ts`.
- `docs/test-runs/20261018-nim-generation-live.md`.

## Archivos modificados
- `app/schemas/models.py` — `GenerationCreate`, `GenerationFileVerification`,
  `GenerationOut`.
- `app/api/v1/router.py` — registro del router y `capabilities.ai_code_generation`.
- `frontend/app/projects/[id]/page.tsx` — inserción de `GenerationPanel`.
- `docs/{PROGRESS,LIMITATIONS,ARCHITECTURE,DEPLOYMENT}.md`.

## Funcionalidades
- Modos `feature` y `repair`; el modo `repair` incluye los hallazgos del archivo
  objetivo en el prompt.
- **Verificación**: ruta segura (`safe_relative_path`), contenido no vacío,
  sintaxis Python (`ast.parse`) y JSON. Los lenguajes sin comprobador se marcan como
  «sintaxis no verificada» (honesto).
- Un fallo de verificación **no persiste** ningún cambio
  (`generation_verification_failed`); sin `ai_consent` → `409 ai_consent_required`;
  sin clave NIM → `503 capability_unavailable`.
- El cambio válido se registra como conjunto `PROPOSED` (`produced_by_rule`
  `NIM-GENERATE`/`NIM-REPAIR`) y sigue el ciclo §15 (aprobar → aplicar → validar →
  revertir).

## Pruebas ejecutadas
- `pytest`: `118 passed, 2 skipped` (`docs/test-runs/20261018-190313`).
- E2E en vivo: `docs/test-runs/20261018-nim-generation-live.md` (`TEST_PASSED`).
- UI E2E Playwright: `1 passed` (regresión).

## Resultados reales
- NIM corrigió `add` (`a - b` → `a + b`) en `latency_ms ≈ 6.7 s`; verificación
  `syntax_ok=True +1/-1`; ciclo `approve/apply/validate = 200`, estado
  `VALIDATED`, reanálisis `COMPLETED`.

## Pruebas no ejecutadas / alcance
- Verificación **dinámica** (ejecutar pruebas sobre el código generado): requiere
  ejecución aislada (§14.1) → pendiente. La verificación actual es estática.

## Riesgos
- Latencia del modelo `nemotron-3-super` (~6.7 s para una corrección trivial);
  coste por tokens no modelado.
- Calidad del código generado depende del modelo; la verificación estática no
  garantiza comportamiento correcto (documentado en `LIMITATIONS`).
