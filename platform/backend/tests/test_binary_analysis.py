"""Pruebas del motor de análisis de binarios (§6.2) con fixtures construidos."""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.engines.binary_analysis import analyze_binary, compare_binaries, detect_format
from tests.conftest import auth_headers, register


# --------------------------------------------------------------------------- #
# Construcción de binarios mínimos válidos
# --------------------------------------------------------------------------- #
def build_elf() -> bytes:
    endian = "<"
    shstr = b"\0.dynstr\0.dynsym\0.dynamic\0.debug_info\0.shstrtab\0"
    dynstr = b"\0libc.so.6\0printf\0my_export\0"
    debug = b"https://example.com 1.2.3\0"

    dynstr_off = 64
    dynsym_off = 96
    dynamic_off = 168
    debug_off = 200
    shstr_off = debug_off + len(debug)
    shoff = shstr_off + len(shstr)
    shoff += (-shoff) % 8

    e_ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    header = e_ident + struct.pack(
        endian + "HHIQQQIHHHHHH",
        3,  # DYN
        0x3E,  # x86_64
        1,
        0x1000,
        0,
        shoff,
        0,
        64,
        0,
        0,
        64,
        6,
        5,
    )

    dynstr_bytes = dynstr.ljust(dynstr_off + len(dynstr) - dynstr_off, b"\x00")
    dynsym = (
        b"\x00" * 24
        + struct.pack(endian + "IBBHQQ", 11, 0x12, 0, 0, 0, 0)  # printf (UNDEF)
        + struct.pack(endian + "IBBHQQ", 18, 0x12, 0, 1, 0x1000, 0)  # my_export (GLOBAL)
    )
    dynamic = struct.pack(endian + "QQ", 1, 1) + struct.pack(endian + "QQ", 0, 0)

    def section(name, stype, offset, size, link=0, info=0, align=1, entsize=0):
        return struct.pack(endian + "IIQQQQIIQQ", name, stype, 0, 0, offset, size, link, info, align, entsize)

    sections = b"".join(
        [
            section(0, 0, 0, 0),
            section(1, 3, dynstr_off, len(dynstr)),
            section(9, 11, dynsym_off, len(dynsym), link=1, info=1, align=8, entsize=24),
            section(17, 6, dynamic_off, len(dynamic), link=1, align=8, entsize=16),
            section(26, 1, debug_off, len(debug)),
            section(38, 3, shstr_off, len(shstr)),
        ]
    )

    buffer = bytearray(shoff + len(sections))
    buffer[0:64] = header
    buffer[dynstr_off : dynstr_off + len(dynstr)] = dynstr
    buffer[dynsym_off : dynsym_off + len(dynsym)] = dynsym
    buffer[dynamic_off : dynamic_off + len(dynamic)] = dynamic
    buffer[debug_off : debug_off + len(debug)] = debug
    buffer[shstr_off : shstr_off + len(shstr)] = shstr
    buffer[shoff : shoff + len(sections)] = sections
    assert len(dynstr_bytes) == len(dynstr)
    return bytes(buffer)


