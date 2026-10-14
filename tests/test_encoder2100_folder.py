"""RAM ZIP, stable identities, real ZXing and source-only CLI regression."""

import hashlib
import io
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest
import zxingcpp
from PIL import Image

from qrft.encoder2100 import archive, cli, player
from qrft.encoder2100.encoder import Source, export, select
from qrft.encoder2100.protocol import FINISH_ID, START_ID
from qrft.encoder2100.qr import png


def sample(root):
    root.mkdir()
    (root / "空目录").mkdir()
    (root / "嵌套 空间").mkdir()
    (root / "嵌套 空间" / "empty").mkdir()
    (root / "嵌套 空间" / "中文,#&[].EXE").write_bytes(bytes(range(256)) * 3)
    (root / ".hidden").write_bytes(b"hidden\x00\xff")
    (root / "Zero.bin").write_bytes(b"")
    (root / "MiX.TXT").write_bytes(b"Case Preserved\n")
    return root


def snapshot(root):
    with Source(root) as source:
        with source.open_stream() as stream:
            data = stream.read()
        return data, source.describe()


def logical_from_memory_zip(data):
    """Independent test implementation of the published canonical serialization."""
    md5, sha = hashlib.md5(), hashlib.sha256()
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        entries = [("", True, b"")]
        entries.extend(
            (i.filename.rstrip("/"), i.is_dir(), zipped.read(i)) for i in zipped.infolist()
        )
        for path, directory, content in sorted(entries, key=lambda item: item[0].encode("utf-8")):
            encoded = path.encode("utf-8")
            raw = (
                (b"D" if directory else b"F")
                + struct.pack(">Q", len(encoded))
                + encoded
                + struct.pack(">Q", len(content))
                + content
            )
            if not path:
                md5.update(b"QRFT2100-FOLDER-CONTENT\x00\x01")
                sha.update(b"QRFT2100-FOLDER-CONTENT\x00\x01")
            md5.update(raw)
            sha.update(raw)
    return md5.hexdigest().upper(), sha.hexdigest().upper()


@pytest.mark.parametrize("kind", ["empty", "single", "nested"])
def test_deterministic_zip_and_stable_content(tmp_path, kind):
    root = tmp_path / "Input"
    if kind == "nested":
        sample(root)
    else:
        root.mkdir()
        if kind == "single":
            (root / "hello").write_bytes(b"hello")
    first, details = snapshot(root)
    second, repeated = snapshot(root)
    assert first == second and details == repeated
    assert details["md5"] == details["archive_zip_md5"] == hashlib.md5(first).hexdigest().upper()
    assert details["archive_zip_sha256"] == hashlib.sha256(first).hexdigest().upper()
    assert logical_from_memory_zip(first) == (
        details["folder_content_md5"],
        details["folder_content_sha256"],
    )
    assert details["folder_content_md5"] != details["archive_zip_md5"]
    with zipfile.ZipFile(io.BytesIO(first)) as zipped:
        assert json.loads(zipped.comment)["folder_content_md5"] == details["folder_content_md5"]
        assert zipped.namelist() == sorted(
            zipped.namelist(), key=lambda name: name.rstrip("/").encode()
        )
        for item in zipped.infolist():
            assert item.date_time == (1980, 1, 1, 0, 0, 0)
            assert item.create_system == 3 and item.extra == item.comment == b""
            assert item.compress_type == zipfile.ZIP_DEFLATED
            if not item.filename.isascii():
                assert item.flag_bits & 0x800
    assert details["zip_size"] == len(first)
    assert details["memory_budget_bytes"] <= details["memory_limit_bytes"]


def test_timestamp_parent_root_name_and_attributes_do_not_change_zip(tmp_path):
    root = sample(tmp_path / "Original")
    first, details = snapshot(root)
    for path in [root, *root.rglob("*")]:
        os.utime(path, ns=(1700000000000000000, 1700000000000000000))
    assert snapshot(root)[0] == first
    copied = tmp_path / "different-parent" / "RenamedRoot"
    shutil.copytree(root, copied)
    second, moved = snapshot(copied)
    assert second == first
    assert moved["folder_content_md5"] == details["folder_content_md5"]
    assert moved["name"] == "RenamedRoot.zip"  # Name only in START, not ZIP bytes.
    if sys.platform == "win32":
        import ctypes

        path = root / ".hidden"
        attrs = path.stat().st_file_attributes
        try:
            assert ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs | 2)
            assert snapshot(root)[0] == first
        finally:
            assert ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs)


