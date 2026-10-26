"""Parser de WebAssembly `.wasm` (§6.2)."""

from __future__ import annotations

from app.engines.binary_analysis.models import BinaryFacts, Section

_SECTION_NAMES = {
    0: "custom",
    1: "type",
    2: "import",
    3: "function",
    4: "table",
    5: "memory",
    6: "global",
    7: "export",
    8: "start",
    9: "element",
    10: "code",
    11: "data",
    12: "datacount",
}


class _Reader:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def u8(self) -> int:
        value = self.data[self.pos]
        self.pos += 1
        return value

    def uleb(self) -> int:
        result = 0
        shift = 0
        while self.pos < len(self.data):
            byte = self.data[self.pos]
            self.pos += 1
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
        return result

    def bytes(self, count: int) -> bytes:
        chunk = self.data[self.pos : self.pos + count]
        self.pos += count
        return chunk

    def string(self) -> str:
        length = self.uleb()
        return self.bytes(length).decode("utf-8", "replace")


def parse_wasm(data: bytes, facts: BinaryFacts) -> None:
    facts.format = "WASM"
    facts.file_type = "WASM_MODULE"
    facts.architecture = "WebAssembly"
    facts.bits = 32
    facts.runtime_indicators.append("WebAssembly")

    version = int.from_bytes(data[4:8], "little")
    facts.signatures.append(f"wasm version={version}")

    reader = _Reader(data, 8)
    while not reader.eof():
        section_id = reader.u8()
        size = reader.uleb()
        name = _SECTION_NAMES.get(section_id, f"unknown({section_id})")
        facts.sections.append(Section(name=name, size=size, offset=reader.pos))
        end = min(reader.pos + size, len(data))
        payload = data[reader.pos : end]
        if section_id == 2:
            _parse_imports(payload, facts)
        elif section_id == 7:
            _parse_exports(payload, facts)
        reader.pos = end


def _parse_imports(payload: bytes, facts: BinaryFacts) -> None:
    reader = _Reader(payload)
    count = reader.uleb()
    for _ in range(count):
        if reader.eof():
            break
        module = reader.string()
        field = reader.string()
        facts.imported_symbols.append(f"{module}.{field}")
        if reader.eof():
            break
        reader.u8()
        _skip_import_descriptor(reader)


def _skip_import_descriptor(reader: _Reader) -> None:
    kind = reader.data[reader.pos - 1] if reader.pos > 0 else 0
    if kind == 0:
        reader.uleb()
    elif kind == 1:
        reader.u8()
        flags = reader.uleb()
        reader.uleb()
        if flags & 1:
            reader.uleb()
    elif kind == 2:
        flags = reader.uleb()
        reader.uleb()
        if flags & 1:
            reader.uleb()
    elif kind == 3:
        reader.u8()
        reader.u8()


def _parse_exports(payload: bytes, facts: BinaryFacts) -> None:
    reader = _Reader(payload)
    count = reader.uleb()
    for _ in range(count):
        if reader.eof():
            break
        name = reader.string()
        facts.exported_symbols.append(name)
        reader.u8()
        reader.uleb()
