"""Detección de formato y mapas de arquitectura (§6.1/§6.2)."""

from __future__ import annotations

ELF_MACHINES = {
    0x03: "x86",
    0x3E: "x86_64",
    0x28: "ARM",
    0xB7: "AArch64",
    0x08: "MIPS",
    0x14: "PowerPC",
    0x15: "PowerPC64",
    0xF3: "RISC-V",
    0x32: "IA-64",
    0x16: "IBM S/390",
}

PE_MACHINES = {
    0x014C: "i386",
    0x8664: "x86_64",
    0x01C0: "ARM",
    0x01C4: "ARM Thumb-2",
    0xAA64: "ARM64",
    0x0200: "IA-64",
}

MACH_CPUTYPES = {
    7: "x86",
    0x01000007: "x86_64",
    12: "ARM",
    0x0100000C: "ARM64",
    18: "PowerPC",
    0x01000012: "PowerPC64",
}

ELF_TYPES = {1: "REL", 2: "EXEC", 3: "DYN", 4: "CORE"}

# Formatos aceptados para análisis estático (§6.1/§6.2).
SUPPORTED_FORMATS = {
    "ELF",
    "PE",
    "MACHO",
    "MACHO_FAT",
    "JAVA_CLASS",
    "WASM",
    "DEX",
    "PYC",
    "ZIP",
    "COFF",
    "AR",
}

MACH_FILETYPES = {
    1: "OBJECT",
    2: "EXECUTE",
    3: "FVMLIB",
    4: "CORE",
    5: "PRELOAD",
    6: "DYLIB",
    8: "BUNDLE",
    10: "DSYM",
}


def _looks_like_coff(data: bytes) -> bool:
    """Heurística estricta para objetos COFF sin cabecera mágica (§6.1)."""
    if len(data) < 20:
        return False
    machine = int.from_bytes(data[0:2], "little")
    if machine not in PE_MACHINES:
        return False
    num_sections = int.from_bytes(data[2:4], "little")
    opt_size = int.from_bytes(data[16:18], "little")
    if not 1 <= num_sections <= 96 or opt_size > 512:
        return False
    return 20 + opt_size + num_sections * 40 <= len(data)


def detect_format(data: bytes) -> str:
    """Identifica el formato por cabecera mágica (§6.2)."""
    if len(data) < 4:
        return "UNKNOWN"
    if data[:4] == b"\x7fELF":
        return "ELF"
    if data[:2] == b"MZ":
        return "PE"
    if data[:4] == b"\x00asm":
        return "WASM"
    if data[:4] == b"dex\n":
        return "DEX"
    if data[:8] == b"!<arch>\n":
        return "AR"
    if data[:2] == b"PK" and data[2:4] in (b"\x03\x04", b"\x05\x06", b"\x07\x08"):
        return "ZIP"
    if data[2:4] == b"\r\n" and len(data) >= 16:
        return "PYC"
    if _looks_like_coff(data):
        return "COFF"
    magic_be = int.from_bytes(data[:4], "big")
    magic_le = int.from_bytes(data[:4], "little")
    if magic_be in (0xFEEDFACE, 0xFEEDFACF):
        return "MACHO"
    if magic_le in (0xFEEDFACE, 0xFEEDFACF):
        return "MACHO"
    if magic_be in (0xCAFEBABE, 0xCAFEBABF):
        # Desambiguar Java .class (minor/major razonables) de Mach-O fat.
        if len(data) >= 8:
            major = int.from_bytes(data[6:8], "big")
            if 40 <= major <= 80:
                return "JAVA_CLASS"
        return "MACHO_FAT"
    return "UNKNOWN"
