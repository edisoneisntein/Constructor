"""Orquestador del análisis estático de binarios (§6.2).

No ejecuta el binario ni promete recuperar código fuente (§6.3/§6.4). Las cadenas
y símbolos son **evidencia contextual**.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.engines.binary_analysis.archive import parse_zip
from app.engines.binary_analysis.coff import parse_ar, parse_coff
from app.engines.binary_analysis.dex import parse_dex
from app.engines.binary_analysis.elf import parse_elf
from app.engines.binary_analysis.formats import detect_format
from app.engines.binary_analysis.macho import parse_macho
from app.engines.binary_analysis.models import BinaryFacts
from app.engines.binary_analysis.pe import parse_pe
from app.engines.binary_analysis.pyc import parse_pyc
from app.engines.binary_analysis.wasm import parse_wasm
from app.engines.binary_analysis.utils import (
    StringLimits,
    extract_strings,
    find_version_signatures,
    hash_bytes,
)

_FRAMEWORK_HINTS = {
    "Electron": "Electron",
    "electron": "Electron",
    "Go build": "Go",
    "go1.": "Go",
    "rustc": "Rust",
    ".NET": ".NET",
    "mscoree": ".NET",
    "Python": "Python",
    "Node.js": "Node.js",
    "UPX": "UPX (posible empaquetado)",
    "Inno Setup": "Inno Setup",
    "Nullsoft": "NSIS",
}


@dataclass
class BinaryLimits:
    max_bytes: int = 64 * 1024 * 1024
    strings: StringLimits = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.strings is None:
            self.strings = StringLimits()


def analyze_binary(path: Path, limits: BinaryLimits | None = None) -> BinaryFacts:
    limits = limits or BinaryLimits()
    size_bytes = path.stat().st_size
    with path.open("rb") as handle:
        data = handle.read(limits.max_bytes)

    sha256, sha1, md5 = hash_bytes(data)
    facts = BinaryFacts(
        path=str(path),
        size_bytes=size_bytes,
        sha256=sha256,
        sha1=sha1,
        md5=md5,
    )
    if size_bytes > len(data):
        facts.limitations.append(
            f"Análisis limitado a los primeros {len(data)} bytes de {size_bytes} (§6.2)."
        )

    fmt = detect_format(data)
    facts.format = fmt
    if fmt == "ELF":
        parse_elf(data, facts)
    elif fmt == "PE":
        parse_pe(data, facts)
    elif fmt in ("MACHO", "MACHO_FAT"):
        parse_macho(data, facts)
    elif fmt == "JAVA_CLASS":
        _parse_java_class(data, facts)
    elif fmt == "WASM":
        parse_wasm(data, facts)
    elif fmt == "DEX":
        parse_dex(data, facts)
    elif fmt == "PYC":
        parse_pyc(data, facts)
    elif fmt == "ZIP":
        parse_zip(data, facts)
    elif fmt == "COFF":
        parse_coff(data, facts)
    elif fmt == "AR":
        parse_ar(data, facts)
    else:
        facts.limitations.append("Formato no reconocido; solo se ofrecen hashes y cadenas.")

    strings, relevant = extract_strings(data, limits.strings)
    facts.strings_sample = relevant[:100] or strings[:20]
    format_signatures = facts.signatures
    version_signatures = find_version_signatures(strings)
    facts.signatures = list(dict.fromkeys(format_signatures + version_signatures))

    indicators = set(facts.runtime_indicators)
    for hint, label in _FRAMEWORK_HINTS.items():
        if any(hint in value for value in strings):
            indicators.add(label)
    facts.runtime_indicators = sorted(indicators)

    facts.limitations.append(
        "Las cadenas y símbolos se ofrecen como evidencia contextual, no como prueba "
        "definitiva de funcionalidad (§6.2)."
    )
    return facts


def _parse_java_class(data: bytes, facts: BinaryFacts) -> None:
    facts.runtime_indicators.append("Java")
    facts.bits = None
    if len(data) >= 8:
        minor = int.from_bytes(data[4:6], "big")
        major = int.from_bytes(data[6:8], "big")
        facts.signatures.append(f"class major={major} minor={minor}")
        facts.file_type = "JAVA_CLASS"
        facts.architecture = "JVM (bytecode)"


def compare_binaries(left: BinaryFacts, right: BinaryFacts) -> dict:
    """Comparación entre artefactos (§6.2)."""
    left_exports = set(left.exported_symbols)
    right_exports = set(right.exported_symbols)
    left_libs = set(left.linked_libraries)
    right_libs = set(right.linked_libraries)
    return {
        "same_format": left.format == right.format,
        "same_architecture": left.architecture == right.architecture,
        "same_digest": left.sha256 == right.sha256,
        "size_delta": right.size_bytes - left.size_bytes,
        "added_exports": sorted(right_exports - left_exports),
        "removed_exports": sorted(left_exports - right_exports),
        "added_libraries": sorted(right_libs - left_libs),
        "removed_libraries": sorted(left_libs - right_libs),
    }
