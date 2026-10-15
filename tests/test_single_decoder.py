"""Real encoder QR -> MP4 -> ZXing -> durable project -> bytes/MD5 tests."""

import hashlib
import io
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from contextlib import contextmanager

import cv2
import numpy as np
import pytest

from qrft.encoder2100.encoder import Source, select
from qrft.encoder2100.protocol import FINISH_ID, START_ID, data_frame, frame
from qrft.encoder2100.qr import image
from qrft.single_decoder import project as module
from qrft.single_decoder.folder import verify_folder
from qrft.single_decoder.project import Project, decode_project
from qrft.single_decoder.protocol import parse


def video(path, sequence):
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 1852 if any(isinstance(item, tuple) for item in sequence) else 926
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (width, 926))
    assert writer.isOpened()
    cache = {}
    try:
        for item in sequence:
            canvas = np.full((926, width, 3), 255, np.uint8)
            codes = item if isinstance(item, tuple) else (item,)
            for index, code in enumerate(codes):
                if code is not None:
                    if code not in cache:
                        cache[code] = np.asarray(image(code))[:, :, ::-1]
                    canvas[:925, index * 927 : index * 927 + 925] = cache[code]
            writer.write(canvas)
    finally:
        writer.release()
    return path


def encoded(path, data=b"\x00\xff" + bytes(range(256)) * 17):
    path.write_bytes(data)
    with Source(path) as source:
        return list(source.frames(select(source.metadata.packets)))


@contextmanager
def db(root):
    connection = sqlite3.connect(root / "state/project.db")
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@pytest.mark.parametrize(
    "name,payload",
    [
        ("空文件.bin", b""),
        ("中文, MiX.TXT", "任意字节".encode()),
        ("program.exe", bytes(range(256)) * 17),
        ("document.pdf", b"%PDF-\x00\xff"),
        ("archive.zip", b"PK\x03\x04\x00\x80not-a-zip"),
        ("random.bin", random.Random(23).randbytes(4201)),
    ],
)
def test_actual_single_mp4_roundtrip_and_repeat(tmp_path, name, payload):
    sequence = encoded(tmp_path / name, payload)
    root = tmp_path / "project"
    video(root / "videos/录像 arbitrary.MP4", [text for _, text in sequence])
    first = decode_project(root)
    assert first["status"] == "SUCCESS", first
    output = root / first["output_path"]
    assert output.read_bytes() == payload
    assert first["actual_md5"] == hashlib.md5(payload).hexdigest().upper()
    assert first["actual_size"] == len(payload)
    assert first["protocol"] == "QRFT2100" and first["missing_packets"] == 0
    before = output.stat().st_mtime_ns
    with db(root) as connection:
        count = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    second = decode_project(root)
    assert second["status"] == "SUCCESS" and second["videos_skipped"] == 1
    assert output.stat().st_mtime_ns == before
    with db(root) as connection:
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == count
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert "# Missing packets: 0" in (root / "reports/missing_packets.txt").read_text()


def test_multiple_out_of_order_missing_and_retransmission(tmp_path):
    sequence = dict(encoded(tmp_path / "original.bin"))
    root = tmp_path / "project"
    video(root / "videos/a-data-first.mp4", [sequence[0], sequence[FINISH_ID], sequence[0]])
    result = decode_project(root)
    assert result["status"] == "INCOMPLETE" and result["total_packets"] is None
    video(root / "videos/sub/z-start.mp4", [sequence[START_ID], sequence[2]])
    result = decode_project(root)
    assert result["status"] == "INCOMPLETE" and result["missing_packets"] == 1
    missing = root / "reports/missing_packets.txt"
    assert select(3, missing=missing) == [(1, 1)]
    video(root / "补传.mp4", [sequence[START_ID], sequence[1], sequence[FINISH_ID]])
    result = decode_project(root)
    assert result["status"] == "SUCCESS" and result["videos_skipped"] == 2
    assert (root / result["output_path"]).read_bytes() == (tmp_path / "original.bin").read_bytes()
    with db(root) as connection:
        assert connection.execute("SELECT COUNT(*) FROM packets").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 7