def build_pe() -> bytes:
    raw_base = 0x200
    rva_base = 0x1000

    buffer = bytearray(1024)
    buffer[0:2] = b"MZ"
    buffer[0x3C:0x40] = struct.pack("<I", 0x40)
    buffer[0x40:0x44] = b"PE\x00\x00"

    coff = struct.pack("<HHIIIHH", 0x14C, 1, 0, 0, 0, 224, 0x0102)
    optional = bytearray(224)
    struct.pack_into("<H", optional, 0, 0x10B)
    struct.pack_into("<I", optional, 16, rva_base)  # entry point
    struct.pack_into("<I", optional, 92, 16)  # number of data directories
    struct.pack_into("<II", optional, 96 + 1 * 8, rva_base, 20)  # import directory

    section_header = struct.pack(
        "<8sIIIIIIHHI",
        b".rdata\x00\x00",
        0x400,
        rva_base,
        raw_base,
        raw_base,
        0,
        0,
        0,
        0,
        0,
    )

    buffer[0x44 : 0x44 + 20] = coff
    buffer[0x44 + 20 : 0x44 + 20 + 224] = optional
    buffer[0x44 + 20 + 224 : 0x44 + 20 + 224 + 40] = section_header

    def put(rva: int, blob: bytes) -> None:
        offset = raw_base + (rva - rva_base)
        buffer[offset : offset + len(blob)] = blob

    put(0x1000, struct.pack("<IIIII", 0x1028, 0, 0, 0x1048, 0x1038))
    put(0x1014, b"\x00" * 20)
    put(0x1028, struct.pack("<II", 0x1058, 0))
    put(0x1038, struct.pack("<II", 0x1058, 0))
    put(0x1048, b"KERNEL32.dll\x00")
    put(0x1058, struct.pack("<H", 0) + b"GetProcAddress\x00")
    return bytes(buffer)


def build_macho() -> bytes:
    dylib_name = b"/usr/lib/libSystem.B.dylib\x00"
    cmd1_size = 24 + len(dylib_name)
    cmd1_size += (-cmd1_size) % 8
    cmd2_size = 24
    header_size = 32
    cmd1_off = header_size
    cmd2_off = cmd1_off + cmd1_size
    symoff = cmd2_off + cmd2_size
    strtab = b"\0_main\0dyld_stub_binder\0"
    stroff = symoff + 32
    total = stroff + len(strtab)

    buffer = bytearray(total)
    buffer[0:4] = b"\xcf\xfa\xed\xfe"
    struct.pack_into("<IIIIIII", buffer, 4, 0x01000007, 3, 2, 2, cmd1_size + cmd2_size, 0, 0)

    struct.pack_into("<IIII", buffer, cmd1_off, 0xC, cmd1_size, 24, 0)
    buffer[cmd1_off + 24 : cmd1_off + 24 + len(dylib_name)] = dylib_name

    struct.pack_into("<IIIIII", buffer, cmd2_off, 0x2, cmd2_size, symoff, 2, stroff, len(strtab))
    struct.pack_into("<I", buffer, symoff, 1)
    struct.pack_into("<I", buffer, symoff + 16, 7)
    buffer[stroff : stroff + len(strtab)] = strtab
    return bytes(buffer)


def build_java_class() -> bytes:
    return b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + b"\x00" * 16