@pytest.mark.parametrize("change", ["content", "path", "add", "delete", "empty-dir", "case"])
def test_logical_changes_detected(tmp_path, change):
    root = sample(tmp_path / "Input")
    before, details = snapshot(root)
    file = root / "MiX.TXT"
    if change == "content":
        file.write_bytes(b"different")
    elif change == "path":
        file.rename(root / "嵌套 空间" / file.name)
    elif change == "add":
        (root / "new").write_bytes(b"")
    elif change == "delete":
        file.unlink()
    elif change == "empty-dir":
        (root / "another-empty").mkdir()
    else:
        file.rename(root / "temporary")
        (root / "temporary").rename(root / "mix.txt")
    after, changed = snapshot(root)
    assert after != before
    assert changed["folder_content_md5"] != details["folder_content_md5"]
    assert changed["folder_content_sha256"] != details["folder_content_sha256"]


def test_no_tempfiles_or_disk_zip_and_limit(tmp_path, monkeypatch):
    root = sample(tmp_path / "Input")
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}

    def denied(*args, **kwargs):
        raise AssertionError("Temporary file creation forbidden")

    for name in (
        "TemporaryFile",
        "NamedTemporaryFile",
        "SpooledTemporaryFile",
        "mkstemp",
        "mkdtemp",
    ):
        monkeypatch.setattr(tempfile, name, denied)
    original_open = Path.open

    def read_only(self, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", read_only)
    with Source(root, max_archive_mib=4) as source:
        assert isinstance(source._archive, io.BytesIO)
        with source.open_stream() as first, source.open_stream() as second:
            assert first.read(10) == second.read(10)
            first.seek(0)
            assert first.read(10) != second.read(10)
        with pytest.raises(io.UnsupportedOperation), source.open_stream() as stream:
            stream.write(b"invalid")
    assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == before
    monkeypatch.setattr(Path, "open", original_open)
    (root / "random").write_bytes(os.urandom(4 * 1024 * 1024))
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    with pytest.raises(ValueError, match="memory limit"):
        Source(root, max_archive_mib=4)
    assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == before


@pytest.mark.parametrize("change", ["content", "tree", "rewrite-restore-time"])
def test_source_changes_during_packaging_refused(tmp_path, monkeypatch, change):
    root = tmp_path / "Input"
    root.mkdir()
    first = root / "a.bin"
    first.write_bytes(b"abc")
    (root / "z.bin").write_bytes(b"last")
    original = zipfile.ZipFile.open

    def mutate(self, name, mode="r", *args, **kwargs):
        if isinstance(name, zipfile.ZipInfo) and name.filename == "z.bin" and mode == "w":
            state = first.stat()
            if change == "tree":
                (root / "new").write_bytes(b"new")
            else:
                first.write_bytes(b"xyz")
                if change == "rewrite-restore-time":
                    os.utime(first, ns=(state.st_atime_ns, state.st_mtime_ns))
        return original(self, name, mode, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", mutate)
    with pytest.raises(ValueError, match="changed"):
        Source(root)
    assert not list(tmp_path.glob("*.zip"))


def test_junction_and_cycles_refused_without_outside_reads(tmp_path):
    root = tmp_path / "Input"
    outside = tmp_path / "Outside"
    root.mkdir()
    outside.mkdir()
    (outside / "private").write_bytes(b"outside")
    if sys.platform == "win32":
        # mklink /J requires no symlink privilege. Only a new test-owned junction is created.
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(root / "Link"), str(outside)],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    else:
        (root / "Link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="reparse|link"):
        Source(root)
    with pytest.raises(ValueError, match="reparse|link"):
        Source(root / "Link")
    assert (outside / "private").read_bytes() == b"outside"
    # Windows junction cleanup removes the link itself, never its target.
    if sys.platform == "win32":
        os.rmdir(root / "Link")
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(root / "Loop"), str(root)],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
    else:
        (root / "Link").unlink()
        (root / "Loop").symlink_to(root, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="reparse|link|cycle"):
            Source(root)
    finally:
        if sys.platform == "win32":
            os.rmdir(root / "Loop")
        else:
            (root / "Loop").unlink()


def test_folder_real_qr_recovery_zip_content_and_retransmission(tmp_path):
    root = sample(tmp_path / "Input")
    (root / "random").write_bytes(os.urandom(5000))
    with Source(root) as source:
        with source.open_stream() as stream:
            original = stream.read()
        metadata = source.describe()
        frames = list(source.frames(select(source.metadata.packets)))
        assert [i for i, _ in frames] == [START_ID, *range(source.metadata.packets), FINISH_ID]
        decoded = {}
        for expected, text in frames:
            result = zxingcpp.read_barcode(Image.open(io.BytesIO(png(text))))
            assert result is not None and result.text == text
            assert set(result.text) <= set("0123456789ABCDEF")
            number = int(bytes.fromhex(result.text[-16:]))
            content = bytes.fromhex(result.text[:-48])
            assert hashlib.md5(content).hexdigest().upper() == result.text[-48:-16]
            assert number == expected
            decoded[number] = content
        assert decoded[START_ID].decode().rsplit(",", 3)[1] == metadata["archive_zip_md5"]
        recovered = b"".join(decoded[i] for i in range(source.metadata.packets))
        assert recovered == original
        assert hashlib.md5(recovered).hexdigest().upper() == metadata["archive_zip_md5"]
        assert logical_from_memory_zip(recovered)[0] == metadata["folder_content_md5"]
        with pytest.raises(ValueError, match="original Archive ZIP MD5"):
            list(source.frames([(0, 0)]))
        with zipfile.ZipFile(io.BytesIO(recovered)) as zipped:
            expected_files = {
                p.relative_to(root).as_posix(): p.read_bytes()
                for p in root.rglob("*")
                if p.is_file()
            }
            expected_dirs = {
                p.relative_to(root).as_posix() + "/" for p in root.rglob("*") if p.is_dir()
            }
            assert {
                i.filename: zipped.read(i) for i in zipped.infolist() if not i.is_dir()
            } == expected_files
            assert {i.filename for i in zipped.infolist() if i.is_dir()} == expected_dirs
        output = tmp_path / "png"
        assert export(source, output, select(source.metadata.packets))["control_repeats"] == 1
    with Source(root, expected_archive_md5=metadata["archive_zip_md5"]) as retry:
        frames2 = list(retry.frames([(0, 0)]))
        assert frames2[1][1] == frames[1][1]
        with retry.open_stream() as stream:
            assert stream.read() == original
    with pytest.raises(ValueError, match="mismatch"):
        Source(root, expected_archive_md5=metadata["folder_content_md5"])


def test_cli_folder_info_play_export_and_expected_archive_guard(tmp_path, monkeypatch, capsys):
    root = sample(tmp_path / "Input")
    monkeypatch.setattr(cli, "authenticate", lambda: True)
    assert cli.main(["info", str(root)]) == 0
    metadata = json.loads(capsys.readouterr().out)
    assert metadata["file_count"] == 4 and metadata["directory_count"] == 3
    calls = []
    monkeypatch.setattr(
        player,
        "play",
        lambda source, ranges, **options: calls.append((source.describe(), ranges, options)) or 0,
    )
    assert cli.main(["play", str(root)]) == 0
    assert calls[0][2]["log_path"] is None
    assert cli.main(["export", str(root), "--output", str(tmp_path / "export")]) == 0
    assert cli.main(["play", str(root), "--start-id", "0", "--end-id", "0"]) == 2
    assert (
        cli.main(
            [
                "play",
                str(root),
                "--end-id",
                "0",
                "--expected-archive-md5",
                metadata["archive_zip_md5"],
            ]
        )
        == 0
    )
    assert cli.main(["play", str(root), "--expected-archive-md5", "A" * 32]) == 2
    assert cli.main(["info", str(root), "--max-archive-mib", "0"]) == 2


def test_real_terminal_folder_info_and_export(tmp_path):
    from qrft.encoder_cli.console_test import run_encoder

    root = sample(tmp_path / "Input")
    command = [sys.executable, "-m", "qrft.encoder2100.cli"]
    info = run_encoder([*command, "info", str(root)], timeout=30)
    assert info.returncode == 0 and "folder_content_md5" in info.stdout
    output = tmp_path / "export"
    result = run_encoder([*command, "export", str(root), "--output", str(output)], timeout=40)
    assert result.returncode == 0, result.stdout
    metadata = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert metadata["input_kind"] == "folder" and metadata["control_repeats"] == 1
    assert len(list(output.glob("*.png"))) == metadata["packets"] + 2


def test_file_symlink_guard_rejects_before_reading(tmp_path, monkeypatch):
    # Actual junction coverage above needs no Windows symlink privilege. This guard
    # test covers the file symlink mode too, even on hosts returning WinError 1314.
    link = tmp_path / "link"
    link.write_bytes(b"not followed")
    original = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda self: (
            SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            if self == link
            else original(self)
        ),
    )
    with pytest.raises(ValueError, match="link"):
        Source(link)


