"""Clasificación de archivos ZIP y contenedores Java/Android (§6.1/§6.2).

Un `.jar` y un `.apk` son archivos ZIP; se inspecciona el índice central para
distinguir JAR (clases `.class`), APK (`classes.dex`/`AndroidManifest.xml`) y ZIP
genérico, y se listan sus miembros y bibliotecas nativas.

W8.4: se inspecciona de forma **acotada** el contenido interno (`.class`, `.dex`,
`.so`) leyendo como mucho ``inner_limit_bytes`` por miembro y un número máximo de
miembros, sin extraer a disco ni descomprimir recursivamente (§14.3).
"""

from __future__ import annotations

import io
import zipfile

from app.engines.binary_analysis.formats import detect_format
from app.engines.binary_analysis.models import BinaryFacts, Section

_MAX_MEMBERS = 500
_DEFAULT_INNER_LIMIT = 4 * 1024 * 1024
_DEFAULT_MAX_INNER = 64
_INNER_SUFFIXES = (".class", ".dex", ".so")
_NESTED_SUFFIXES = (".zip", ".jar", ".war", ".apk", ".aar")


def parse_zip(
    data: bytes,
    facts: BinaryFacts,
    *,
    inner_limit_bytes: int = _DEFAULT_INNER_LIMIT,
    max_inner: int = _DEFAULT_MAX_INNER,
) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        facts.limitations.append("ZIP ilegible; solo se ofrecen hashes y cadenas.")
        return

    with archive:
        members = archive.infolist()
        names = [info.filename for info in members]
        has_dex = any(name.endswith(".dex") for name in names)
        has_class = any(name.endswith(".class") for name in names)
        has_manifest = any(name.upper().endswith("META-INF/MANIFEST.MF") for name in names)
        has_android = "AndroidManifest.xml" in names or has_dex

        if has_android:
            facts.format = "APK"
            facts.file_type = "ANDROID_PACKAGE"
            facts.architecture = "Dalvik/ART"
            facts.runtime_indicators.append("Android")
        elif has_class or has_manifest:
            facts.format = "JAR"
            facts.file_type = "JAVA_ARCHIVE"
            facts.architecture = "JVM (bytecode)"
            facts.runtime_indicators.append("Java")
        else:
            facts.format = "ZIP"
            facts.file_type = "ZIP_ARCHIVE"

        for info in members[:200]:
            facts.sections.append(
                Section(name=info.filename, size=info.file_size, offset=info.header_offset)
            )
            if info.filename.endswith(".so"):
                facts.linked_libraries.append(info.filename.split("/")[-1])
        if any(name.startswith("lib/") and name.endswith(".so") for name in names):
            facts.runtime_indicators.append("Native libraries (JNI)")
        if len(members) > _MAX_MEMBERS:
            facts.limitations.append(
                f"Archivo con {len(members)} miembros; se listan los primeros {_MAX_MEMBERS}."
            )

        _inspect_embedded(archive, members, facts, inner_limit_bytes, max_inner)
        facts.limitations.append(
            "El contenido interno se inspecciona de forma acotada y no recursiva; "
            "no equivale a la extracción completa (§6.2/§14.3)."
        )


def _inspect_embedded(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    facts: BinaryFacts,
    inner_limit_bytes: int,
    max_inner: int,
) -> None:
    inspected = 0
    for info in members:
        if info.is_dir() or inspected >= max_inner:
            break
        lower = info.filename.lower()
        if lower.endswith(_NESTED_SUFFIXES):
            facts.embedded.append(
                {"name": info.filename, "format": "ARCHIVE", "size": info.file_size}
            )
            inspected += 1
            continue
        if not lower.endswith(_INNER_SUFFIXES) or info.file_size == 0:
            continue

        try:
            with archive.open(info) as handle:
                raw = handle.read(inner_limit_bytes + 1)
        except (zipfile.BadZipFile, OSError, RuntimeError, EOFError):
            continue
        if len(raw) > inner_limit_bytes:
            facts.embedded.append(
                {
                    "name": info.filename,
                    "format": "TRUNCATED",
                    "size": info.file_size,
                    "limit": inner_limit_bytes,
                }
            )
            inspected += 1
            continue

        entry = _describe_member(info.filename, raw)
        facts.embedded.append(entry)
        inspected += 1


def _describe_member(name: str, raw: bytes) -> dict:
    fmt = detect_format(raw)
    entry: dict = {"name": name, "format": fmt, "size": len(raw)}
    if fmt == "JAVA_CLASS" and len(raw) >= 8:
        entry["major"] = int.from_bytes(raw[6:8], "big")
    elif fmt == "ELF" and len(raw) >= 20:
        entry["machine"] = int.from_bytes(raw[18:20], "little")
    elif fmt == "DEX" and len(raw) >= 7:
        entry["version"] = raw[4:7].decode("ascii", "replace")
    return entry
