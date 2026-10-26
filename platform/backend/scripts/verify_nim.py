"""Verificación reproducible de la integración NVIDIA NIM (§12/§13).

Uso:
    cd platform/backend
    python -m scripts.verify_nim

Requiere SIREP_NIM_API_KEY (o un `.env` local). No imprime la clave.
"""

from __future__ import annotations

import json
import sys

from app.core.config import get_settings
from app.services.migration_service import verify_nim_connection


def main() -> int:
    report = verify_nim_connection(get_settings())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = (
        report["configured"]
        and report["reachable"]
        and report["model_available"]
        and report["completion_ok"]
    )
    print("RESULT:", "TEST_PASSED" if ok else "TEST_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