def _uleb(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def build_wasm() -> bytes:
    def section(section_id: int, payload: bytes) -> bytes:
        return bytes([section_id]) + _uleb(len(payload)) + payload

    type_section = b"\x01\x60\x00\x01\x7f"
    import_section = (
        b"\x01" + b"\x03env" + b"\x03foo" + b"\x00" + b"\x00"
    )
    export_section = b"\x01" + b"\x03run" + b"\x00" + b"\x01"
    code_section = b"\x01" + b"\x02\x00\x0b"
    return (
        b"\x00asm"
        + struct.pack("<I", 1)
        + section(1, type_section)
        + section(2, import_section)
        + section(7, export_section)
        + section(10, code_section)
    )


def build_dex() -> bytes:
    buffer = bytearray(0x100)
    buffer[0:8] = b"dex\n035\x00"
    struct.pack_into("<I", buffer, 0x20, 0x70)  # header_size
    struct.pack_into("<I", buffer, 0x38, 2)  # string_ids_size
    struct.pack_into("<I", buffer, 0x3C, 0x70)  # string_ids_off
    first = b"Lcom/example/Main;"
    second = b"run"
    str1 = _uleb(len(first)) + first + b"\x00"
    str2 = _uleb(len(second)) + second + b"\x00"
    struct.pack_into("<I", buffer, 0x70, 0x78)
    struct.pack_into("<I", buffer, 0x74, 0x78 + len(str1))
    buffer[0x78 : 0x78 + len(str1)] = str1
    buffer[0x78 + len(str1) : 0x78 + len(str1) + len(str2)] = str2
    return bytes(buffer)


def build_pyc() -> bytes:
    return struct.pack("<H", 3531) + b"\r\n" + struct.pack("<I", 0) + b"\x00" * 24


def build_coff() -> bytes:
    header = struct.pack("<HHIIIHH", 0x14C, 1, 0, 0, 0, 0, 0x0104)
    section = b".text\x00\x00\x00" + struct.pack("<IIIIIIHHI", 0, 0, 16, 0, 0, 0, 0, 0, 0)
    return header + section


def build_ar() -> bytes:
    member = struct.pack("<HHIIIHH", 0x14C, 1, 0, 0, 0, 0, 0x0104)
    body = member + b"\x00" * 4
    name = b"main.o/"
    header = (
        name.ljust(16)
        + b"0".ljust(12)
        + b"0".ljust(6)
        + b"0".ljust(6)
        + b"100644".ljust(8)
        + str(len(body)).encode().ljust(10)
        + b"`\n"
    )
    return b"!<arch>\n" + header + body


def build_zip_jar() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        archive.writestr("com/example/Main.class", build_java_class())
    return buffer.getvalue()


def build_apk() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AndroidManifest.xml", "binary-xml")
        archive.writestr("classes.dex", build_dex())
        archive.writestr("lib/arm64-v8a/libnative.so", "\x7fELF" + "\x00" * 60)
    return buffer.getvalue()


def build_plain_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data.txt", "hello")
    return buffer.getvalue()


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# --------------------------------------------------------------------------- #
# Detección y análisis por formato
# --------------------------------------------------------------------------- #
def test_detect_format():
    assert detect_format(build_elf()) == "ELF"
    assert detect_format(build_pe()) == "PE"
    assert detect_format(build_macho()) == "MACHO"
    assert detect_format(build_java_class()) == "JAVA_CLASS"
    assert detect_format(b"not-a-binary") == "UNKNOWN"


def test_analyze_elf(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "sample.elf", build_elf()))
    assert facts.format == "ELF"
    assert facts.architecture == "x86_64"
    assert facts.bits == 64
    assert facts.file_type == "DYN"
    assert facts.entry_point == 0x1000
    assert "printf" in facts.imported_symbols
    assert "my_export" in facts.exported_symbols
    assert "libc.so.6" in facts.linked_libraries
    assert facts.debug_info_present is True
    assert any("https://" in value for value in facts.strings_sample)
    assert "1.2.3" in facts.signatures
    assert any(".debug_info" in section.name for section in facts.sections)


def test_analyze_pe(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "sample.exe", build_pe()))
    assert facts.format == "PE"
    assert facts.architecture == "i386"
    assert facts.bits == 32
    assert facts.file_type == "EXE"
    assert "KERNEL32.dll" in facts.linked_libraries
    assert "GetProcAddress" in facts.imported_symbols


def test_analyze_macho(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "sample.macho", build_macho()))
    assert facts.format == "MACHO"
    assert facts.architecture == "x86_64"
    assert facts.file_type == "EXECUTE"
    assert "/usr/lib/libSystem.B.dylib" in facts.linked_libraries
    assert "main" in facts.exported_symbols
    assert "dyld_stub_binder" in facts.imported_symbols


def test_analyze_java_class(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "Sample.class", build_java_class()))
    assert facts.format == "JAVA_CLASS"
    assert "Java" in facts.runtime_indicators


def test_detect_format_extended():
    assert detect_format(build_wasm()) == "WASM"
    assert detect_format(build_dex()) == "DEX"
    assert detect_format(build_pyc()) == "PYC"
    assert detect_format(build_coff()) == "COFF"
    assert detect_format(build_ar()) == "AR"
    assert detect_format(build_zip_jar()) == "ZIP"
    assert detect_format(build_apk()) == "ZIP"


