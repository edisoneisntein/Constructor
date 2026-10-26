"""Pruebas del RepairEngine (§9)."""

from __future__ import annotations

import pytest

from app.engines.repair_engine.repair import classify_repair, apply_repair
from app.engines.repair_engine.patterns import COMMON_PYTHON_PATTERNS


def test_classify_repair_no_patterns():
    """Code sin patrones detectados debe tener confianza 0."""
    code = "x = 1\ny = 2\n"
    result = classify_repair(code)
    assert result.confidence == 0.0
    assert not result.repair_suggested
    assert len(result.patterns_detected) == 0


def test_classify_repair_eval_exec():
    """Code con eval/exec debe detectarse."""
    code = "result = eval('x + 1')\n"
    result = classify_repair(code)
    assert result.confidence > 0.0
    assert result.repair_suggested
    nombres = [p.name for p in result.patterns_detected]
    assert any("EvalExec" in n for n in nombres)


def test_classify_repair_bare_except():
    """Code con bare except debe detectarse."""
    code = "try:\n    x = 1\n    return x\nexcept:\n    pass\n"
    result = classify_repair(code)
    assert result.confidence > 0.0
    assert result.repair_suggested
    nombres = [p.name for p in result.patterns_detected]
    assert any("BareExcept" in n for n in nombres)


def test_classify_repair_open_without_context():
    """Code con open sin contexto debe detectarse."""
    code = "f = open('file.txt')\ncontenido = f.read()\n"
    result = classify_repair(code)
    assert result.confidence > 0.0
    assert result.repair_suggested
    nombres = [p.name for p in result.patterns_detected]
    assert any("OpenWithoutContext" in n for n in nombres)


def test_apply_repair_bare_except():
    """Aplicar reparación de bare except."""
    code = "try:\n    x = 1\n    return x\nexcept:\n    pass\n"
    result = apply_repair(code)
    assert result.success
    assert "except Exception as e" in result.repaired_code
    print(f"BareExcept repair: {result.explanation}")


def test_apply_repair_open_with_context():
    """Aplicar reparación de open sin contexto."""
    code = "f = open('file.txt')\ncontenido = f.read()\n"
    result = apply_repair(code)
    assert result.success
    assert "with open" in result.repaired_code
    print(f"OpenWithoutContext repair: {result.explanation}")


def test_full_repair_workflow():
    """Workflow completo: clasificar -> reparar -> verificar."""
    # Test 1: bare except
    code = "try:\n    x = 1\n    return x\nexcept:\n    pass\n"
    classified = classify_repair(code)
    assert classified.repair_suggested

    result = apply_repair(code)
    assert result.success

    # Test 2: open without context
    code2 = "f = open('file.txt')\ncontenido = f.read()\n"
    classified2 = classify_repair(code2)
    assert classified2.repair_suggested

    result2 = apply_repair(code2)
    assert result2.success

    # Test 3: eval/exec
    code3 = "result = eval('x + 1')\n"
    classified3 = classify_repair(code3)
    assert classified3.repair_suggested

    result3 = apply_repair(code3)
    assert result3.success