def test_duplicate_conflict_and_source_removal(tmp_path):
    sequence = dict(encoded(tmp_path / "original.bin"))
    root = tmp_path / "project"
    video(
        root / "videos/good.mp4",
        [sequence[START_ID], sequence[0], sequence[0], sequence[1], sequence[2]],
    )
    conflict = video(root / "videos/conflict.mp4", [data_frame(b"X" * 2100, 0)])
    result = decode_project(root)
    assert result["status"] == "FAILED" and result["packet_conflicts"] == 1
    assert not list((root / "output").iterdir())
    conflict.unlink()  # Test-owned input; removal invalidates its provenance.
    result = decode_project(root)
    assert result["status"] == "SUCCESS" and result["packet_conflicts"] == 0


def test_multiple_tasks_and_protocols_refused(tmp_path):
    first = encoded(tmp_path / "one.bin", b"same")
    second = encoded(tmp_path / "two.bin", b"different")
    root = tmp_path / "project"
    video(root / "videos/a.mp4", [text for _, text in first])
    video(root / "videos/b.mp4", [text for _, text in second])
    result = decode_project(root)
    assert result["status"] == "FAILED" and result["metadata_conflicts"] == 1
    assert not list((root / "output").iterdir())


def test_final_md5_mismatch_records_actual_and_never_publishes(tmp_path):
    sequence = dict(encoded(tmp_path / "original.bin", b"correct"))
    root = tmp_path / "project"
    video(
        root / "videos/bad-content.mp4",
        [sequence[START_ID], data_frame(b"wrong!!", 0), sequence[FINISH_ID]],
    )
    result = decode_project(root)
    assert result["status"] == "FAILED" and not result["md5_verified"]
    assert result["actual_md5"] == hashlib.md5(b"wrong!!").hexdigest().upper()
    assert not list((root / "output").iterdir())


def test_invalid_frames_blanks_multi_qr_and_corrupt_video_continue(tmp_path):
    sequence = dict(encoded(tmp_path / "original.bin", b"payload"))
    root = tmp_path / "project"
    corrupt = sequence[0][:-48] + "0" * 32 + sequence[0][-16:]
    video(
        root / "videos/good.mp4",
        [None, "AB", corrupt, (sequence[START_ID], sequence[0]), sequence[FINISH_ID]],
    )
    (root / "videos/broken.mp4").write_bytes(b"not a video")
    result = decode_project(root)
    assert result["status"] == "SUCCESS" and result["videos_failed"] == 1
    with db(root) as connection:
        assert (
            connection.execute(
                "SELECT invalid_frames FROM videos WHERE path='videos/good.mp4'"
            ).fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT status FROM videos WHERE path='videos/broken.mp4'"
            ).fetchone()[0]
            == "failed"
        )
    assert (root / result["output_path"]).read_bytes() == b"payload"


def test_changed_video_same_size_and_mtime_invalidates_old_packets(tmp_path):
    sequence = dict(encoded(tmp_path / "original.bin"))
    root = tmp_path / "project"
    path = video(root / "videos/a.mp4", [sequence[START_ID], sequence[0], sequence[1], sequence[2]])
    assert decode_project(root)["status"] == "SUCCESS"
    before = path.stat()
    replacement = video(tmp_path / "replacement.mp4", [None])
    raw = replacement.read_bytes()
    assert len(raw) < before.st_size
    path.write_bytes(raw + b"\x00" * (before.st_size - len(raw)))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    result = decode_project(root)
    assert result["status"] == "INCOMPLETE" and result["received_packets"] == 0
    assert not result["trusted_start"] and result["videos_skipped"] == 0