def test_analyze_wasm(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "module.wasm", build_wasm()))
    assert facts.format == "WASM"
    assert facts.architecture == "WebAssembly"
    assert "env.foo" in facts.imported_symbols
    assert "run" in facts.exported_symbols
    assert "WebAssembly" in facts.runtime_indicators
    assert any(section.name == "code" for section in facts.sections)


def test_analyze_dex(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "classes.dex", build_dex()))
    assert facts.format == "DEX"
    assert facts.architecture == "Dalvik/ART"
    assert "Android" in facts.runtime_indicators
    assert any("Lcom/example/Main;" == value for value in facts.strings_sample)


def test_analyze_pyc(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "module.pyc", build_pyc()))
    assert facts.format == "PYC"
    assert "Python" in facts.runtime_indicators
    assert "Python 3.12" in facts.runtime_indicators
    assert any("pyc magic" in value for value in facts.signatures)


def test_analyze_coff(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "module.obj", build_coff()))
    assert facts.format == "COFF"
    assert facts.architecture == "i386"
    assert facts.bits == 32
    assert any(section.name == ".text" for section in facts.sections)


def test_analyze_ar(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "libfoo.a", build_ar()))
    assert facts.format == "AR"
    assert facts.file_type == "STATIC_LIBRARY"
    assert any(section.name == "main.o" for section in facts.sections)


def test_analyze_jar_and_apk_and_zip(tmp_path: Path):
    jar = analyze_binary(_write(tmp_path, "app.jar", build_zip_jar()))
    assert jar.format == "JAR"
    assert "Java" in jar.runtime_indicators
    assert any(section.name == "com/example/Main.class" for section in jar.sections)
    class_entry = next(e for e in jar.embedded if e["name"].endswith("Main.class"))
    assert class_entry["format"] == "JAVA_CLASS"
    assert class_entry["major"] == 52

    apk = analyze_binary(_write(tmp_path, "app.apk", build_apk()))
    assert apk.format == "APK"
    assert "Android" in apk.runtime_indicators
    assert "libnative.so" in apk.linked_libraries
    dex_entry = next(e for e in apk.embedded if e["name"] == "classes.dex")
    assert dex_entry["format"] == "DEX"
    so_entry = next(e for e in apk.embedded if e["name"].endswith("libnative.so"))
    assert so_entry["format"] == "ELF"

    plain = analyze_binary(_write(tmp_path, "data.zip", build_plain_zip()))
    assert plain.format == "ZIP"
    assert any(section.name == "data.txt" for section in plain.sections)


