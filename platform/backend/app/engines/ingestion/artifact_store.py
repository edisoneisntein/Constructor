"""Almacenamiento de artefactos y detección de tipo (§4.5, §14.3).

El tipo MIME se detecta por contenido (magic bytes), no solo por extensión.
Tipo MIME y extensión se validan de forma independiente.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

# Firmas de contenido relevantes para el MVP (validación independiente de la extensión).
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"PK\x03\x04", "application/zip"),
    (b"PK\x05\x06", "application/zip"),
    (b"PK\x07\x08", "application/zip"),
    (b"\x7fELF", "application/x-elf"),
    (b"MZ", "application/vnd.microsoft.portable-executable"),
    (b"\xcf\xfa\xed\xfe", "application/x-mach-binary"),
    (b"\xce\xfa\xed\xfe", "application/x-mach-binary"),
    (b"\xfe\xed\xfa\xce", "application/x-mach-binary"),
    (b"\xfe\xed\xfa\xcf", "application/x-mach-binary"),
    (b"\x1f\x8b", "application/gzip"),
]

_TEXT_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".cfg", ".ini", ".env",
    ".html", ".css", ".sql", ".sh", ".go", ".rs", ".java", ".cs", ".rb", ".php",
}


@dataclass
class StoredArtifact:
    storage_path: str
    sha256: str
    size_bytes: int
    detected_mime: str
    declared_mime: str | None
    kind: str
    filename: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sniff_mime(data: bytes, filename: str) -> str:
    """Detecta el tipo por contenido; cae a texto plano por extensión conocida."""
    head = data[:8]
    for signature, mime in _MAGIC_SIGNATURES:
        if head.startswith(signature):
            return mime
    suffix = Path(filename).suffix.lower()
    if suffix in _TEXT_EXTENSIONS:
        return "text/plain"
    # Si no hay bytes nulos en el inicio, es probable que sea texto.
    if b"\x00" not in data[:1024]:
        return "text/plain"
    return "application/octet-stream"


def classify_kind(detected_mime: str, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if detected_mime == "application/zip":
        # Un ZIP de código fuente se ingesta como SOURCE_ZIP.
        return "SOURCE_ZIP"
    if detected_mime.startswith("application/x-elf") or "mach-binary" in detected_mime or "portable-executable" in detected_mime:
        return "BINARY"
    if detected_mime == "text/plain":
        return "SOURCE_DIRECTORY" if suffix == "" else "SOURCE_DIRECTORY"
    return "BINARY"


def store_artifact(
    storage_root: Path,
    *,
    organization_id: str,
    filename: str,
    data: bytes,
    declared_mime: str | None = None,
) -> StoredArtifact:
    """Persiste el contenido en almacenamiento dedicado con dirección por hash.

    Estructura: ``artifacts/{org}/{sha[:2]}/{sha}/{nombre_saneado}``.
    """
    digest = sha256_bytes(data)
    safe_name = os.path.basename(filename.replace("\\", "/")) or "artifact.bin"
    safe_name = safe_name.replace("\x00", "")
    detected_mime = sniff_mime(data, safe_name)
    kind = classify_kind(detected_mime, safe_name)
    directory = storage_root / "artifacts" / organization_id / digest[:2] / digest
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / safe_name
    target.write_bytes(data)
    return StoredArtifact(
        storage_path=str(target),
        sha256=digest,
        size_bytes=len(data),
        detected_mime=detected_mime,
        declared_mime=declared_mime,
        kind=kind,
        filename=safe_name,
    )
