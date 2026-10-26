"""Extracción de dependencias declaradas (§5.2 Dependencias).

Parsea manifiestos reales: ``package.json`` (npm), ``requirements.txt`` (PyPI) y
``pyproject.toml`` (PyPI, PEP 621 y Poetry). Los valores se registran tal como se
declaran; no se inventan versiones.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_REQUIREMENT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9_.\-]+)\s*(?P<extras>\[[^\]]+\])?\s*(?P<spec>[<>=!~;].*)?$"
)


@dataclass
class DependencyDecl:
    ecosystem: str
    name: str
    version: str | None
    source_file: str


def parse_package_json(path: Path, relative: str) -> list[DependencyDecl]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return []
    results: list[DependencyDecl] = []
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = payload.get(section)
        if isinstance(block, dict):
            for name, version in block.items():
                results.append(
                    DependencyDecl(
                        ecosystem="npm",
                        name=str(name),
                        version=str(version) if version is not None else None,
                        source_file=relative,
                    )
                )
    return results


def parse_requirements_txt(path: Path, relative: str) -> list[DependencyDecl]:
    results: list[DependencyDecl] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        line = line.split("#", 1)[0].strip()
        match = _REQUIREMENT_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        if not name:
            continue
        spec = (match.group("spec") or "").strip() or None
        results.append(DependencyDecl(ecosystem="pypi", name=name, version=spec, source_file=relative))
    return results


def parse_pyproject_toml(path: Path, relative: str) -> list[DependencyDecl]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    results: list[DependencyDecl] = []
    project = data.get("project", {})
    for raw in project.get("dependencies", []) or []:
        match = _REQUIREMENT_RE.match(str(raw))
        if match and match.group("name"):
            results.append(
                DependencyDecl("pypi", match.group("name"), (match.group("spec") or "").strip() or None, relative)
            )
    poetry = data.get("tool", {}).get("poetry", {})
    for name, spec in (poetry.get("dependencies") or {}).items():
        if name.lower() == "python":
            continue
        version = spec if isinstance(spec, str) else (spec.get("version") if isinstance(spec, dict) else None)
        results.append(DependencyDecl("pypi", str(name), str(version) if version else None, relative))
    return results


def parse_manifest(path: Path, relative: str) -> list[DependencyDecl]:
    name = path.name
    if name == "package.json":
        return parse_package_json(path, relative)
    if name == "requirements.txt":
        return parse_requirements_txt(path, relative)
    if name == "pyproject.toml":
        return parse_pyproject_toml(path, relative)
    return []