def test_embedded_nested_archive_is_not_expanded(tmp_path: Path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("inner.jar", build_zip_jar())
        archive.writestr("readme.txt", "hello")
    facts = analyze_binary(_write(tmp_path, "outer.zip", buffer.getvalue()))
    nested = next(e for e in facts.embedded if e["name"] == "inner.jar")
    assert nested["format"] == "ARCHIVE"
    assert not any(e["name"].endswith("Main.class") for e in facts.embedded)
    assert any("no recursiva" in note for note in facts.limitations)


def test_embedded_inspection_respects_byte_limit(tmp_path: Path):
    from app.engines.binary_analysis.archive import parse_zip
    from app.engines.binary_analysis.models import BinaryFacts

    facts = BinaryFacts(path="x", size_bytes=0, sha256="", sha1="", md5="")
    parse_zip(build_zip_jar(), facts, inner_limit_bytes=8)
    assert any(entry["format"] == "TRUNCATED" for entry in facts.embedded)


def test_upload_wasm_matches_known_formats(client: TestClient):
    session = register(client, "wasm@example.com", "Wasm Org")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "Wasm"}, headers=headers).json()
    upload = client.post(
        f"/api/v1/projects/{project['id']}/binaries",
        files={"file": ("module.wasm", build_wasm(), "application/octet-stream")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    analyzed = client.post(
        f"/api/v1/projects/{project['id']}/binary-analyses",
        json={"artifact_id": upload.json()["id"]},
        headers=headers,
    )
    assert analyzed.status_code == 201, analyzed.text
    assert analyzed.json()["format"] == "WASM"


def test_meta_lists_binary_formats(client: TestClient):
    meta = client.get("/api/v1/meta").json()
    assert "WASM" in meta["binary_formats"]
    assert "DEX" in meta["binary_formats"]
    assert meta["capabilities"]["binary_analysis"] == "PARTIALLY_IMPLEMENTED"
    assert meta["capabilities"]["binary_analysis_advanced"] == "PROPOSED_NOT_IMPLEMENTED"


def test_analyze_unknown_format_records_limitation(tmp_path: Path):
    facts = analyze_binary(_write(tmp_path, "blob.bin", b"random-bytes-here-0123456789"))
    assert facts.format == "UNKNOWN"
    assert facts.limitations
    assert facts.sha256


def test_compare_binaries(tmp_path: Path):
    left = analyze_binary(_write(tmp_path, "a.elf", build_elf()))
    right = analyze_binary(_write(tmp_path, "b.elf", build_elf() + b"\x00"))
    diff = compare_binaries(left, right)
    assert diff["same_format"] is True
    assert diff["same_digest"] is False
    assert diff["size_delta"] == 1


# --------------------------------------------------------------------------- #
# Flujo por API
# --------------------------------------------------------------------------- #
def test_binary_analysis_api_flow(client: TestClient, tmp_path: Path):
    session = register(client, "bin@example.com", "Bin Org")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "Bin"}, headers=headers).json()

    upload = client.post(
        f"/api/v1/projects/{project['id']}/binaries",
        files={"file": ("sample.elf", build_elf(), "application/octet-stream")},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    artifact = upload.json()
    assert artifact["kind"] == "BINARY"

    analyzed = client.post(
        f"/api/v1/projects/{project['id']}/binary-analyses",
        json={"artifact_id": artifact["id"]},
        headers=headers,
    )
    assert analyzed.status_code == 201, analyzed.text
    body = analyzed.json()
    assert body["format"] == "ELF"
    assert body["facts"]["architecture"] == "x86_64"
    analysis_id = body["id"]

    fetched = client.get(f"/api/v1/binary-analyses/{analysis_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["sha256"] == artifact["sha256"]

    listed = client.get(f"/api/v1/projects/{project['id']}/binary-analyses", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    compared = client.post(
        "/api/v1/binary-analyses/compare",
        json={"left_id": analysis_id, "right_id": analysis_id},
        headers=headers,
    )
    assert compared.status_code == 200, compared.text
    assert compared.json()["same_digest"] is True


def test_binary_upload_rejects_unknown_and_is_org_scoped(client: TestClient):
    session = register(client, "bin-owner@example.com", "Bin A")
    headers = auth_headers(session["token"])
    project = client.post("/api/v1/projects", json={"name": "A"}, headers=headers).json()

    rejected = client.post(
        f"/api/v1/projects/{project['id']}/binaries",
        files={"file": ("weird.bin", b"definitely-not-a-binary", "application/octet-stream")},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "validation_error"

    upload = client.post(
        f"/api/v1/projects/{project['id']}/binaries",
        files={"file": ("ok.elf", build_elf(), "application/octet-stream")},
        headers=headers,
    ).json()
    analysis = client.post(
        f"/api/v1/projects/{project['id']}/binary-analyses",
        json={"artifact_id": upload["id"]},
        headers=headers,
    ).json()

    outsider = register(client, "bin-outsider@example.com", "Bin B")
    outsider_headers = auth_headers(outsider["token"])
    assert (
        client.get(f"/api/v1/binary-analyses/{analysis['id']}", headers=outsider_headers).status_code
        == 404
    )
