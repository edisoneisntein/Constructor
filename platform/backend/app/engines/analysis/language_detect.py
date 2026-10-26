"""Detección de lenguaje por extensión (§5.1).

Reconocer una extensión no equivale a soportar el lenguaje completo: solo se
analizan con AST los lenguajes soportados explícitamente.
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_LANGUAGES = {"python", "typescript", "javascript"}

_EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
}

# Reconocidos (no analizados con AST en el MVP): se reportan como limitación.
_KNOWN_UNSUPPORTED = {
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
}

MANIFEST_NAMES = {
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "package-lock.json",
    "poetry.lock",
    "Pipfile",
    "setup.py",
    "setup.cfg",
}

IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "vendor",
    "bower_components",
}


def language_for_path(path: Path) -> str | None:
    return _EXTENSION_MAP.get(path.suffix.lower())


def known_unsupported_language(path: Path) -> str | None:
    return _KNOWN_UNSUPPORTED.get(path.suffix.lower())


def is_manifest(path: Path) -> bool:
    return path.name in MANIFEST_NAMES


def should_skip_dir(name: str) -> bool:
    return name in IGNORED_DIRECTORIES or name.startswith(".")
