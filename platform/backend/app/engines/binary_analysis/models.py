"""Modelos del motor de análisis de binarios (§6.2).

Toda la información derivada de cadenas y símbolos se marca como evidencia
**contextual** (§6.2), nunca como prueba definitiva de funcionalidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Section:
    name: str
    size: int
    offset: int
    entropy: float | None = None


@dataclass
class BinaryFacts:
    """Hechos estáticos extraídos de un artefacto binario (§6.2)."""

    path: str
    size_bytes: int
    sha256: str
    sha1: str
    md5: str
    format: str = "UNKNOWN"
    architecture: str | None = None
    bits: int | None = None
    endianness: str | None = None
    file_type: str | None = None
    entry_point: int | None = None
    sections: list[Section] = field(default_factory=list)
    imported_symbols: list[str] = field(default_factory=list)
    exported_symbols: list[str] = field(default_factory=list)
    linked_libraries: list[str] = field(default_factory=list)
    debug_info_present: bool = False
    runtime_indicators: list[str] = field(default_factory=list)
    signatures: list[str] = field(default_factory=list)
    strings_sample: list[str] = field(default_factory=list)
    embedded: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "sha1": self.sha1,
            "md5": self.md5,
            "format": self.format,
            "architecture": self.architecture,
            "bits": self.bits,
            "endianness": self.endianness,
            "file_type": self.file_type,
            "entry_point": self.entry_point,
            "sections": [s.__dict__ for s in self.sections],
            "imported_symbols": self.imported_symbols,
            "exported_symbols": self.exported_symbols,
            "linked_libraries": self.linked_libraries,
            "debug_info_present": self.debug_info_present,
            "runtime_indicators": self.runtime_indicators,
            "signatures": self.signatures,
            "strings_sample": self.strings_sample,
            "embedded": self.embedded,
            "limitations": self.limitations,
        }
