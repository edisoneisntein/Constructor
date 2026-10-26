"""Adaptadores de validación y reglas de estado (§ Implementation Validator).

Cada *check* es una comprobación concreta y reproducible. Los adaptadores solo
ejecutan **comandos permitidos** (compilación de Python y ``pytest``) contra un
*workspace* controlado; nunca ejecutan scripts arbitrarios del repositorio.
Toda salida se registra como evidencia (comando, código de salida, duración,
salida recortada y limitaciones).
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from app.core.sandbox import build_preexec

CHECK_TYPES = {
    "file_exists",
    "symbol_present",
    "no_marker",
    "pytest",
    "compileall",
    "secret_scan",
}

PASS = "PASS"
FAIL = "FAIL"
ERROR = "ERROR"
SKIPPED = "SKIPPED"
BLOCKED = "BLOCKED"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_PARTIAL = "PARTIAL"
STATUS_BLOCKED = "BLOCKED"
STATUS_NOT_RUN = "NOT_RUN"

DEFAULT_MARKERS = ["TODO", "FIXME", "NotImplementedError", "XXX", "HACK"]

_SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password)\s*[:=]\s*['\"][^'\"${\s]{12,}['\"]"),
]

_PYTEST_COUNTS = re.compile(r"(\d+) (passed|failed|error|errors|skipped)")
_MAX_OUTPUT = 4000


@dataclass
class CheckResult:
    check_id: str
    check_type: str
    criterion: str
    target: str | None
    status: str
    passed: bool
    exit_code: int | None = None
    duration_ms: int = 0
    command: str | None = None
    output: str | None = None
    limitations: list[str] = field(default_factory=list)


@dataclass
class RequirementResult:
    requirement_id: str
    status: str
    checks_total: int
    checks_passed: int
    checks_failed: int
    checks_skipped: int
    criteria_met: list[dict]
    results: list[CheckResult]
    limitations: list[str]


def _clip(text: str | None) -> str | None:
    """Recorta la salida conservando cabeza y cola.

    El resumen de pytest (``N passed``) se emite al final de la salida, por lo
    que un recorte que solo conserve el inicio lo perdería.
    """
    if not text:
        return None
    if len(text) <= _MAX_OUTPUT:
        return text
    head = _MAX_OUTPUT // 2
    tail = _MAX_OUTPUT - head
    omitted = len(text) - _MAX_OUTPUT
    return (
        text[:head]
        + f"\n... ({omitted} caracteres omitidos) ...\n"
        + text[-tail:]
    )


def _within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve(workspace: Path, target: str | None) -> Path | None:
    if not target:
        return None
    candidate = (workspace / target).resolve()
    if not _within(workspace, candidate):
        return None
    return candidate


def compute_code_hash(workspace: Path) -> str:
    """Hash del código relevante (app/**, tests/**, requirements.txt)."""
    digest = hashlib.sha256()
    roots = [workspace / "app", workspace / "tests"]
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(sorted(p for p in root.rglob("*.py") if p.is_file()))
    req = workspace / "requirements.txt"
    if req.is_file():
        files.append(req)
    for path in files:
        digest.update(path.relative_to(workspace).as_posix().encode())
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()


def run_check(check: dict, workspace: Path, settings=None) -> CheckResult:
    check_type = check.get("type")
    check_id = check.get("id", "?")
    criterion = check.get("criterion", "")
    target = check.get("target")
    params = check.get("params") or {}
    if check_type not in CHECK_TYPES:
        return CheckResult(
            check_id, str(check_type), criterion, target, ERROR, False,
            limitations=[f"Tipo de comprobación desconocido: {check_type}"],
        )
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()
    try:
        if check_type in {"file_exists", "symbol_present", "no_marker", "secret_scan"}:
            return _run_static(check_id, check_type, criterion, target, params, workspace)
        if check_type == "compileall":
            return _run_compileall(check_id, criterion, target, params, workspace, settings)
        blocked = _profile_blocks_execution(settings)
        if blocked is not None:
            return CheckResult(
                check_id, "pytest", criterion, target, BLOCKED, False,
                limitations=[blocked],
            )
        return _run_pytest(check_id, criterion, params, workspace, settings)
    except Exception as exc:  # noqa: BLE001 - error de infraestructura, no de la prueba
        return CheckResult(
            check_id, check_type, criterion, target, ERROR, False,
            limitations=[f"Error de infraestructura al ejecutar la comprobación: {exc}"],
        )


def _run_static(check_id, check_type, criterion, target, params, workspace) -> CheckResult:
    path = _resolve(workspace, target)
    if path is None or not path.exists():
        return CheckResult(
            check_id, check_type, criterion, target, FAIL, False, output=None,
            limitations=[f"No existe la ruta esperada: {target}"],
        )
    if check_type == "file_exists":
        minimum = int(params.get("min_bytes", 1))
        size = path.stat().st_size if path.is_file() else 0
        passed = path.is_file() and size >= minimum
        return CheckResult(
            check_id, check_type, criterion, target, PASS if passed else FAIL, passed,
            output=f"{size} bytes",
            limitations=[] if passed else [f"Archivo vacío o incompleto ({size} bytes)."],
        )
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    if check_type == "symbol_present":
        pattern = params.get("pattern", "")
        found = re.search(pattern, text) is not None if pattern else False
        return CheckResult(
            check_id, check_type, criterion, target or pattern, PASS if found else FAIL, found,
            output=f"patrón: {pattern}",
            limitations=[] if found else [f"No se encontró el símbolo requerido: {pattern}"],
        )
    if check_type == "no_marker":
        markers = params.get("markers", DEFAULT_MARKERS)
        hits = [marker for marker in markers if marker in text]
        passed = not hits
        return CheckResult(
            check_id, check_type, criterion, target, PASS if passed else FAIL, passed,
            output="sin marcadores" if passed else f"marcadores: {', '.join(hits)}",
            limitations=[] if passed else [f"Implementación incompleta: {', '.join(hits)}"],
        )
    # secret_scan
    hits = [pattern.pattern for pattern in _SECRET_PATTERNS if pattern.search(text)]
    passed = not hits
    return CheckResult(
        check_id, check_type, criterion, target, PASS if passed else FAIL, passed,
        output="sin secretos detectados" if passed else f"{len(hits)} patrón(es) sensible(s)",
        limitations=[] if passed else ["Posible secreto embebido en el código."],
    )


def _run_compileall(check_id, criterion, target, params, workspace, settings=None) -> CheckResult:
    path = _resolve(workspace, target) or workspace
    command = [sys.executable, "-m", "compileall", "-q", str(path.relative_to(workspace))]
    return _execute(command, workspace, check_id, "compileall", criterion, target, params, settings)


def _run_pytest(check_id, criterion, params, workspace, settings=None) -> CheckResult:
    node_ids = list(params.get("node_ids") or [])
    if not node_ids:
        return CheckResult(
            check_id, "pytest", criterion, None, ERROR, False,
            limitations=["La comprobación 'pytest' requiere 'node_ids'."],
        )
    # ``-o addopts=`` neutraliza los ``addopts`` del proyecto (p. ej. ``-q`` en
    # pytest.ini). Sin esto, ``-q -q`` sube la verbosidad a ``-2`` y pytest 9
    # omite la línea de resumen, que es la fuente primaria del parser.
    # El informe JUnit XML aporta los contadores de forma estructurada y estable.
    report_dir = Path(tempfile.mkdtemp(prefix="sirep_junit_"))
    report_path = report_dir / "report.xml"
    command = [
        sys.executable, "-m", "pytest", *node_ids,
        "-o", "addopts=",
        "-p", "no:cacheprovider",
        "--junitxml", str(report_path),
    ]
    result = _execute(
        command, workspace, check_id, "pytest", criterion, ", ".join(node_ids), params,
        settings, junit_path=report_path,
    )
    shutil.rmtree(report_dir, ignore_errors=True)
    return result


def _read_junit_counts(report_path: Path) -> dict[str, int] | None:
    """Lee los contadores del informe JUnit XML generado por pytest.

    Devuelve ``None`` si el informe no existe o no es parseable, de modo que el
    llamador pueda recurrir al parser textual.
    """
    try:
        if not report_path.is_file():
            return None
        root = ET.parse(report_path).getroot()
    except (ET.ParseError, OSError):
        return None

    # pytest puede emitir <testsuites> o <testsuite> en la raíz.
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "total": 0}
    # Atributos JUnit -> contadores internos.
    attribute_map = {
        "tests": "total",
        "failures": "failed",
        "errors": "errors",
        "skipped": "skipped",
    }
    for suite in suites:
        for attribute, counter in attribute_map.items():
            try:
                counts[counter] += int(suite.get(attribute, 0) or 0)
            except (TypeError, ValueError):
                continue
    counts["passed"] = max(
        counts["total"] - counts["failed"] - counts["errors"] - counts["skipped"], 0
    )
    return counts


def _profile_blocks_execution(settings) -> str | None:
    """Motivo por el que el perfil vigente prohíbe ejecutar el código del proyecto.

    Devuelve ``None`` cuando el perfil permite ejecutar código del proyecto.
    """
    from app.core.execution_profiles import active_profile, profile_executes_project_code

    if profile_executes_project_code(settings):
        return None
    return (
        f"El perfil de ejecución activo '{active_profile(settings).value}' no permite "
        "ejecutar el código del proyecto (§14.1). La comprobación queda bloqueada; "
        "no se reporta como aprobada ni como fallida."
    )


def _execute(
    command,
    workspace,
    check_id,
    check_type,
    criterion,
    target,
    params,
    settings=None,
    junit_path=None,
    junit_counts: dict[str, int] | None = None,
) -> CheckResult:
    timeout = float(params.get("timeout", 0) or 0)
    if timeout <= 0:
        timeout = float(getattr(settings, "validation_timeout_seconds", 180) or 180)
    cpu_seconds = int(getattr(settings, "validation_cpu_seconds", 0) or 0)
    preexec = build_preexec(cpu_seconds=cpu_seconds or int(timeout), max_file_bytes=0, max_memory_mb=0)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=preexec,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(workspace)},
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            check_id, check_type, criterion, target, ERROR, False,
            duration_ms=int((time.monotonic() - started) * 1000),
            command=" ".join(command),
            limitations=[f"La comprobación excedió el tiempo límite ({timeout}s)."],
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    output = _clip((completed.stdout or "") + (completed.stderr or ""))

    if check_type == "compileall":
        passed = completed.returncode == 0
        return CheckResult(
            check_id, check_type, criterion, target, PASS if passed else FAIL, passed,
            exit_code=completed.returncode, duration_ms=duration_ms,
            command=" ".join(command), output=output,
            limitations=[] if passed else ["Errores de compilación estática."],
        )

    counts = junit_counts if junit_counts is not None else (
        _read_junit_counts(junit_path) if junit_path else None
    )
    result = _interpret_pytest(
        check_id, criterion, target, completed.returncode, output, duration_ms, command,
        junit_counts=counts,
    )
    if junit_path is not None:
        if counts is None:
            result.limitations.append(
                "No se pudo leer el informe JUnit; se interpretó la salida de texto."
            )
        else:
            result.limitations.append(
                "Contadores JUnit: "
                f"{counts['passed']} passed, {counts['failed']} failed, "
                f"{counts['errors']} errors, {counts['skipped']} skipped."
            )
    return result


def _interpret_pytest(
    check_id, criterion, target, returncode, output, duration_ms, command, junit_counts=None
) -> CheckResult:
    """Interpreta el resultado de una ejecución de pytest.

    La fuente de verdad primaria es el **código de salida** de pytest:

    * ``0`` → todas las pruebas recogidas pasaron (pueden haber omisiones).
    * ``1`` → hubo fallos o errores de prueba.
    * ``2`` → ejecución interrumpida.
    * ``3`` → error interno de pytest.
    * ``4`` → error de uso (línea de comandos inválida).
    * ``5`` → no se recogió ninguna prueba.
    * ``>=128`` → el proceso terminó por una señal.

    Los contadores (JUnit XML si está disponible; si no, el texto de la salida)
    solo refinan el veredicto: permiten distinguir ``PASS`` de ``SKIPPED`` y
    cuantificar los fallos. Nunca se deduce el estado únicamente del texto.
    """
    counts = junit_counts if junit_counts else _parse_pytest_text(output)
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0)
    errored = counts.get("errors", 0)
    skipped = counts.get("skipped", 0)
    total = counts.get("total", 0) or (passed + failed + errored + skipped)

    base = dict(
        check_id=check_id, check_type="pytest", criterion=criterion, target=target,
        exit_code=returncode, duration_ms=duration_ms, command=" ".join(command), output=output,
    )

    if returncode == 5:
        return CheckResult(
            status=ERROR, passed=False,
            limitations=["No se recogieron pruebas para comprobar el requisito."], **base,
        )
    if returncode == 4:
        return CheckResult(
            status=ERROR, passed=False,
            limitations=["Error de uso en la invocación de pytest (código 4)."], **base,
        )
    if returncode == 3:
        return CheckResult(
            status=ERROR, passed=False,
            limitations=["Error interno de pytest (código 3)."], **base,
        )
    if returncode == 2:
        return CheckResult(
            status=ERROR, passed=False,
            limitations=["La ejecución de pytest fue interrumpida (código 2)."], **base,
        )
    if returncode is not None and returncode >= 128:
        return CheckResult(
            status=ERROR, passed=False,
            limitations=[f"pytest terminó por una señal (código {returncode})."], **base,
        )
    if returncode != 0:
        return CheckResult(
            status=FAIL, passed=False,
            limitations=[f"Pruebas fallidas: {failed}, errores: {errored}."], **base,
        )

    # Código de salida 0: todas las pruebas recogidas pasaron.
    if total == 0:
        return CheckResult(
            status=ERROR, passed=False,
            limitations=[
                "pytest terminó correctamente pero no se recogieron pruebas "
                "para comprobar el requisito."
            ],
            **base,
        )
    if failed or errored:
        return CheckResult(
            status=FAIL, passed=False,
            limitations=[f"Pruebas fallidas: {failed}, errores: {errored}."], **base,
        )
    if passed == 0:
        return CheckResult(
            status=SKIPPED, passed=False,
            limitations=[f"Todas las pruebas se omitieron ({skipped})."], **base,
        )
    limitations = [f"{skipped} prueba(s) omitida(s) por el entorno (no cuentan como éxito)."] if skipped else []
    return CheckResult(status=PASS, passed=True, limitations=limitations, **base)


def _parse_pytest_text(output: str | None) -> dict[str, int]:
    """Extrae los contadores del resumen textual de pytest.

    Solo se usa como respaldo cuando no hay informe JUnit disponible.
    """
    counts = {kind: int(number) for number, kind in _PYTEST_COUNTS.findall(output or "")}
    if not counts:
        return {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "total": 0}
    failed = counts.get("failed", 0)
    errored = counts.get("error", 0) + counts.get("errors", 0)
    skipped = counts.get("skipped", 0)
    passed = counts.get("passed", 0)
    return {
        "passed": passed,
        "failed": failed,
        "errors": errored,
        "skipped": skipped,
        "total": passed + failed + errored + skipped,
    }


def evaluate_requirement(requirement: dict, workspace: Path, settings=None) -> RequirementResult:
    checks = requirement.get("checks") or []
    results: list[CheckResult] = [run_check(check, workspace, settings) for check in checks]

    total = len(results)
    n_pass = sum(1 for r in results if r.status == PASS)
    n_fail = sum(1 for r in results if r.status == FAIL)
    n_skip = sum(1 for r in results if r.status == SKIPPED)
    n_error = sum(1 for r in results if r.status == ERROR)
    n_blocked = sum(1 for r in results if r.status == BLOCKED)
    required = [r for r, c in zip(results, checks) if c.get("required", True)]
    optional = [r for r, c in zip(results, checks) if not c.get("required", True)]
    required_fail = any(r.status == FAIL for r in required)
    required_skip = any(r.status == SKIPPED for r in required)
    required_blocked = any(r.status == BLOCKED for r in required)
    optional_fail = any(r.status == FAIL for r in optional)

    if total == 0:
        status = STATUS_NOT_RUN
    elif required_fail:
        status = STATUS_FAIL
    elif required_blocked or n_error:
        status = STATUS_BLOCKED
    elif required_skip:
        status = STATUS_BLOCKED
    elif optional_fail:
        status = STATUS_PARTIAL
    elif n_pass == total:
        status = STATUS_PASS
    else:
        status = STATUS_PARTIAL

    criteria_met = [
        {"criterion": r.criterion or r.check_id, "check_id": r.check_id, "met": r.passed}
        for r in results
    ]
    limitations: list[str] = []
    for r in results:
        limitations.extend(f"[{r.check_id}] {note}" for note in r.limitations)

    return RequirementResult(
        requirement_id=requirement["id"],
        status=status,
        checks_total=total,
        checks_passed=n_pass,
        checks_failed=n_fail,
        checks_skipped=n_skip,
        criteria_met=criteria_met,
        results=results,
        limitations=limitations,
    )


def normalize_relative(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/"))
