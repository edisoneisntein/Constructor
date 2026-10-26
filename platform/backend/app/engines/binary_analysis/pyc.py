"""Parser de bytecode compilado de CPython (`.pyc`) (§6.2)."""

from __future__ import annotations

from app.engines.binary_analysis.models import BinaryFacts

_PYC_MAGIC = {
    3413: "3.8",
    3425: "3.9",
    3439: "3.10",
    3495: "3.11",
    3531: "3.12",
    3571: "3.13",
}


def parse_pyc(data: bytes, facts: BinaryFacts) -> None:
    facts.format = "PYC"
    facts.file_type = "CPYTHON_BYTECODE"
    facts.architecture = "CPython bytecode"
    facts.runtime_indicators.append("Python")
    if len(data) >= 4:
        magic = int.from_bytes(data[0:2], "little")
        version = _PYC_MAGIC.get(magic)
        facts.signatures.append(f"pyc magic=0x{magic:04x}" + (f" python={version}" if version else ""))
        if version:
            facts.runtime_indicators.append(f"Python {version}")
    if len(data) >= 8:
        flags = int.from_bytes(data[4:8], "little")
        if flags & 0x01:
            facts.runtime_indicators.append("PYC hash-based")
        elif flags & 0x02:
            facts.runtime_indicators.append("PYC checked-hash")
    facts.limitations.append(
        "El bytecode compilado no equivale al código fuente; se ofrecen metadatos y "
        "cadenas como evidencia contextual (§6.2/§6.4)."
    )
