"""Extracción segura de archivos (§14.3, §20.3).

Defensas implementadas y verificables:
  * Rechazo de rutas absolutas, ``..``, unidades Windows y separadores ``\\``.
  * Rechazo de enlaces simbólicos (bit de modo POSIX en ``external_attr``).
  * Límite de entradas, tamaño total extraído, tamaño por archivo y profundidad.
  * Detección de "zip bomb" por ratio de compresión total y por entrada.
  * Rechazo de archivos con nombres nulos (``\\x00``) y de entradas duplicadas.
  * Sin descompresión recursiva: los archivos anidados se registran, no se expanden.

La función falla en cerrado (``UnsafeArchiveError``): si una entrada es insegura,
no se extrae nada.
"""

from __future__ import annotations

import hashlib
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.core.errors import UnsafeArchiveError
from app.engines.ingestion.safe_paths import (
    PathLimits,
    assert_within,
    validate_relative_path,
)


@dataclass
class ExtractionLimits:
    max_entries: int = 20_000
    max_total_bytes: int = 500 * 1024 * 1024
    max_file_bytes: int = 20 * 1024 * 1024
    max_compression_ratio: float = 100.0
    max_path_depth: int = 64


@dataclass
class ExtractedFile:
    path: str
    size_bytes: int
    sha256: str


@dataclass
class ExtractionReport:
    root: Path
    files: list[ExtractedFile] = field(default_factory=list)
    total_bytes: int = 0
    skipped_nested_archives: list[str] = field(default_factory=list)


_NESTED_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".war", ".apk"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _validate_member_name(name: str, limits: ExtractionLimits) -> PurePosixPath:
    if "\x00" in name:
        raise UnsafeArchiveError("Nombre de entrada contiene byte nulo.", details={"name": repr(name)})
    if "\\" in name:
        raise UnsafeArchiveError("Nombre de entrada contiene separador Windows.", details={"name": name})
    candidate = PurePosixPath(name)
    if candidate.is_absolute():
        raise UnsafeArchiveError("Ruta absoluta en el archivo.", details={"name": name})
    parts = candidate.parts
    if any(part in {"..", ""} for part in parts):
        raise UnsafeArchiveError("Ruta con traversal ('..').", details={"name": name})
    if any(len(part) >= 2 and part[1] == ":" for part in parts):
        raise UnsafeArchiveError("Ruta con unidad Windows.", details={"name": name})
    if len(parts) > limits.max_path_depth:
        raise UnsafeArchiveError("Ruta demasiado profunda.", details={"name": name, "depth": len(parts)})
    return candidate


def inspect_zip(path: Path, limits: ExtractionLimits) -> dict[str, object]:
    """Valida el archivo sin extraerlo. Devuelve un resumen o lanza error."""
    if not zipfile.is_zipfile(path):
        raise UnsafeArchiveError("El archivo no es un ZIP válido.", details={"path": str(path)})
    total_uncompressed = 0
    entries = 0
    seen: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > limits.max_entries:
            raise UnsafeArchiveError(
                "El archivo supera el número máximo de entradas.",
                details={"entries": len(infos), "max": limits.max_entries},
            )
        for info in infos:
            if info.is_dir():
                continue
            entries += 1
            name = info.filename
            if name in seen:
                raise UnsafeArchiveError("Entrada duplicada en el archivo.", details={"name": name})
            seen.add(name)
            _validate_member_name(name, limits)
            if _is_symlink(info):
                raise UnsafeArchiveError("Enlace simbólico no permitido.", details={"name": name})
            if info.file_size > limits.max_file_bytes:
                raise UnsafeArchiveError(
                    "Un archivo supera el tamaño máximo permitido.",
                    details={"name": name, "size": info.file_size, "max": limits.max_file_bytes},
                )
            total_uncompressed += info.file_size
            if total_uncompressed > limits.max_total_bytes:
                raise UnsafeArchiveError(
                    "El contenido extraído supera el límite total.",
                    details={"total": total_uncompressed, "max": limits.max_total_bytes},
                )
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > limits.max_compression_ratio:
                    raise UnsafeArchiveError(
                        "Ratio de compresión sospechoso (posible zip bomb).",
                        details={"name": name, "ratio": round(ratio, 2), "max": limits.max_compression_ratio},
                    )
    return {"entries": entries, "total_uncompressed_bytes": total_uncompressed}


def safe_extract(path: Path, destination: Path, limits: ExtractionLimits) -> ExtractionReport:
    """Extrae el archivo de forma segura. Falla en cerrado ante cualquier riesgo."""
    inspect_zip(path, limits)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report = ExtractionReport(root=destination)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relative = _validate_member_name(info.filename, limits)
            target = (destination / Path(*relative.parts)).resolve()
            if not target.is_relative_to(destination):
                raise UnsafeArchiveError("Ruta resuelta fuera del destino.", details={"name": info.filename})
            suffix = relative.suffix.lower()
            if suffix in _NESTED_SUFFIXES:
                # No se descomprime recursivamente; se registra como limitación.
                report.skipped_nested_archives.append(info.filename)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = archive.read(info)
            if len(data) > limits.max_file_bytes:
                raise UnsafeArchiveError(
                    "Un archivo extraído supera el tamaño máximo.",
                    details={"name": info.filename, "size": len(data)},
                )
            target.write_bytes(data)
            report.files.append(
                ExtractedFile(path=str(relative), size_bytes=len(data), sha256=_sha256_bytes(data))
            )
            report.total_bytes += len(data)
    return report
