"""Folder size boundaries without allocating multi-gigabyte fixtures."""

import zipfile

import pytest

from qrft.core.folder import verify_folder
from qrft.encoder_cli import archive, entrypoint


def test_default_limits_and_cli_help(capsys):
    assert archive.DEFAULT_MAX_ARCHIVE_MIB == 4096
    assert archive.MAX_ARCHIVE_BYTES == 2 * 1024**3
    assert archive.MAX_SOURCE_BYTES == 4 * 1024**3
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["info", "--help"])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "4096 MiB" in help_text and "4 GiB" in help_text and "2 GiB" in help_text


def test_original_size_counts_all_files_and_allows_exact_limit(tmp_path, monkeypatch):
    root = tmp_path / "folder"
    root.mkdir()
    (root / "first").write_bytes(b"abc")
    (root / "second").write_bytes(b"defg")
    monkeypatch.setattr(archive, "MAX_SOURCE_BYTES", 7)
    buffer, details = archive.build_archive(root)
    with buffer:
        assert details["original_file_bytes"] == 7
        assert details["max_original_file_bytes"] == 7
    monkeypatch.setattr(archive, "MAX_SOURCE_BYTES", 6)
    monkeypatch.setattr(
        archive, "checked_open", lambda *_: pytest.fail("oversized folder was read")
    )
    with pytest.raises(ValueError, match="source size limit"):
        archive.build_archive(root)


def test_full_zip_limit_includes_directory_and_comment(tmp_path, monkeypatch):
    root = tmp_path / "folder"
    root.mkdir()
    (root / "payload").write_bytes(b"a" * 8192)
    buffer, details = archive.build_archive(root)
    with buffer:
        expected = buffer.getvalue()
    assert len(expected) == details["zip_size"]
    monkeypatch.setattr(archive, "MAX_ARCHIVE_BYTES", len(expected))
    buffer, details = archive.build_archive(root)
    with buffer:
        assert buffer.getvalue() == expected
        assert details["max_zip_bytes"] == len(expected)
        assert details["memory_budget_bytes"] <= details["memory_limit_bytes"]
    monkeypatch.setattr(archive, "MAX_ARCHIVE_BYTES", len(expected) - 1)
    with pytest.raises(ValueError, match="ZIP size limit"):
        archive.build_archive(root)


def test_large_source_uses_zip64_and_keeps_folder_fingerprint(tmp_path, monkeypatch):
    root = tmp_path / "folder"
    root.mkdir()
    payload = b"a" * 8192
    (root / "payload").write_bytes(payload)
    monkeypatch.setattr(zipfile, "ZIP64_LIMIT", 1024)
    buffer, _ = archive.build_archive(root)
    with buffer:
        with zipfile.ZipFile(buffer) as zipped:
            info = zipped.getinfo("payload")
            assert info.extract_version >= 45
            assert zipped.read("payload") == payload
        destination = tmp_path / "result.zip"
        destination.write_bytes(buffer.getvalue())
        assert verify_folder(destination, len(payload))["status"] == "PASS"
