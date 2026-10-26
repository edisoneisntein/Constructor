"""Adaptador PE: cabecera, secciones, importaciones, exportaciones y .NET (§6.2)."""

from __future__ import annotations

import struct

from app.engines.binary_analysis.formats import PE_MACHINES
from app.engines.binary_analysis.models import BinaryFacts, Section

_MAX_IMPORTS = 2000
_MAX_EXPORTS = 2000
_MAX_SECTIONS = 96


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0] if offset + 2 <= len(data) else 0


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0] if offset + 4 <= len(data) else 0


def _cstring(data: bytes, offset: int, limit: int = 512) -> str:
    if offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\x00", offset, min(offset + limit, len(data)))
    if end == -1:
        end = min(offset + limit, len(data))
    return data[offset:end].decode("latin-1", "replace")


def parse_pe(data: bytes, facts: BinaryFacts) -> None:
    if len(data) < 0x40:
        facts.limitations.append("Cabecera DOS/PE truncada.")
        return
    pe_offset = _u32(data, 0x3C)
    if pe_offset + 24 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        facts.limitations.append("Firma PE no encontrada.")
        return

    coff = pe_offset + 4
    machine = _u16(data, coff)
    num_sections = _u16(data, coff + 2)
    size_optional = _u16(data, coff + 16)
    optional = coff + 20
    magic = _u16(data, optional)
    facts.bits = 32 if magic == 0x10B else 64 if magic == 0x20B else None
    facts.architecture = PE_MACHINES.get(machine, f"machine:{machine:#x}")
    facts.file_type = "DLL" if _u16(data, coff + 18) & 0x2000 else "EXE"
    facts.entry_point = _u32(data, optional + 16)

    if facts.bits == 64:
        num_dirs_off, dirs_off = optional + 108, optional + 112
    else:
        num_dirs_off, dirs_off = optional + 92, optional + 96
    num_dirs = _u32(data, num_dirs_off)

    def directory(index: int) -> tuple[int, int]:
        if index >= num_dirs:
            return 0, 0
        base = dirs_off + index * 8
        return _u32(data, base), _u32(data, base + 4)

    section_table = optional + size_optional
    sections: list[dict] = []
    for index in range(min(num_sections, _MAX_SECTIONS)):
        base = section_table + index * 40
        if base + 40 > len(data):
            break
        name = data[base : base + 8].rstrip(b"\x00").decode("latin-1", "replace") or f"sec{index}"
        virtual_size = _u32(data, base + 8)
        virtual_address = _u32(data, base + 12)
        raw_size = _u32(data, base + 16)
        raw_pointer = _u32(data, base + 20)
        sections.append(
            {"name": name, "vsize": virtual_size, "vaddr": virtual_address, "raw": raw_pointer, "raw_size": raw_size}
        )
        facts.sections.append(Section(name=name, size=raw_size or virtual_size, offset=raw_pointer))

    def rva_to_offset(rva: int) -> int:
        for section in sections:
            span = max(section["vsize"], section["raw_size"])
            if section["vaddr"] <= rva < section["vaddr"] + span:
                return section["raw"] + (rva - section["vaddr"])
        return rva if rva < len(data) else -1

    exported: list[str] = []
    export_rva, _ = directory(0)
    if export_rva:
        base = rva_to_offset(export_rva)
        if base >= 0:
            number_of_names = _u32(data, base + 24)
            address_of_names = _u32(data, base + 32)
            names_base = rva_to_offset(address_of_names)
            if names_base >= 0:
                for index in range(min(number_of_names, _MAX_EXPORTS)):
                    name_rva = _u32(data, names_base + index * 4)
                    name = _cstring(data, rva_to_offset(name_rva))
                    if name and name not in exported:
                        exported.append(name)

    imported: list[str] = []
    libraries: list[str] = []
    import_rva, _ = directory(1)
    descriptor = rva_to_offset(import_rva) if import_rva else -1
    if descriptor >= 0:
        thunk_size = 8 if facts.bits == 64 else 4
        ordinal_flag = 1 << (63 if facts.bits == 64 else 31)
        for _ in range(512):
            if descriptor + 20 > len(data):
                break
            original_first_thunk = _u32(data, descriptor)
            name_rva = _u32(data, descriptor + 12)
            first_thunk = _u32(data, descriptor + 16)
            if not (original_first_thunk or name_rva or first_thunk):
                break
            dll = _cstring(data, rva_to_offset(name_rva))
            if dll and dll not in libraries:
                libraries.append(dll)
            thunk_rva = original_first_thunk or first_thunk
            thunk_offset = rva_to_offset(thunk_rva)
            if thunk_offset >= 0:
                for index in range(1024):
                    offset = thunk_offset + index * thunk_size
                    if offset + thunk_size > len(data):
                        break
                    value = int.from_bytes(data[offset : offset + thunk_size], "little")
                    if value == 0:
                        break
                    if value & ordinal_flag:
                        imported.append(f"{dll}#ordinal{value & 0xFFFF}")
                        continue
                    name_offset = rva_to_offset(value)
                    name = _cstring(data, name_offset + 2) if name_offset >= 0 else ""
                    if name:
                        imported.append(name)
            descriptor += 20

    facts.imported_symbols = imported[:500]
    facts.exported_symbols = exported[:500]
    facts.linked_libraries = libraries[:200]

    debug_rva, _ = directory(6)
    facts.debug_info_present = bool(debug_rva)
    clr_rva, _ = directory(14)
    if clr_rva:
        facts.runtime_indicators.append(".NET (CLI)")
