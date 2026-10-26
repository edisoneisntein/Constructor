"""Adaptador ELF: cabecera, secciones, símbolos, bibliotecas y depuración (§6.2)."""

from __future__ import annotations

import struct

from app.engines.binary_analysis.formats import ELF_MACHINES, ELF_TYPES
from app.engines.binary_analysis.models import BinaryFacts, Section
from app.engines.binary_analysis.utils import entropy

SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_DYNAMIC = 6
SHT_NOBITS = 8
SHT_DYNSYM = 11
DT_NEEDED = 1

_MAX_SYMBOLS = 2000


def parse_elf(data: bytes, facts: BinaryFacts) -> None:
    if len(data) < 0x34:
        facts.limitations.append("Cabecera ELF truncada.")
        return
    bits = 64 if data[4] == 2 else 32
    endian = "<" if data[5] == 1 else ">"
    facts.bits = bits
    facts.endianness = "little" if endian == "<" else "big"

    end = f"{endian}"
    if bits == 64:
        header = struct.unpack_from(end + "HHIQQQIHHHHHH", data, 16)
    else:
        header = struct.unpack_from(end + "HHIIIIIHHHHHH", data, 16)
    (
        e_type,
        e_machine,
        _e_version,
        e_entry,
        _e_phoff,
        e_shoff,
        _e_flags,
        _e_ehsize,
        _e_phentsize,
        _e_phnum,
        e_shentsize,
        e_shnum,
        e_shstrndx,
    ) = header

    facts.architecture = ELF_MACHINES.get(e_machine, f"machine:{e_machine:#x}")
    facts.file_type = ELF_TYPES.get(e_type)
    facts.entry_point = e_entry

    if e_shoff <= 0 or e_shnum <= 0 or e_shentsize <= 0:
        facts.limitations.append("No hay tabla de secciones ELF disponible.")
        return

    sh_fmt = end + ("IIQQQQIIQQ" if bits == 64 else "IIIIIIIIII")
    sections: list[dict] = []
    for index in range(min(e_shnum, 4096)):
        offset = e_shoff + index * e_shentsize
        if offset + e_shentsize > len(data):
            break
        values = struct.unpack_from(sh_fmt, data, offset)
        sections.append(
            {
                "name_offset": values[0],
                "type": values[1],
                "offset": values[4],
                "size": values[5],
                "link": values[6],
                "entsize": values[9],
            }
        )

    def read_c_string(base: int, relative: int) -> str:
        start = base + relative
        if start < 0 or start >= len(data):
            return ""
        end_index = data.find(b"\x00", start, min(start + 512, len(data)))
        if end_index == -1:
            end_index = min(start + 512, len(data))
        return data[start:end_index].decode("latin-1", "replace")

    shstr_base = sections[e_shstrndx]["offset"] if 0 <= e_shstrndx < len(sections) else 0

    names: list[str] = []
    for index, section in enumerate(sections):
        name = read_c_string(shstr_base, section["name_offset"]) if shstr_base else ""
        name = name or f"sec{index}"
        section["name"] = name
        names.append(name)
        body = b""
        if section["type"] != SHT_NOBITS and section["offset"] < len(data):
            body = data[section["offset"] : section["offset"] + min(section["size"], 1 << 20)]
        facts.sections.append(
            Section(name=name, size=section["size"], offset=section["offset"], entropy=entropy(body))
        )

    if any(name.startswith(".debug") for name in names):
        facts.debug_info_present = True
    if any("go.buildinfo" in name for name in names):
        facts.runtime_indicators.append("Go")

    strtab_cache: dict[int, bytes] = {}

    def strtab(index: int) -> bytes:
        if index not in strtab_cache:
            section = sections[index] if 0 <= index < len(sections) else None
            strtab_cache[index] = (
                data[section["offset"] : section["offset"] + section["size"]] if section else b""
            )
        return strtab_cache[index]

    imported: list[str] = []
    exported: list[str] = []
    for section in sections:
        if section["type"] not in (SHT_SYMTAB, SHT_DYNSYM):
            continue
        table = strtab(section["link"])
        entsize = section["entsize"] or (24 if bits == 64 else 16)
        count = section["size"] // entsize if entsize else 0
        for symbol_index in range(min(count, _MAX_SYMBOLS)):
            offset = section["offset"] + symbol_index * entsize
            if offset + entsize > len(data):
                break
            st_name = struct.unpack_from(end + "I", data, offset)[0]
            if bits == 64:
                st_info = data[offset + 4]
                st_shndx = struct.unpack_from(end + "H", data, offset + 6)[0]
            else:
                st_info = data[offset + 12]
                st_shndx = struct.unpack_from(end + "H", data, offset + 14)[0]
            if st_name == 0 or st_name >= len(table):
                continue
            end_index = table.find(b"\x00", st_name)
            name = table[st_name : end_index if end_index != -1 else len(table)].decode("latin-1", "replace")
            if not name:
                continue
            binding = st_info >> 4
            if st_shndx == 0:
                if name not in imported:
                    imported.append(name)
            elif binding in (1, 2) and name not in exported:  # GLOBAL / WEAK
                exported.append(name)
    facts.imported_symbols = imported[:500]
    facts.exported_symbols = exported[:500]

    dependencies: list[str] = []
    for section in sections:
        if section["type"] != SHT_DYNAMIC:
            continue
        table = strtab(section["link"])
        entry = end + ("QQ" if bits == 64 else "II")
        entsize = section["entsize"] or (16 if bits == 64 else 8)
        count = section["size"] // entsize if entsize else 0
        for entry_index in range(min(count, 4096)):
            offset = section["offset"] + entry_index * entsize
            if offset + entsize > len(data):
                break
            tag, value = struct.unpack_from(entry, data, offset)
            if tag == 0:
                break
            if tag == DT_NEEDED:
                end_index = table.find(b"\x00", value)
                name = table[value : end_index if end_index != -1 else len(table)].decode("latin-1", "replace")
                if name and name not in dependencies:
                    dependencies.append(name)
    facts.linked_libraries = dependencies
