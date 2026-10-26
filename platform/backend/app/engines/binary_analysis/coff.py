"""Parser de objetos COFF (`.obj`) y archivos `ar` (`.a`/`.lib`) (§6.2)."""

from __future__ import annotations

from app.engines.binary_analysis.formats import PE_MACHINES
from app.engines.binary_analysis.models import BinaryFacts, Section

_AR_MAGIC = b"!<arch>\n"


def parse_coff(data: bytes, facts: BinaryFacts) -> None:
    facts.format = "COFF"
    facts.file_type = "COFF_OBJECT"
    if len(data) < 20:
        facts.limitations.append("Cabecera COFF incompleta.")
        return

    machine = int.from_bytes(data[0:2], "little")
    num_sections = int.from_bytes(data[2:4], "little")
    opt_size = int.from_bytes(data[16:18], "little")
    characteristics = int.from_bytes(data[18:20], "little")
    facts.architecture = PE_MACHINES.get(machine, f"0x{machine:04x}")
    facts.bits = 64 if machine in (0x8664, 0xAA64) else 32
    facts.signatures.append(f"coff characteristics=0x{characteristics:04x}")

    offset = 20 + opt_size
    for _ in range(min(num_sections, 200)):
        if offset + 40 > len(data):
            break
        raw_name = data[offset : offset + 8]
        size = int.from_bytes(data[offset + 16 : offset + 20], "little")
        name = raw_name.rstrip(b"\x00").decode("ascii", "replace")
        facts.sections.append(Section(name=name or "?", size=size, offset=0))
        offset += 40


def parse_ar(data: bytes, facts: BinaryFacts) -> None:
    """Archivo `ar` (biblioteca estática)."""
    if not data.startswith(_AR_MAGIC):
        facts.limitations.append("Archivo `ar` inválido.")
        return
    facts.format = "AR"
    facts.file_type = "STATIC_LIBRARY"
    facts.architecture = None

    offset = len(_AR_MAGIC)
    long_names = b""
    members: list[str] = []
    while offset + 60 <= len(data):
        header = data[offset : offset + 60]
        if header[58:60] != b"`\n":
            break
        raw_name = header[0:16].decode("ascii", "replace").strip()
        try:
            size = int(header[48:58].decode("ascii", "replace").strip() or "0")
        except ValueError:
            break
        body_start = offset + 60
        if raw_name == "//":
            long_names = data[body_start : body_start + size]
        elif raw_name.startswith("/") and raw_name[1:].strip().isdigit():
            name = _long_name(long_names, int(raw_name[1:]))
            members.append(name)
        elif raw_name and raw_name != "/":
            members.append(raw_name.rstrip("/"))
        offset = body_start + size + (size % 2 == 1)

    for name in members[:200]:
        if name and not name.startswith("__.SYMDEF") and name != "/":
            facts.sections.append(Section(name=name, size=0, offset=0))
    facts.signatures.append(f"ar members={len(members)}")


def _long_name(table: bytes, index: int) -> str:
    if not table or index >= len(table):
        return ""
    end = table.find(b"\x00", index)
    if end == -1:
        end = table.find(b"/\n", index)
    if end == -1:
        end = len(table)
    return table[index:end].decode("ascii", "replace").rstrip("/")
