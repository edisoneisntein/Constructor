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
    """
    ascii_strings: list[str] = []
    current: list[str] = []
    for byte in data:
        if byte in _PRINTABLE:
            current.append(chr(byte))
        else:
            if len(current) >= limits.min_length:
                ascii_strings.append("".join(current)[: limits.max_length])
            current = []
    if len(current) >= limits.min_length:
        ascii_strings.append("".join(current)[: limits.max_length])

    utf16: list[str] = []
    current16: list[str] = []
    for index in range(0, len(data) - 1, 2):
        low, high = data[index], data[index + 1]
        if high == 0 and low in _PRINTABLE:
            current16.append(chr(low))
        else:
            if len(current16) >= limits.min_length:
                utf16.append("".join(current16)[: limits.max_length])
            current16 = []
    if len(current16) >= limits.min_length:
        utf16.append("".join(current16)[: limits.max_length])

    seen: set[str] = set()
    unique: list[str] = []
    for value in ascii_strings + utf16:
        if value not in seen:
            seen.add(value)
            unique.append(value)
        if len(unique) >= limits.max_strings:
            break

    relevant = [value for value in unique if any(hint in value for hint in _RELEVANT_HINTS)]
    return unique, relevant


def find_version_signatures(strings: list[str], limit: int = 20) -> list[str]:
    pattern = re.compile(r"\b\d+\.\d+(?:\.\d+){0,3}\b")
    found: list[str] = []
    seen: set[str] = set()
    for value in strings:
        for match in pattern.findall(value):
            if match not in seen:
                seen.add(match)
                found.append(match)
            if len(found) >= limit:
                return found
    return found
