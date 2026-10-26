"""Utilidades del análisis de binarios: hashes, entropía, cadenas (§6.2)."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

_PRINTABLE = set(range(0x20, 0x7F))
_RELEVANT_HINTS = (
    "http://",
    "https://",
    "://",
    ".dll",
    ".so",
    ".dylib",
    "UPX",
    "Electron",
    "Node.js",
    "Python",
    "go1.",
    "GO build",
    "rustc",
    "MSVC",
    "GCC:",
    "clang",
    ".NET",
    "mscoree",
    "vcruntime",
    "openssl",
    "libc",
)


@dataclass
class StringLimits:
    min_length: int = 5
    max_strings: int = 200
    max_length: int = 512


def hash_bytes(data: bytes) -> tuple[str, str, str]:
    return (
        hashlib.sha256(data).hexdigest(),
        hashlib.sha1(data).hexdigest(),
        hashlib.md5(data).hexdigest(),
    )


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    total = len(data)
    result = 0.0
    for count in counts:
        if count:
            probability = count / total
            result -= probability * math.log2(probability)
    return round(result, 4)


def extract_strings(data: bytes, limits: StringLimits) -> tuple[list[str], list[str]]:
    """Extrae cadenas ASCII y UTF-16LE; separa un subconjunto relevante.

    Las cadenas son **evidencia contextual** (§6.2), no prueba de funcionalidad.

    El recorrido es de un solo paso y con memoria acotada: se conservan solo las
    ``max_strings`` primeras cadenas únicas y, dentro de cada corrida, los primeros
    ``max_length`` bytes. El resultado es idéntico al de materializar todas las
    corridas, pero la memoria deja de crecer con el tamaño del binario.
    """
    seen: set[str] = set()
    unique: list[str] = []

    def _append(value: str) -> None:
        if value not in seen:
            seen.add(value)
            unique.append(value)

    ascii_buffer = bytearray()
    ascii_length = 0
    for byte in data:
        if byte in _PRINTABLE:
            ascii_length += 1
            if len(ascii_buffer) < limits.max_length:
                ascii_buffer.append(byte)
            continue
        if ascii_length >= limits.min_length:
            _append(bytes(ascii_buffer).decode("ascii", errors="replace"))
            if len(unique) >= limits.max_strings:
                break
        ascii_buffer.clear()
        ascii_length = 0
    else:
        if ascii_length >= limits.min_length:
            _append(bytes(ascii_buffer).decode("ascii", errors="replace"))

    if len(unique) < limits.max_strings:
        utf16_buffer = bytearray()
        utf16_length = 0
        for index in range(0, len(data) - 1, 2):
            low, high = data[index], data[index + 1]
            if high == 0 and low in _PRINTABLE:
                utf16_length += 1
                if len(utf16_buffer) < limits.max_length:
                    utf16_buffer.append(low)
                continue
            if utf16_length >= limits.min_length:
                _append(bytes(utf16_buffer).decode("ascii", errors="replace"))
                if len(unique) >= limits.max_strings:
                    break
            utf16_buffer.clear()
            utf16_length = 0
        else:
            if utf16_length >= limits.min_length:
                _append(bytes(utf16_buffer).decode("ascii", errors="replace"))

    relevant = [value for value in unique if any(hint in value for hint in _RELEVANT_HINTS)]
    return unique, relevant


_VERSION_PATTERN = re.compile(r"\b\d+\.\d+(?:\.\d+){0,3}\b")


def find_version_signatures(strings: list[str], limit: int = 20) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for value in strings:
        for match in _VERSION_PATTERN.findall(value):
            if match not in seen:
                seen.add(match)
                found.append(match)
            if len(found) >= limit:
                return found
    return found
