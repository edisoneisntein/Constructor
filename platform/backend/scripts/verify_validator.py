"""Verificación reproducible del Implementation Validator (§4.3/§5).

Uso:
    cd platform/backend
    python -m scripts.verify_validator

Imprime un informe JSON con la conformidad de los requisitos verificados.

Perfil de ejecución
--------------------
El perfil se obtiene de ``get_settings()`` (no de ``Settings()``): solo el
cargador consolidado lee las variables de entorno, por lo que ``Settings()``
siempre devolvería el valor por defecto ``STATIC_ANALYSIS``.

Para que los *checks* de tipo ``pytest`` puedan ejecutarse (y no queden
``BLOCKED``) hay que habilitar el perfil de ejecución de pruebas:

    SIREP_EXECUTION_PROFILE=ISOLATED_TEST_EXECUTION python -m scripts.verify_validator

o bien de forma explícita:

    python -m scripts.verify_validator --profile ISOLATED_TEST_EXECUTION

Sin ese perfil el validador no ejecuta el código del proyecto (§14.1) y los
requisitos con pruebas se reportan como ``BLOCKED`` (nunca como aprobados).
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from app.core.config import get_settings, reset_settings_cache
from app.core.ids import utcnow_iso
from app.db.database import Database
from app.services import validation_service


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica la conformidad de los requisitos del Implementation Validator."
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Perfil de ejecución a usar (p. ej. ISOLATED_TEST_EXECUTION). "
            "Si se omite, se toma de SIREP_EXECUTION_PROFILE."
        ),
    )
    parser.add_argument(
        "--registry-path",
        default=None,
        help="Ruta alternativa del registro de requisitos (JSON).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.profile:
        os.environ["SIREP_EXECUTION_PROFILE"] = args.profile
        reset_settings_cache()

    tmp_dir = Path(tempfile.mkdtemp(prefix="sirep_validate_"))
    db_path = tmp_dir / "sirep.sqlite3"
    storage_root = tmp_dir / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    db = Database(str(db_path))
    db.initialize(utcnow_iso())
    conn = db.connect()

    try:
        validation_service.sync_registry(conn)

        # ``get_settings()`` es el único cargador que aplica las variables de
        # entorno (SIREP_EXECUTION_PROFILE, SIREP_STORAGE_ROOT, ...).
        settings = get_settings()

        report = validation_service.run_validation(
            conn,
            settings=settings,
            user_id="verify_validator",
            registry_path=args.registry_path,
        )

        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())