# Registro de verificación — Persistencia PostgreSQL (§4.4, §19.6)

- **ID**: 20261018-postgresql-persistence
- **Fecha**: 2026-10-18 (UTC-05:00)
- **Tipo**: integración real contra PostgreSQL 16 (contenedor) del adaptador de dialecto.
- **Resultado**: `TEST_PASSED`
- **Comandos**:
  ```bash
  # 1) Suite con PostgreSQL local (contenedor efímero en :55432)
  SIREP_TEST_POSTGRES_URL=postgresql://sirep:sirep@127.0.0.1:55432/sirep \
    python3 -m pytest -o addopts=""            # 122 passed, 2 skipped
  # 2) Suite Postgres desde dentro de la imagen backend contra el servicio `db` de Compose
  docker compose --profile postgres up -d db
  docker compose run --rm -T \
    -e SIREP_DATABASE_URL=postgresql://sirep:sirep@db:5432/sirep \
    -e SIREP_TEST_POSTGRES_URL=postgresql://sirep:sirep@db:5432/sirep \
    backend python -m pytest tests/test_postgres_persistence.py -q
  ```
- **Evidencia (real)**:
  - Local: `122 passed, 0 failed, 0 errors, 2 skipped`
    (`docs/test-runs/20261018-192347`).
  - Dentro del contenedor contra `db`: `4 passed` (`tests/test_postgres_persistence.py`).
  - Casos cubiertos: inicialización de esquema, flujo vertical completo
    (registro→proyecto→artefacto→análisis→hallazgos/grafo→cambio
    aprobar/aplicar/validar), rate limiter en BD (`ON CONFLICT ... RETURNING`) y
    reclamo de trabajo del worker (`UPDATE ... RETURNING`).
- **Failed**: 0
- **Not run**: 0
- **Notas**:
  - La **misma** capa de repositorio (SQL escrito para SQLite) se ejecuta sobre
    PostgreSQL mediante `app/db/pg.py` (traducción `?`→`%s`, `:name`→`%(name)s`,
    `INSERT OR IGNORE`→`ON CONFLICT DO NOTHING`, filas tipo diccionario).
  - SQLite sigue siendo el valor por defecto; PostgreSQL se activa con
    `SIREP_DATABASE_URL`. Requiere `psycopg[binary]` (añadido a `requirements.txt`).
  - La suite SQLite por defecto permanece intacta: `118 passed, 6 skipped`.
  - Credenciales de ejemplo no productivas (`sirep/sirep`), usadas solo en pruebas.
