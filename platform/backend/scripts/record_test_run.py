#!/usr/bin/env python3
"""Registra una ejecución real de pruebas (§19.6).

Ejecuta la suite con ``pytest``, captura la salida, y escribe un registro
verificable en ``docs/test-runs/`` (JSON + Markdown) y actualiza el índice.
No inventa resultados: si la suite falla, el registro lo refleja.

Uso:
    python3 scripts/record_test_run.py [--label "Fase 11"] [-- <args pytest>...]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = BACKEND_ROOT.parent / "docs" / "test-runs"

_SYSTEM_MAP = {"Darwin": "Darwin", "Linux": "Linux", "Windows": "Windows"}


def _run_git(args: list[str]) -> str | None:
    if shutil.which("git") is None:
        return None
    try:
        out = subprocess.run(
            ["git", *args], cwd=BACKEND_ROOT.parent, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = out.stdout.strip()
    return value or None


def _parse_counts(report_path: Path) -> dict[str, int]:
    """Extrae los conteos del reporte JUnit XML real de pytest."""
    if not report_path.exists():
        return {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    suite = ET.parse(report_path).getroot()
    if suite.tag == "testsuites":
        child = suite.find("testsuite")
        if child is not None:
            suite = child
    total = int(suite.get("tests", 0))
    failed = int(suite.get("failures", 0))
    errors = int(suite.get("errors", 0))
    skipped = int(suite.get("skipped", 0))
    return {"passed": total - failed - errors - skipped, "failed": failed, "errors": errors, "skipped": skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description="Registra una ejecución de pruebas (§19.6).")
    parser.add_argument("--label", default="", help="Etiqueta de la ejecución (p. ej. fase).")
    parser.add_argument("pytest_args", nargs="*", help="Argumentos adicionales para pytest.")
    args = parser.parse_args()

    report_fd, report_name = tempfile.mkstemp(suffix="-junit.xml")
    os.close(report_fd)
    report_path = Path(report_name)
    command = [sys.executable, "-m", "pytest", "-q", "--junitxml", str(report_path), *args.pytest_args]
    started = datetime.now(timezone.utc)
    start = time.time()
    completed = subprocess.run(command, cwd=BACKEND_ROOT, capture_output=True, text=True, check=False)
    duration = round(time.time() - start, 3)

    output = (completed.stdout or "") + (completed.stderr or "")
    counts = _parse_counts(report_path)
    report_path.unlink(missing_ok=True)
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0)
    errors = counts.get("errors", 0)
    skipped = counts.get("skipped", 0)
    success = completed.returncode == 0 and failed == 0 and errors == 0

    try:
        import pytest

        pytest_version = pytest.__version__
    except Exception:  # pragma: no cover
        pytest_version = "unknown"

    record = {
        "timestamp_utc": started.isoformat(),
        "label": args.label,
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "success": success,
        "duration_seconds": duration,
        "counts": {"passed": passed, "failed": failed, "errors": errors, "skipped": skipped},
        "environment": {
            "python_version": platform.python_version(),
            "pytest_version": pytest_version,
            "platform": _SYSTEM_MAP.get(platform.system(), platform.system()),
            "machine": platform.machine(),
        },
        "vcs": {
            "commit": _run_git(["rev-parse", "HEAD"]),
            "branch": _run_git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "dirty": bool(_run_git(["status", "--porcelain"])),
        },
        "output_tail": output.strip().splitlines()[-40:],
    }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    json_path = DOCS_DIR / f"{stamp}.json"
    md_path = DOCS_DIR / f"{stamp}.md"
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = "TEST_PASSED" if success else "TEST_FAILED"
    md_lines = [
        f"# Ejecución de pruebas {stamp}",
        "",
        f"- Estado: **{status}**",
        f"- Etiqueta: {args.label or '(sin etiqueta)'}",
        f"- Comando: `{record['command']}`",
        f"- Resultado: {passed} passed · {failed} failed · {errors} errors · {skipped} skipped",
        f"- Duración: {duration}s · Código de salida: {completed.returncode}",
        f"- Python {record['environment']['python_version']} · pytest {pytest_version} · {record['environment']['platform']}",
        f"- Commit: {record['vcs']['commit'] or 'n/d'} (rama {record['vcs']['branch'] or 'n/d'}, dirty={record['vcs']['dirty']})",
        "",
        "## Cola de salida",
        "",
        "```",
        *record["output_tail"],
        "```",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    index_path = DOCS_DIR / "INDEX.md"
    header = "# Índice de ejecuciones de pruebas (§19.6)\n\n| Fecha (UTC) | Estado | Etiqueta | Resultado | Registro |\n|---|---|---|---|---|\n"
    existing = ""
    if index_path.exists():
        lines = index_path.read_text(encoding="utf-8").splitlines()
        existing = "\n".join(line for line in lines if line.startswith("|") and "---" not in line and "Fecha" not in line)
    row = (
        f"| {record['timestamp_utc'][:19]}Z | {status} | {args.label or '—'} | "
        f"{passed}p/{failed}f/{errors}e/{skipped}s | [{stamp}.json]({stamp}.json) |"
    )
    index_path.write_text(
        header + (existing + "\n" if existing else "") + row + "\n", encoding="utf-8"
    )

    print(f"{status}: {passed} passed, {failed} failed, {errors} errors, {skipped} skipped")
    print(f"Registro: {json_path}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