def test_interruption_checkpoints_resume_and_project_move(tmp_path):
    sequence = encoded(tmp_path / "original.bin")
    root = tmp_path / "project"
    video(root / "videos/a.mp4", [text for _, text in sequence] * 8)
    calls = [0]

    def cancel():
        calls[0] += 1
        return calls[0] == 28

    result = decode_project(root, cancelled=cancel)
    assert result["status"] == "INCOMPLETE" and result["interrupted"]
    with db(root) as connection:
        assert connection.execute("SELECT status,processed_frames FROM videos").fetchone()[:] == (
            "failed",
            25,
        )
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] > 0
    moved = tmp_path / "different parent/项目"
    moved.parent.mkdir()
    shutil.move(str(root), moved)
    assert decode_project(moved)["status"] == "SUCCESS"
    assert decode_project(moved)["videos_skipped"] == 1


def test_actual_process_crash_keeps_transaction_and_releases_lock(tmp_path):
    root = tmp_path / "project"
    sequence = encoded(tmp_path / "original.bin")
    video(root / "videos/a.mp4", [text for _, text in sequence] * 7)
    command = "import os,sys; from qrft.single_decoder.project import decode_project; decode_project(sys.argv[1],progress=lambda n,c,s,i,t: os._exit(77) if s=='processing' and i==25 else None)"
    result = subprocess.run(
        [sys.executable, "-c", command, str(root)], capture_output=True, timeout=90, check=False
    )
    assert result.returncode == 77
    with db(root) as connection:
        assert connection.execute("SELECT status,processed_frames FROM videos").fetchone()[:] == (
            "processing",
            25,
        )
    assert decode_project(root)["status"] == "SUCCESS"


def test_folder_zip_bytes_and_independent_content_fingerprint(tmp_path):
    folder = tmp_path / "源 Folder"
    (folder / "中文 Empty").mkdir(parents=True)
    (folder / ".hidden").write_bytes(b"\x00\xff")
    (folder / "Zero.bin").write_bytes(b"")
    (folder / "random.bin").write_bytes(random.Random(74).randbytes(4201))
    with Source(folder) as source:
        sequence = list(source.frames(select(source.metadata.packets)))
        details = source.describe()
        with source.open_stream() as stream:
            expected = stream.read()
    root = tmp_path / "project"
    video(root / "videos/folder.mp4", [text for _, text in sequence])
    result = decode_project(root)
    assert result["status"] == "SUCCESS", result
    assert result["folder"]["folder_content_md5"] == details["folder_content_md5"]
    assert result["folder"]["folder_content_sha256"] == details["folder_content_sha256"]
    assert result["actual_md5"] == details["archive_zip_md5"]
    restored = root / result["output_path"]
    assert restored.read_bytes() == expected and not result["folder"]["auto_extracted"]
    with zipfile.ZipFile(restored) as zipped:
        for name in zipped.namelist():
            original = folder / name
            assert (
                original.is_dir()
                if name.endswith("/")
                else zipped.read(name) == original.read_bytes()
            )
    with pytest.raises(ValueError, match="budget"):
        verify_folder(restored, max_bytes=1)


def test_wrong_folder_fingerprint_blocks_valid_zip_md5(tmp_path):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as zipped:
        zipped.writestr("some.bin", b"data")
        zipped.comment = json.dumps(
            {
                "format": "QRFT2100-FOLDER-1",
                "folder_content_md5": "0" * 32,
                "folder_content_sha256": "0" * 64,
            }
        ).encode()
    sequence = encoded(tmp_path / "folder.zip", raw.getvalue())
    root = tmp_path / "project"
    video(root / "videos/a.mp4", [text for _, text in sequence])
    result = decode_project(root)
    assert result["status"] == "FAILED" and result["md5_verified"]
    assert result["folder"]["status"] == "FAILED" and not list((root / "output").iterdir())


def test_output_protection_db_corruption_and_exclusive_project(tmp_path):
    sequence = encoded(tmp_path / "original.bin", b"content")
    root = tmp_path / "project"
    video(root / "videos/a.mp4", [text for _, text in sequence])
    (root / "output").mkdir()
    destination = root / "output/original.bin"
    destination.write_bytes(b"user file")
    assert decode_project(root)["status"] == "FAILED"
    assert destination.read_bytes() == b"user file"
    with Project(root), pytest.raises(OSError, match="another process"):
        Project(root)
    with db(root) as connection:
        connection.execute("UPDATE packets SET payload=? WHERE packet_id=0", (b"tampered",))
    result = decode_project(root)
    assert result["status"] == "FAILED" and "checksum" in result["error"]