def test_export_and_optional_log_cannot_modify_input_folder(tmp_path):
    root = sample(tmp_path / "Input")
    before = set(root.rglob("*"))
    with Source(root) as source:
        ranges = select(source.metadata.packets)
        with pytest.raises(ValueError, match="outside the input folder"):
            export(source, root / "png", ranges)
        with pytest.raises(ValueError, match="outside the input folder"):
            player.play(source, ranges, log_path=root / "play.jsonl")
    assert set(root.rglob("*")) == before


def test_chunked_reads_cancellation_and_catalog_memory_bound(tmp_path, monkeypatch):
    root = sample(tmp_path / "Input")
    (root / "large").write_bytes(bytes(200000))
    actual = archive.checked_open
    sizes = []

    class Guard:
        def __init__(self, stream):
            self.stream = stream

        def read(self, size):
            assert 0 < size <= 64 * 1024
            sizes.append(size)
            return self.stream.read(size)

        def fileno(self):
            return self.stream.fileno()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.stream.close()

    monkeypatch.setattr(archive, "checked_open", lambda *args: Guard(actual(*args)))
    with Source(root):
        pass
    assert len(sizes) >= 8
    with pytest.raises(InterruptedError):
        Source(root, cancelled=lambda: True)
    catalog = tmp_path / "Catalog"
    catalog.mkdir()
    for i in range(300):
        (catalog / str(i)).touch()
    with pytest.raises(ValueError, match="memory limit"):
        Source(catalog, max_archive_mib=4)


