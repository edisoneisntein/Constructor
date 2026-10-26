"""Adaptador Mach-O: cabecera, arch, dependencias, símbolos y DWARF (§6.2)."""

from __future__ import annotations

import struct

from app.engines.binary_analysis.formats import MACH_CPUTYPES, MACH_FILETYPES
from app.engines.binary_analysis.models import BinaryFacts, Section

LC_SEGMENT = 0x1
LC_SYMTAB = 0x2
LC_LOAD_DYLIB = 0xC
LC_ID_DYLIB = 0xD
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_SEGMENT_64 = 0x19

_MAGICS = {
    b"\xce\xfa\xed\xfe": ("<", 32),
    b"\xcf\xfa\xed\xfe": ("<", 64),
    b"\xfe\xed\xfa\xce": (">", 32),
    b"\xfe\xed\xfa\xcf": (">", 64),
}
_FAT_MAGICS = {b"\xca\xfe\xba\xbe": ">", b"\xbe\xba\xfe\xca": "<"}

_MAX_SYMBOLS = 2000
_MAX_CMDS = 4096


def parse_macho(data: bytes, facts: BinaryFacts) -> None:
    if data[:4] in _FAT_MAGICS:
        _parse_fat(data, facts)
        return
    _parse_thin(data, facts)


def _cstring(data: bytes, offset: int, limit: int = 512) -> str:
    if offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\x00", offset, min(offset + limit, len(data)))
    if end == -1:
        end = min(offset + limit, len(data))
    return data[offset:end].decode("latin-1", "replace")


def _parse_fat(data: bytes, facts: BinaryFacts) -> None:
    endian = _FAT_MAGICS[data[:4]]
    facts.format = "MACHO_FAT"
    count = struct.unpack_from(endian + "I", data, 4)[0] if len(data) >= 8 else 0
    archs: list[str] = []
    first_slice: tuple[int, int] | None = None
    for index in range(min(count, 64)):
        base = 8 + index * 20
        if base + 20 > len(data):
            break
        cputype, _sub, offset, size, _align = struct.unpack_from(endian + "IIIII", data, base)
        archs.append(MACH_CPUTYPES.get(cputype, f"cputype:{cputype:#x}"))
        if first_slice is None:
            first_slice = (offset, size)
    if archs:
        facts.architecture = ", ".join(dict.fromkeys(archs))
        facts.runtime_indicators.append("binario universal (fat)")
    if first_slice and first_slice[0] + first_slice[1] <= len(data):
        slice_data = data[first_slice[0] : first_slice[0] + first_slice[1]]
        _parse_thin(slice_data, facts, preserve_format=True)


def _parse_thin(data: bytes, facts: BinaryFacts, *, preserve_format: bool = False) -> None:
    magic = data[:4]
    if magic not in _MAGICS:
        facts.limitations.append("Cabecera Mach-O no reconocida.")
        return
    endian, bits = _MAGICS[magic]
    if not preserve_format:
        facts.format = "MACHO"
    facts.bits = bits
    facts.endianness = "little" if endian == "<" else "big"

    header_size = 32 if bits == 64 else 28
    if len(data) < header_size:
        facts.limitations.append("Cabecera Mach-O truncada.")
        return
    cputype, cpusubtype, filetype, ncmds, _sizeofcmds, _flags = struct.unpack_from(
        endian + "IIIIII", data, 4
    )
    facts.architecture = facts.architecture or MACH_CPUTYPES.get(cputype, f"cputype:{cputype:#x}")
    facts.file_type = MACH_FILETYPES.get(filetype, str(filetype))

    offset = header_size
    dependencies: list[str] = []
    exported: list[str] = []
    imported: list[str] = []
    for _ in range(min(ncmds, _MAX_CMDS)):
        if offset + 8 > len(data):
            break
        cmd, cmdsize = struct.unpack_from(endian + "II", data, offset)
        if cmdsize < 8 or offset + cmdsize > len(data):
            break
        if cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_ID_DYLIB):
            name_offset = struct.unpack_from(endian + "I", data, offset + 8)[0]
            name = _cstring(data, offset + name_offset)
            if name and cmd != LC_ID_DYLIB and name not in dependencies:
                dependencies.append(name)
        elif cmd == LC_SYMTAB and cmdsize >= 24:
            symoff, nsyms, stroff, strsize = struct.unpack_from(endian + "IIII", data, offset + 8)
            string_table = data[stroff : stroff + strsize]
            nlist_size = 16 if bits == 64 else 12
            for index in range(min(nsyms, _MAX_SYMBOLS)):
                base = symoff + index * nlist_size
                if base + 4 > len(data):
                    break
                n_strx = struct.unpack_from(endian + "I", data, base)[0]
                if n_strx == 0 or n_strx >= len(string_table):
                    continue
                end = string_table.find(b"\x00", n_strx)
                name = string_table[n_strx : end if end != -1 else len(string_table)].decode("latin-1", "replace")
                if not name:
                    continue
                if name.startswith("_") and name not in exported:
                    exported.append(name[1:] if len(name) > 1 else name)
                elif name.startswith(("dyld_", "imp_")) and name not in imported:
                    imported.append(name)
        elif cmd in (LC_SEGMENT, LC_SEGMENT_64):
            _parse_segment(data, facts, offset, cmd, endian, bits)

        offset += cmdsize

    facts.linked_libraries = dependencies[:200]
    facts.exported_symbols = exported[:500]
    facts.imported_symbols = imported[:500]


def _parse_segment(data: bytes, facts: BinaryFacts, cmd_offset: int, cmd: int, endian: str, bits: int) -> None:
    if bits == 64:
        segname = _cstring(data, cmd_offset + 8, 16)
        nsects = struct.unpack_from(endian + "I", data, cmd_offset + 64)[0] if cmd_offset + 68 <= len(data) else 0
        section_offset = cmd_offset + 72
        section_size = 80
    else:
        segname = _cstring(data, cmd_offset + 8, 16)
        nsects = struct.unpack_from(endian + "I", data, cmd_offset + 48)[0] if cmd_offset + 52 <= len(data) else 0
        section_offset = cmd_offset + 56
        section_size = 68
    for index in range(min(nsects, 256)):
        base = section_offset + index * section_size
        if base + section_size > len(data):
            break
        sectname = _cstring(data, base, 16) or f"section{index}"
        if bits == 64:
            size = struct.unpack_from(endian + "Q", data, base + 40)[0]
            file_offset = struct.unpack_from(endian + "I", data, base + 48)[0]
        else:
            size = struct.unpack_from(endian + "I", data, base + 36)[0]
            file_offset = struct.unpack_from(endian + "I", data, base + 40)[0]
        full_name = f"{segname},{sectname}" if segname else sectname
        facts.sections.append(Section(name=full_name, size=size, offset=file_offset))
        if sectname.startswith("__debug") or sectname.startswith("__zdebug") or "DWARF" in sectname:
            facts.debug_info_present = True
