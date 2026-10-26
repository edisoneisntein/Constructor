"""Pruebas del FunctionReconstructionEngine (§8)."""

from __future__ import annotations

import ast
import pytest

from app.engines.function_reconstruction_engine.patterns import classify_function, extract_dependencies, reconstruct_function
from app.engines.function_reconstruction_engine.repair import apply_function_repair, FunctionRepairResult


def test_classify_function_basic():
    """Test basic function classification."""
    code = "def hello(name: str) -> str:\n    return 'Hello, ' + name\n"
    tree = ast.parse(code)
    func_info = classify_function(code, tree)
    
    assert func_info.name == "hello"
    assert "name" in func_info.params
    assert func_info.return_annotation is not None


def test_classify_async_function():
    """Test async function classification."""
    code = "async def fetch_data() -> dict:\n    return {}\n"
    tree = ast.parse(code)
    func_info = classify_function(code, tree)
    
    assert func_info.name == "fetch_data"
    assert func_info.is_async is True


def test_extract_dependencies():
    """Test dependency extraction."""
    code = "def process_data(data: list) -> list:\n    result = []\n    for item in data:\n        result.append(item.upper())\n    return result\n"
    tree = ast.parse(code)
    func_info = classify_function(code, tree)
    deps = extract_dependencies(code, func_info)
    
    assert func_info.name == "process_data"
    assert "data" in deps.reads
    assert "result" in deps.writes
    assert "upper" in deps.calls


def test_reconstruct_function():
    """Test function reconstruction."""
    code = "def calculate_total(items: list[float]) -> float:\n    total = 0.0\n    for item in items:\n        total += item\n    return total\n"
    result = reconstruct_function(code)
    
    assert "function" in result
    assert "dependencies" in result
    assert result["function"]["name"] == "calculate_total"


def test_apply_function_repair_add_annotations():
    """Test adding annotations to a function."""
    code = "def process(items):\n    return items\n"
    result = apply_function_repair(code, repair_type="add_annotations")
    
    assert result.success
    # The repaired code should contain annotations
    assert "Any" in result.repaired_code or "int" in result.repaired_code


def test_apply_function_repair_add_docstring():
    """Test adding docstring to a function."""
    code = "def process(items):\n    return items\n"
    result = apply_function_repair(code, repair_type="add_docstring")
    
    assert result.success
    assert "docstring" in result.explanation.lower() or "Docstring" in result.explanation


def test_full_reconstruction_workflow():
    """Test workflow completo: clasificación -> dependencias -> reparación."""
    code = "def process_data(data: list) -> list:\n    result = []\n    for item in data:\n        result.append(item * 2)\n    return result\n"
    
    # Step 1: Classify
    tree = ast.parse(code)
    func_info = classify_function(code, tree)
    assert func_info.name == "process_data"
    assert len(func_info.params) > 0
    
    # Step 2: Extract dependencies
    deps = extract_dependencies(code, func_info)
    assert func_info.name == "process_data"
    assert "data" in deps.reads
    assert "result" in deps.writes
    
    # Step 3: Reconstruct function
    result = reconstruct_function(code)
    assert result["function"]["name"] == "process_data"
    
    # Step 4: Apply repair
    repair_result = apply_function_repair(code, repair_type="add_annotations")
    assert repair_result.success


def test_function_with_decorators():
    """Test function with decorators."""
    code = "@deprecated\n@cache(ttl=300)\ndef get_cached_data() -> dict:\n    pass\n"
    tree = ast.parse(code)
    func_info = classify_function(code, tree)
    
    assert func_info.name == "get_cached_data"
    assert len(func_info.decorators) >= 1
    assert "deprecated" in func_info.decorators or "cache" in func_info.decorators