@pytest.mark.parametrize(
    "name",
    ["../escape.bin", "C:\\escape.bin", "NUL.txt", "trailing.", "COM¹.txt", "CONIN$", "COM1 .bin"],
)
def test_unsafe_start_filename_rejected(name):
    with pytest.raises(ValueError, match="Unsafe"):
        parse(frame(f"{name},{'0' * 32},0,QRFT2100".encode(), START_ID))


def test_old_v2_real_encoder_avi_and_cli(tmp_path):
    from qrft.encoder_cli.video_export import export_video

    source = tmp_path / "old, V2.bin"
    source.write_bytes(bytes(range(256)) * 6)
    root = tmp_path / "project"
    (root / "videos").mkdir(parents=True)
    export_video(source, root / "videos/old.avi", protocol_version=2)
    result = decode_project(root)
    assert result["status"] == "SUCCESS" and result["protocol"] == "V2"
    assert (root / result["output_path"]).read_bytes() == source.read_bytes()
    cli = subprocess.run(
        [sys.executable, "-m", "qrft", "decode", str(root)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert cli.returncode == 0 and "Skipped: 1" in cli.stdout and "MD5: PASS" in cli.stdout


def test_video_changes_during_scan_invalidate_committed_provenance(tmp_path, monkeypatch):
    root = tmp_path / "project"
    sequence = encoded(tmp_path / "original.bin")
    path = video(root / "videos/a.mp4", [text for _, text in sequence] * 7)
    actual_frames = module.frames

    def modified_frames(path):
        for index, total, codes, error in actual_frames(path):
            yield index, total, codes, error
            if index == 26:
                current = path.stat()
                os.utime(path, ns=(current.st_atime_ns, current.st_mtime_ns + 10_000_000))

    monkeypatch.setattr(module, "frames", modified_frames)
    result = decode_project(root)
    assert result["videos_failed"] == 1 and result["received_packets"] == 0
    assert result["status"] == "INCOMPLETE" and not result["trusted_start"]
    monkeypatch.setattr(module, "frames", actual_frames)
    assert decode_project(root)["status"] == "SUCCESS"
    assert path.is_file()


def test_completed_rescan_and_modified_owned_output_protection(tmp_path):
    root = tmp_path / "project"
    sequence = encoded(tmp_path / "original.bin", b"source")
    video(root / "videos/a.mp4", [text for _, text in sequence])
    first = decode_project(root)
    assert first["status"] == "SUCCESS"
    repeated = decode_project(root, rescan=True)
    assert repeated["status"] == "SUCCESS" and repeated["videos_completed"] == 1
    with db(root) as connection:
        assert connection.execute("SELECT attempts FROM videos").fetchone()[0] == 2
    target = root / first["output_path"]
    target.write_bytes(b"user changes")
    failed = decode_project(root)
    assert failed["status"] == "FAILED" and target.read_bytes() == b"user changes"


def test_persisted_start_corruption_is_reported_not_trusted(tmp_path):
    root = tmp_path / "project"
    sequence = encoded(tmp_path / "original.bin", b"good")
    video(root / "videos/a.mp4", [text for _, text in sequence])
    assert decode_project(root)["status"] == "SUCCESS"
    with db(root) as connection:
        connection.execute(
            "UPDATE packets SET payload=? WHERE packet_id=?", (b"bad START", START_ID)
        )
    result = decode_project(root)
    assert result["status"] == "FAILED" and result["metadata_conflicts"] == 1
    assert (
        json.loads((root / "reports/decode_result.json").read_text(encoding="utf-8"))["status"]
        == "FAILED"
    )


def test_wrong_chunk_layout_is_not_accepted_even_with_matching_file_md5(tmp_path):
    payload = b"A" * 10 + b"B" * 10
    start = frame(
        f"original.bin,{hashlib.md5(payload).hexdigest().upper()},2,QRFT2100".encode(), START_ID
    )
    root = tmp_path / "project"
    video(root / "videos/a.mp4", [start, data_frame(payload[:10], 0), data_frame(payload[10:], 1)])
    result = decode_project(root)
    assert result["status"] == "FAILED" and not list((root / "output").iterdir())


def test_protocol_lock_does_not_mix_old_v2_and_qrft2100(tmp_path):
    from qrft.core.protocol_v2 import encode_start_v2

    payload = b"same"
    md5 = hashlib.md5(payload).hexdigest().upper()
    modern = encoded(tmp_path / "original.bin", payload)
    old = encode_start_v2({"filename": "original.bin", "md5": md5, "total_packets": 1})
    root = tmp_path / "project"
    video(root / "videos/a.mp4", [text for _, text in modern] + [old.decode("ascii")])
    result = decode_project(root)
    assert result["status"] == "FAILED" and result["metadata_conflicts"] == 1


def test_missing_report_full_ids_and_unrelated_project_protection(tmp_path):
    root = tmp_path / "project"
    (root / "reports").mkdir(parents=True)
    foreign = root / "reports/decode_result.json"
    foreign.write_text("user record")
    with pytest.raises(ValueError, match="unrelated"):
        Project(root)
    assert foreign.read_text() == "user record"
    separate = tmp_path / "other"
    with Project(separate) as project:
        meta = {
            "protocol": "QRFT2100",
            "filename": "big.bin",
            "expected_md5": "0" * 32,
            "total_packets": 1001,
            "chunk_size": 2100,
        }
        with project.db:
            project.db.execute("INSERT INTO task VALUES(1,?)", (json.dumps(meta),))
        result = project.run()
    missing = separate / "reports/missing_packets.txt"
    assert result["missing_packets"] == 1001
    assert select(1001, missing=missing) == [(0, 1000)]
    assert (
        len([line for line in missing.read_text().splitlines() if not line.startswith("#")]) == 1001
    )


def test_empty_folder_is_a_valid_zip_transfer(tmp_path):
    folder = tmp_path / "Empty Folder"
    folder.mkdir()
    with Source(folder) as source:
        sequence = list(source.frames(select(source.metadata.packets)))
        expected_md5 = source.metadata.md5
    root = tmp_path / "project"
    video(root / "videos/empty.mp4", [text for _, text in sequence])
    result = decode_project(root)
    assert result["status"] == "SUCCESS" and result["folder"]["entries"] == 0
    assert result["actual_md5"] == expected_md5 and result["total_packets"] > 0


@pytest.mark.parametrize("entry", ["../escape", "/absolute", "C:\\escape", "missing-parent/file"])
def test_folder_verifier_refuses_unsafe_archive_paths(tmp_path, entry):
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as zipped:
        zipped.writestr(entry, b"data")
        zipped.comment = json.dumps({"format": "QRFT2100-FOLDER-1"}).encode()
    with pytest.raises(ValueError):
        verify_folder(path, 1024)


def test_native_video_read_exception_does_not_abort_other_videos(tmp_path, monkeypatch):
    sequence = encoded(tmp_path / "original.bin", b"safe content")
    root = tmp_path / "project"
    codes = [text for _, text in sequence]
    video(root / "videos/a-failing.mp4", codes)
    video(root / "videos/z-good.mp4", codes)
    real_capture = cv2.VideoCapture

    class FailingCapture:
        def __init__(self, path):
            self.capture = real_capture(path)

        def __getattr__(self, name):
            return getattr(self.capture, name)

        def read(self):
            raise cv2.error("injected native read failure")

    monkeypatch.setattr(
        cv2,
        "VideoCapture",
        lambda path: FailingCapture(path) if path.endswith("a-failing.mp4") else real_capture(path),
    )
    result = decode_project(root)
    assert result["status"] == "SUCCESS" and result["videos_failed"] == 1
    assert result["videos_completed"] == 1 and result["md5_verified"]
