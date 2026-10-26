"""Parser del formato DEX de Android (§6.2)."""

from __future__ import annotations

from app.engines.binary_analysis.models import BinaryFacts


def parse_dex(data: bytes, facts: BinaryFacts) -> None:
    facts.format = "DEX"
    facts.file_type = "DALVIK_EXECUTABLE"
    facts.architecture = "Dalvik/ART"
    facts.bits = 32
    facts.runtime_indicators.append("Android")
    facts.runtime_indicators.append("Dalvik/ART")

    if len(data) < 0x70:
        facts.limitations.append("Cabecera DEX incompleta.")
        return

    version = data[4:7].decode("ascii", "replace")
    facts.signatures.append(f"dex version={version}")
    checksum = int.from_bytes(data[8:12], "little")
    facts.signatures.append(f"dex checksum=0x{checksum:08x}")

    counts = {
        "string_ids": int.from_bytes(data[0x38:0x3C], "little"),
        "type_ids": int.from_bytes(data[0x40:0x44], "little"),
        "proto_ids": int.from_bytes(data[0x48:0x4C], "little"),
        "field_ids": int.from_bytes(data[0x50:0x54], "little"),
        "method_ids": int.from_bytes(data[0x58:0x5C], "little"),
        "class_defs": int.from_bytes(data[0x60:0x64], "little"),
    }
    for name, count in counts.items():
        if count:
            facts.signatures.append(f"dex {name}={count}")

    string_ids_size = counts["string_ids"]
    string_ids_off = int.from_bytes(data[0x3C:0x40], "little")
    facts.sections.append(
        _section("string_ids", string_ids_size * 4, string_ids_off)
    )
    for index in range(min(string_ids_size, 64)):
        base = string_ids_off + index * 4
        if base + 4 > len(data):
            break
        offset = int.from_bytes(data[base : base + 4], "little")
        text = _read_uleb_string(data, offset)
        if text:
            facts.strings_sample.append(text)


def _read_uleb_string(data: bytes, offset: int) -> str:
    if offset <= 0 or offset >= len(data):
        return ""
    pos = offset
    while pos < len(data) and data[pos] & 0x80:
        pos += 1
    pos += 1
    end = data.find(b"\x00", pos)
    if end == -1:
        return ""
    return data[pos:end].decode("utf-8", "replace")


def _section(name: str, size: int, offset: int):
    from app.engines.binary_analysis.models import Section

    return Section(name=name, size=size, offset=offset)
