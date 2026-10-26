"""Pruebas de seguridad de extracción (§19.3)."""

from __future__ import annotations

import io
import stat
import zipfile

import pytest

from app.core.errors import UnsafeArchiveError
from app.engines.ingestion.safe_zip import ExtractionLimits, inspect_zip, safe_extract
from tests.conftest import make_zip


def _write(tmp_path, data: bytes):
    path = tmp_path / "archive.zip"
    path.write_bytes(data)
    return path


def test_extracts_valid_archive(tmp_path):
    archive = _write(tmp_path, make_zip({"src/app.py": "print('ok')\n", "README.md": "# x"}))
    report = safe_extract(archive, tmp_path / "out", ExtractionLimits())
    names = sorted(f.path for f in report.files)
    assert names == ["README.md", "src/app.py"]
    assert (tmp_path / "out" / "src" / "app.py").read_text() == "print('ok')\n"


def test_rejects_path_traversal(tmp_path):
    archive = _write(tmp_path, make_zip({"../evil.txt": "x"}))
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(archive, ExtractionLimits())


def test_rejects_absolute_path(tmp_path):
    archive = _write(tmp_path, make_zip({"/etc/passwd": "x"}))
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(archive, ExtractionLimits())


def test_rejects_windows_separator(tmp_path):
    archive = _write(tmp_path, make_zip({"..\\evil.txt": "x"}))
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(archive, ExtractionLimits())


def test_rejects_symlink_entry(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "/etc/passwd")
    path = _write(tmp_path, buffer.getvalue())
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(path, ExtractionLimits())


def test_rejects_zip_bomb_by_ratio(tmp_path):
    archive = _write(tmp_path, make_zip({"bomb.txt": "A" * 200_000}))
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(archive, ExtractionLimits(max_compression_ratio=10.0))


def test_rejects_too_many_entries(tmp_path):
    files = {f"f{i}.txt": "x" for i in range(5)}
    archive = _write(tmp_path, make_zip(files))
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(archive, ExtractionLimits(max_entries=2))


def test_rejects_oversized_single_file(tmp_path):
    archive = _write(tmp_path, make_zip({"big.txt": "B" * 5000}))
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(archive, ExtractionLimits(max_file_bytes=1000, max_compression_ratio=1000.0))


def test_rejects_total_size_limit(tmp_path):
    files = {f"f{i}.txt": "C" * 1000 for i in range(5)}
    archive = _write(tmp_path, make_zip(files))
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(archive, ExtractionLimits(max_total_bytes=1000, max_compression_ratio=1000.0))


def test_rejects_non_zip(tmp_path):
    path = tmp_path / "not.zip"
    path.write_bytes(b"not a zip file")
    with pytest.raises(UnsafeArchiveError):
        inspect_zip(path, ExtractionLimits())


def test_nested_archive_not_expanded(tmp_path):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("a.txt", "x")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("nested.zip", inner.getvalue())
        archive.writestr("top.py", "print(1)\n")
    path = _write(tmp_path, outer.getvalue())
    report = safe_extract(path, tmp_path / "out", ExtractionLimits())
    assert "nested.zip" in report.skipped_nested_archives
    assert any(f.path == "top.py" for f in report.files)