@pytest.mark.parametrize("kind", ["empty-file", "folder"])
def test_player_single_control_frames_wait_and_finish_hold(tmp_path, monkeypatch, kind):
    import cv2

    if kind == "folder":
        path = sample(tmp_path / "Input")
    else:
        path = tmp_path / "empty"
        path.write_bytes(b"")
    clock, ticks, displays = [0.0], [0], []
    monkeypatch.setattr(player.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(player, "windows_desktop", lambda _: (None, None))
    monkeypatch.setattr(cv2, "namedWindow", lambda *args: None)
    monkeypatch.setattr(cv2, "destroyWindow", lambda *args: None)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(cv2, "imshow", lambda title, pixels: displays.append(pixels.copy()))

    def wait(_):
        ticks[0] += 1
        clock[0] += 0.02
        if ticks[0] < 4:
            assert len(displays) == 1  # Initial START stays completely static.
        return 32 if ticks[0] == 4 else 27 if ticks[0] == 30 else -1

    class Pending:
        def __init__(self, frames, capacity):
            self.frames = frames
            self.queue = deque()

        def fill(self):
            for number, text in self.frames:
                picture = player.render(text)
                self.queue.append(
                    (
                        number,
                        SimpleNamespace(done=lambda: True, result=lambda picture=picture: picture),
                    )
                )

        def close(self):
            self.frames.close()

    monkeypatch.setattr(player, "Frames", Pending)
    monkeypatch.setattr(cv2, "waitKey", wait)
    with Source(path) as source:
        log = tmp_path / "play.jsonl"
        assert player.play(source, select(source.metadata.packets), log_path=log) == 0
        events = [json.loads(line) for line in log.read_text().splitlines()]
        assert [e["packet_id"] for e in events if e["event"] == "display"] == [
            START_ID,
            *range(source.metadata.packets),
            FINISH_ID,
        ]
        assert (
            next(e for e in events if e["event"] == "completed")["position"]
            == source.metadata.packets + 2
        )
        assert events[-1]["event"] == "exit" and events[-1]["complete"]
        region = displays[-1][player.QR_Y : player.QR_Y + 925, player.QR_X : player.QR_X + 925]
        result = zxingcpp.read_barcode(region)
        assert result is not None and int(bytes.fromhex(result.text[-16:])) == FINISH_ID
