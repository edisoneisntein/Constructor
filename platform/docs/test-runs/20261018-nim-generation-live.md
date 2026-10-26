# Registro de verificación — Generación de código con NIM en vivo (§10, §15, §19.6)

- **ID**: 20261018-nim-generation-live
- **Fecha**: 2026-10-18 (UTC-05:00)
- **Tipo**: verificación en vivo (integración real con proveedor de IA + ciclo de cambios).
- **Proveedor**: NVIDIA NIM (único). Modelo `nvidia/nemotron-3-super-120b-a12b`.
- **Resultado**: `TEST_PASSED`
- **Comando**:
  ```bash
  SIREP_API_BASE_URL=http://127.0.0.1:8000 python -m scripts.verify_nim_generation
  ```
- **Entorno**: contenedores `backend`, `worker`, `frontend` en marcha; NIM con DNS
  resuelto y credencial presente.
- **Evidencia (real)**:
  - `analysis status: COMPLETED`.
  - `generation status: 201` · `model: nvidia/nemotron-3-super-120b-a12b` · `mode: repair`
    · `latency_ms: 6679.38`.
  - `summary: Fixed add function to perform addition instead of subtraction.`
  - `limitations: []`.
  - Verificación: `src/math_utils.py [python] MODIFIED syntax_checked=True
    syntax_ok=True +1/-1`.
  - Diff:
    ```diff
    --- a/src/math_utils.py
    +++ b/src/math_utils.py
    @@ -1,2 +1,2 @@
     def add(a, b):
    -    return a - b
    +    return a + b
    ```
  - Ciclo §15: `approve: 200 → apply: 200 → validate: 200` · `final status: VALIDATED`.
  - `validation_result`: `{"status": "COMPLETED", "findings_count": 1, "node_count": 2,
    "edge_count": 1, "files_analyzed": 1, "limitations": []}`.
- **Failed**: 0
- **Not run**: 0
- **Notas**:
  - El código generado se **verificó** (sintaxis Python con `ast.parse` + reanálisis
    estático tras aplicar) antes y después de persistir el cambio; ninguna propuesta
    inválida se registra.
  - La generación exige consentimiento de transmisión (`ai_consent`) por §14.
  - Complementado por la suite automática (transporte NIM falso): `118 passed,
    2 skipped` (`docs/test-runs/20261018-190313`).
