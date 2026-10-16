"""Folder size boundaries without allocating multi-gigabyte fixtures."""

import zipfile

import pytest

from qrft.core.folder import verify_folder
from qrft.encoder_cli import archive, entrypoint


def test_default_limits_and_cli_help(capsys):
    assert archive.DEFAULT_MAX_SOURCE_GIB == 16
    assert archive.source_limit_bytes(16) == 16 * 1024**3
    with pytest.raises(SystemExit) as result:
        entrypoint.main(["info", "--help"])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "--max-source-gib" in help_text and "16 GiB" in help_text
    assert "--max-archive-mib" not in help_text


def test_original_size_counts_all_files_and_allows_exact_limit(tmp_path, monkeypatch):
    root = tmp_path / "folder"
    root.mkdir()
    (root / "first").write_bytes(b"abc")
    (root / "second").write_bytes(b"defg")
    monkeypatch.setattr(archive, "source_limit_bytes", lambda _: 7)
    buffer, details = archive.build_archive(root)
    with buffer:
        assert details["original_file_bytes"] == 7
        assert details["max_original_file_bytes"] == 7
    monkeypatch.setattr(archive, "source_limit_bytes", lambda _: 6)
    monkeypatch.setattr(
        archive, "checked_open", lambda *_: pytest.fail("oversized folder was read")
    )
    with pytest.raises(ValueError, match="source size limit"):
        archive.build_archive(root)


def test_zip_can_exceed_source_limit_without_separate_output_or_memory_cap(tmp_path, monkeypatch):
    root = tmp_path / "folder"
    root.mkdir()
    (root / "payload").write_bytes(b"abc")
    monkeypatch.setattr(archive, "source_limit_bytes", lambda _: 3)
    buffer, details = archive.build_archive(root)
    with buffer:
        assert details["original_file_bytes"] == 3
        assert details["zip_size"] > 3
        assert "max_zip_bytes" not in details
        assert "memory_limit_bytes" not in details
        assert "memory_budget_bytes" not in details
        with zipfile.ZipFile(buffer) as zipped:
            assert zipped.read("payload") == b"abc"


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "16"])
def test_source_limit_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="positive integer"):
        archive.source_limit_bytes(value)


def test_regular_file_source_limit_checked_before_hashing(tmp_path, monkeypatch):
    from qrft.encoder_cli import source as source_module

    source_path = tmp_path / "payload"
    source_path.write_bytes(b"abcd")
    monkeypatch.setattr(source_module, "source_limit_bytes", lambda _: 4)
    with source_module.Source(source_path) as source:
        assert source.actual_size == 4
    monkeypatch.setattr(source_module, "source_limit_bytes", lambda _: 3)
    monkeypatch.setattr(
        source_module,
        "inspect_file",
        lambda *_args, **_kwargs: pytest.fail("oversized file was hashed"),
    )
    with pytest.raises(ValueError, match="Source file size limit"):
        source_module.Source(source_path)


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


def test_out_of_memory_closes_archive_and_reports_cli_error(tmp_path, monkeypatch, capsys):
    root = tmp_path / "folder"
    root.mkdir()
    (root / "payload").write_bytes(b"data")
    real_zip = zipfile.ZipFile
    buffers = []

    class OutOfMemoryZip(real_zip):
        def open(self, name, mode="r", *args, **kwargs):
            if mode == "w":
                buffers.append(self.fp)
                raise MemoryError("simulated allocation failure")
            return super().open(name, mode, *args, **kwargs)

    monkeypatch.setattr(zipfile, "ZipFile", OutOfMemoryZip)
    assert entrypoint.main(["info", str(root)]) == 2
    assert "内存不足" in capsys.readouterr().err
    assert buffers and buffers[0].closed
