"""Pruebas del Implementation Validator (§ validación de requisitos).

El validador debe ser reproducible y honesto: distingue una prueba que pasa de
una omitida, detecta archivos ausentes y marcadores de implementación incompleta,
y no aprueba un requisito cuyas pruebas no se hayan ejecutado.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.engines.validation import registry as registry_module
from app.engines.validation.engine import (
    STATUS_BLOCKED,
    STATUS_FAIL,
    STATUS_PASS,
    evaluate_requirement,
    run_check,
)
from tests.conftest import auth_headers, register


def _workspace(tmp_path):
    root = tmp_path / "ws"
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "app" / "mod.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (root / "tests" / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n\n\ndef test_bad():\n    assert False\n", encoding="utf-8"
    )
    (root / "tests" / "test_skip.py").write_text(
        "import pytest\n\n\n@pytest.mark.skip(reason='no')\ndef test_skip():\n    assert True\n",
        encoding="utf-8",
    )
    return root


def test_registry_is_valid_and_complete():
    requirements = registry_module.load_requirements()
    assert len(requirements) >= 10
    ids = {r["id"] for r in requirements}
    assert {"REQ-001", "REQ-004", "REQ-006", "REQ-012"} <= ids
    for requirement in requirements:
        assert requirement["acceptance_criteria"]
        for check in requirement["checks"]:
            assert check["type"] in {
                "file_exists",
                "symbol_present",
                "no_marker",
                "pytest",
                "compileall",
                "secret_scan",
            }


def test_engine_pytest_pass(tmp_path):
    workspace = _workspace(tmp_path)
    result = run_check(
        {"id": "C", "type": "pytest", "criterion": "ok", "params": {"node_ids": ["tests/test_sample.py::test_ok"]}},
        workspace,
    )
    assert result.status == "PASS" and result.passed is True
    assert result.exit_code == 0


def test_engine_pytest_fail(tmp_path):
    workspace = _workspace(tmp_path)
    result = run_check(
        {"id": "C", "type": "pytest", "criterion": "bad", "params": {"node_ids": ["tests/test_sample.py::test_bad"]}},
        workspace,
    )
    assert result.status == "FAIL" and result.passed is False
    assert result.exit_code != 0
    assert "1" in (result.output or "")


def test_engine_skipped_is_not_pass(tmp_path):
    workspace = _workspace(tmp_path)
    result = run_check(
        {"id": "C", "type": "pytest", "criterion": "skip", "params": {"node_ids": ["tests/test_skip.py"]}},
        workspace,
    )
    assert result.status == "SKIPPED"
    assert result.passed is False
    requirement = {
        "id": "REQ-X",
        "checks": [{"id": "REQ-X-A", "type": "pytest", "criterion": "skip", "required": True,
                    "params": {"node_ids": ["tests/test_skip.py"]}}],
    }
    outcome = evaluate_requirement(requirement, workspace)
    assert outcome.status == STATUS_BLOCKED


def test_engine_missing_file_fails(tmp_path):
    workspace = _workspace(tmp_path)
    check = {"id": "C", "type": "file_exists", "target": "app/does_not_exist.py", "criterion": "x", "required": True}
    result = run_check(check, workspace)
    assert result.status == "FAIL"
    requirement = {"id": "REQ-Y", "checks": [check]}
    assert evaluate_requirement(requirement, workspace).status == STATUS_FAIL


def test_engine_marker_and_secret_detection(tmp_path):
    workspace = _workspace(tmp_path)
    (workspace / "app" / "incomplete.py").write_text("def todo():\n    pass  # TODO: implementar\n", encoding="utf-8")
    (workspace / "app" / "leaky.py").write_text('API_KEY = "nvapi-abcdefghijklmnopqrstuvwxyz"\n', encoding="utf-8")

    marker = run_check({"id": "M", "type": "no_marker", "target": "app/incomplete.py", "criterion": "x"}, workspace)
    assert marker.status == "FAIL"
    secret = run_check({"id": "S", "type": "secret_scan", "target": "app/leaky.py", "criterion": "x"}, workspace)
    assert secret.status == "FAIL"

    requirement = {"id": "REQ-Z", "checks": [
        {"id": "REQ-Z-A", "type": "no_marker", "target": "app/incomplete.py", "required": True, "criterion": "x"},
    ]}
    assert evaluate_requirement(requirement, workspace).status == STATUS_FAIL


def test_service_run_persists_evidence(client: TestClient, tmp_path):
    from app.db.session import get_database
    from app.services import validation_service

    workspace = _workspace(tmp_path)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "id": "REQ-TEST-1",
                        "title": "Prueba de validación",
                        "description": "Un requisito con una comprobación real.",
                        "acceptance_criteria": ["El archivo existe", "La prueba pasa"],
                        "checks": [
                            {"id": "REQ-TEST-1-A", "type": "file_exists", "target": "app/mod.py",
                             "criterion": "El archivo existe", "required": True, "params": {"min_bytes": 1}},
                            {"id": "REQ-TEST-1-B", "type": "pytest", "criterion": "La prueba pasa",
                             "required": True, "params": {"node_ids": ["tests/test_sample.py::test_ok"]}},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    database = get_database()
    conn = database.connect()
    try:
        from app.core.config import get_settings

        run = validation_service.run_validation(
            conn, settings=get_settings(), user_id="u1", workspace=workspace, registry_path=registry_path
        )
    finally:
        if not database.is_ephemeral:
            conn.close()

    assert run["status"] == "COMPLETED"
    assert len(run["code_hash"]) == 64
    assert len(run["results"]) == 1
    result = run["results"][0]
    assert result["status"] == STATUS_PASS
    assert result["checks_total"] == 2 and result["checks_passed"] == 2
    assert len(result["evidence"]) == 2


def test_validation_endpoints(client: TestClient):
    session = register(client, "validator@example.com", "Acme")
    headers = auth_headers(session["token"])

    requirements = client.get("/api/v1/validation/requirements", headers=headers)
    assert requirements.status_code == 200, requirements.text
    ids = {item["id"] for item in requirements.json()}
    assert "REQ-012" in ids

    report = client.get("/api/v1/validation/report", headers=headers)
    assert report.status_code == 200
    assert report.json()["total"] == len(requirements.json())
    assert report.json()["verified"] == 0  # todavía sin ejecutar

    run = client.post(
        "/api/v1/validation/run", json={"requirement_ids": ["REQ-012"]}, headers=headers
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "COMPLETED"
    assert len(body["results"]) == 1
    assert body["results"][0]["requirement_id"] == "REQ-012"
    assert body["results"][0]["status"] == STATUS_PASS
    assert body["results"][0]["evidence"]

    report_after = client.get("/api/v1/validation/report", headers=headers).json()
    assert report_after["verified"] == 1


def test_validation_requires_role(client: TestClient):
    session = register(client, "owner2@example.com", "Acme")
    headers = auth_headers(session["token"])
    # El propietario puede leer; se verifica que un requisito inexistente da 404.
    missing = client.get("/api/v1/validation/requirements/REQ-DOES-NOT-EXIST", headers=headers)
    assert missing.status_code == 404


def test_validation_run_unknown_requirement(client: TestClient):
    session = register(client, "owner3@example.com", "Acme")
    headers = auth_headers(session["token"])
    response = client.post(
        "/api/v1/validation/run", json={"requirement_ids": ["REQ-NOPE"]}, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- Parser de pytest: el código de salida es la fuente de verdad ------------


def _interpret(returncode, output="", junit=None):
    from app.engines.validation.engine import _interpret_pytest

    return _interpret_pytest(
        "C", "criterion", "tests/test_x.py", returncode, output, 10,
        ["pytest", "tests/test_x.py"], junit_counts=junit,
    )


def test_interpret_pytest_success_uses_exit_code():
    """Un resumen no reconocible no invalida un código de salida 0."""
    result = _interpret(0, "salida sin resumen reconocible\n", {"passed": 3, "failed": 0, "errors": 0, "skipped": 0, "total": 3})
    assert result.status == "PASS" and result.passed is True
    assert result.exit_code == 0


def test_interpret_pytest_success_from_text_when_no_junit():
    result = _interpret(0, "3 passed in 0.12s\n")
    assert result.status == "PASS" and result.passed is True


def test_interpret_pytest_failure():
    result = _interpret(1, "1 failed in 0.10s\n", {"passed": 0, "failed": 1, "errors": 0, "skipped": 0, "total": 1})
    assert result.status == "FAIL" and result.passed is False


def test_interpret_pytest_no_tests_collected_is_error():
    """pytest devuelve 5 cuando no recoge pruebas: no es un aprobado."""
    result = _interpret(5, "no tests ran\n")
    assert result.status == "ERROR" and result.passed is False
    assert any("No se recogieron pruebas" in note for note in result.limitations)


def test_interpret_pytest_unrecognized_output_without_counts_is_error():
    """Salida no reconocida con código 0 no puede declararse PASS."""
    result = _interpret(0, "??? unexpected output ???\n")
    assert result.status == "ERROR" and result.passed is False


def test_interpret_pytest_skipped_only_is_not_pass():
    result = _interpret(0, "1 skipped in 0.05s\n", {"passed": 0, "failed": 0, "errors": 0, "skipped": 1, "total": 1})
    assert result.status == "SKIPPED" and result.passed is False


def test_interpret_pytest_exit_code_2_3_4_are_errors():
    for code in (2, 3, 4):
        result = _interpret(code, "algo salió mal\n")
        assert result.status == "ERROR", code
        assert result.passed is False


def test_interpret_pytest_signal_exit_code_is_error():
    result = _interpret(137, "terminated\n")
    assert result.status == "ERROR" and result.passed is False


def test_run_pytest_ignores_project_addopts(tmp_path):
    """El runner debe anular los ``addopts`` del proyecto (p. ej. ``-q``).

    Con ``-q -q`` (verbosidad ``-2``) pytest 9 omite la línea de resumen; el
    parser no debe depender de ella.
    """
    workspace = tmp_path / "ws"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "pytest.ini").write_text("[pytest]\naddopts = -q\n", encoding="utf-8")
    (workspace / "tests" / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    from app.engines.validation.engine import _run_pytest

    result = _run_pytest("C", "ok", {"node_ids": ["tests/test_x.py::test_ok"]}, workspace)
    assert result.status == "PASS", result.limitations
    assert result.exit_code == 0


def test_run_pytest_missing_node_is_not_pass(tmp_path):
    """Un nodo inexistente no puede reportarse como aprobado."""
    workspace = tmp_path / "ws"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "test_x.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    from app.engines.validation.engine import _run_pytest

    result = _run_pytest("C", "ok", {"node_ids": ["tests/test_x.py::test_no_existe"]}, workspace)
    assert result.status != "PASS"
    assert result.passed is False
