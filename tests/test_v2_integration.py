"""Actual QR/AVI/MD5, durable retransmission and networked distributed workers."""

import base64
import hashlib
import json
import random
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qrft.control.app import app, connection
from qrft.core.manifest import inspect_file
from qrft.core.protocol import ProtocolError, encode_data
from qrft.core.protocol_v2 import encode_data_v2, encode_finish_v2, encode_start_v2
from qrft.decoder.main import restore_video
from qrft.decoder.video import iter_video_frames
from qrft.decoder.worker import process_slice
from qrft.encoder_cli.playback import iter_encoded_frames
from qrft.encoder_cli.video_export import export_video, write_v2_video


@pytest.fixture
def control(tmp_path, monkeypatch):
    monkeypatch.setenv("QRFT_API_TOKEN", "v2-test-only")
    monkeypatch.setenv("QRFT_DB_PATH", str(tmp_path / "control.db"))
    monkeypatch.setenv("QRFT_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.delenv("QRFT_ACCEPTANCE_ID", raising=False)
    return TestClient(app, headers={"Authorization": "Bearer v2-test-only"})


def create(control):
    return control.post("/tasks", json={"name": "v2 explicit task", "protocol_version": 2}).json()[
        "id"
    ]


def batch(control, task, raws):
    return control.post(
        "/packets/batch",
        json={"task_id": task, "frames_base64": [base64.b64encode(raw).decode() for raw in raws]},
    )


def bind(control, task, raw):
    return control.post(
        "/tasks/manifest", json={"task_id": task, "start_base64": base64.b64encode(raw).decode()}
    )


@pytest.mark.parametrize(
    "payload",
    [b"", b"\x00\xff\x80", random.Random(5).randbytes(1400), bytes(range(256)) * 11 + b"end"],
    ids=["empty", "binary-tail", "random-1400", "all-byte-values"],
)
def test_real_video_sequence_and_restore(tmp_path, payload):
    import cv2

    source = tmp_path / "中文,文档.exe"
    source.write_bytes(payload)
    video = export_video(source, tmp_path / "synthetic.avi", protocol_version=2)
    capture = cv2.VideoCapture(str(video))
    total = (len(payload) + 1399) // 1400
    assert capture.get(cv2.CAP_PROP_FPS) == 20
    assert capture.get(cv2.CAP_PROP_FRAME_COUNT) == 40 + total
    capture.release()
    frames = list(iter_video_frames(video))
    assert [f.kind for f in frames] == ["start"] * 20 + ["data"] * total + ["finish"] * 20
    restored = restore_video(video, tmp_path / "task", protocol_version=2)
    assert restored.read_bytes() == payload
    result = json.loads((tmp_path / "task" / "verification.json").read_text(encoding="utf-8"))
    assert result["md5"] == hashlib.md5(payload).hexdigest().upper()


def test_lost_frame_and_persistent_retransmission(tmp_path):
    import cv2
    import numpy as np

    source = tmp_path / "whole.zip"
    payload = random.Random(4).randbytes(2805)
    source.write_bytes(payload)
    video = export_video(source, tmp_path / "original.avi", protocol_version=2)
    damaged = tmp_path / "lost.avi"
    reader = cv2.VideoCapture(str(video))
    writer = cv2.VideoWriter(str(damaged), cv2.VideoWriter_fourcc(*"MJPG"), 20, (926, 926))
    assert writer.isOpened()
    index = 0
    try:
        while True:
            ok, image = reader.read()
            if not ok:
                break
            writer.write(np.full_like(image, 255) if index == 21 else image)
            index += 1
    finally:
        reader.release()
        writer.release()
    directory = tmp_path / "durable-task"
    assert restore_video(damaged, directory, protocol_version=2) is None
    missing = directory / "missing.txt"
    assert missing.read_text(encoding="utf-8").strip() == "00000001"
    retransmit = write_v2_video(
        iter_encoded_frames(source, protocol_version=2, retransmit=missing),
        tmp_path / "retransmit.avi",
    )
    assert restore_video(retransmit, directory, protocol_version=2).read_bytes() == payload
    assert missing.read_text(encoding="utf-8") == ""


def test_start_missing_then_start_only_and_finish_missing(tmp_path):
    source = tmp_path / "document.pdf"
    source.write_bytes(b"%PDF\x00\xff")
    frames = list(iter_encoded_frames(source, protocol_version=2))
    video = write_v2_video((f for f in frames if f[0] != "START"), tmp_path / "no-start.avi")
    directory = tmp_path / "task"
    assert restore_video(video, directory, protocol_version=2) is None
    assert (
        json.loads((directory / ".qrft-session/status.json").read_text(encoding="utf-8"))["status"]
        == "awaiting_start"
    )
    start = write_v2_video(frames[:20], tmp_path / "start-only.avi")
    assert restore_video(start, directory, protocol_version=2).read_bytes() == source.read_bytes()
    nofinish = write_v2_video((f for f in frames if f[0] != "FINISH"), tmp_path / "no-finish.avi")
    assert (
        restore_video(nofinish, tmp_path / "other", protocol_version=2).read_bytes()
        == source.read_bytes()
    )


def test_control_unordered_lock_dedup_conflict_and_md5(control, tmp_path):
    source = tmp_path / "commas,中文.bin"
    payload = random.Random(11).randbytes(1405)
    source.write_bytes(payload)
    meta = inspect_file(source, 1400)
    task = create(control)
    raw0, raw1 = encode_data_v2(0, payload[:1400]), encode_data_v2(1, payload[1400:])
    assert batch(control, task, [raw1, encode_finish_v2(), encode_finish_v2()]).json() == {
        "inserted": 2,
        "duplicate": 1,
        "conflict": 0,
    }
    assert bind(control, task, encode_start_v2(meta)).status_code == 200
    assert bind(control, task, encode_start_v2(meta)).json()["status"] == "already_bound"
    assert control.get(f"/tasks/{task}/missing").json()["missing_ids"] == [0]
    assert batch(control, task, [raw0, raw0]).json()["duplicate"] == 1
    assert batch(control, task, [encode_data(0, b"v1")]).status_code == 422
    result = control.post(f"/tasks/{task}/recover").json()
    assert result["status"] == "verified" and result["md5"] == meta["md5"].upper()
    assert Path(result["path"]).read_bytes() == payload
    assert (
        bind(control, task, encode_start_v2({**meta, "filename": "different.bin"})).status_code
        == 409
    )
    conflict = create(control)
    assert bind(control, conflict, encode_start_v2(meta)).status_code == 200
    assert (
        batch(control, conflict, [raw0, raw1, encode_data_v2(0, b"z" * 1400)]).json()["conflict"]
        == 1
    )
    assert control.post(f"/tasks/{conflict}/recover").status_code == 409
    with connection() as db:
        assert (
            bytes(
                db.execute(
                    "SELECT frame FROM packets WHERE task_id=? AND packet_id=0", (conflict,)
                ).fetchone()[0]
            )
            == raw0
        )
    wrong = create(control)
    bind(control, wrong, encode_start_v2(meta))
    assert batch(control, wrong, [encode_data_v2(0, b"a" * 1400), raw1]).status_code == 200
    assert control.post(f"/tasks/{wrong}/recover").status_code == 409


def test_v1_default_and_wrong_size_reject_v2(control, tmp_path):
    task = control.post("/tasks", json={"name": "legacy"}).json()["id"]
    assert batch(control, task, [encode_data_v2(0, b"x")]).status_code == 422
    source = tmp_path / "large.bin"
    source.write_bytes(b"x" * 1401)
    task = create(control)
    bind(control, task, encode_start_v2(inspect_file(source, 1400)))
    assert batch(control, task, [encode_data_v2(0, b"short")]).status_code == 422
    assert control.get(f"/tasks/{task}/progress").json()["stored"] == 0


def split(control, task, video):
    vid = control.post(
        "/videos", json={"task_id": task, "path": str(video), "duration_seconds": 2.15}
    ).json()["id"]
    with connection() as db:
        db.execute("DELETE FROM slices WHERE video_id=?", (vid,))
        db.executemany(
            "INSERT INTO slices(video_id,start_ms,end_ms) VALUES (?,?,?)",
            [(vid, 0, 1050), (vid, 1050, 2150)],
        )
    return vid


def test_real_http_workers_and_independent_processes(control, tmp_path):
    import uvicorn

    source = tmp_path / "distributed.bin"
    payload = random.Random(12).randbytes(2805)
    source.write_bytes(payload)
    video = export_video(source, tmp_path / "worker.avi", protocol_version=2)
    task = create(control)
    split(control, task, video)
    first = control.post("/slices/claim", json={"node_id": "first"}).json()
    second = control.post("/slices/claim", json={"node_id": "second"}).json()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        url = f"http://127.0.0.1:{port}"
        assert process_slice(url, "v2-test-only", "second", second) > 0
        assert control.get(f"/tasks/{task}/progress").json()["total_packets"] is None
        assert process_slice(url, "v2-test-only", "first", first) > 0
        result = control.post(f"/tasks/{task}/recover").json()
        assert result["status"] == "verified" and Path(result["path"]).read_bytes() == payload
        task2 = create(control)
        vid = split(control, task2, video)
        children = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "qrft.decoder.entrypoint",
                    "worker",
                    "--server",
                    url,
                    "--node-id",
                    name,
                    "--once",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            for name in ("node-a", "node-b")
        ]
        try:
            for child in children:
                stdout, _ = child.communicate(timeout=30)
                assert child.returncode == 0, stdout.decode(errors="replace")
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait()
        assert {r["owner"] for r in control.get(f"/slices?video_id={vid}").json()} == {
            "node-a",
            "node-b",
        }
        result = control.post(f"/tasks/{task2}/recover").json()
        assert result["status"] == "verified" and Path(result["path"]).read_bytes() == payload
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_mixed_local_task_rejected(tmp_path):
    source = tmp_path / "same.bin"
    source.write_bytes(b"x")
    v1 = export_video(source, tmp_path / "v1.avi")
    v2 = export_video(source, tmp_path / "v2.avi", protocol_version=2)
    with pytest.raises(ProtocolError, match="version mismatch"):
        restore_video([v2, v1], tmp_path / "mixed", protocol_version=2)


def test_gui_fixed_v2_and_real_png(tmp_path):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from qrft.core.qr_decode import decode_qr_png
    from qrft.encoder_gui.main import EncoderWindow

    qt = QApplication.instance() or QApplication([])
    source = tmp_path / "qt.bin"
    source.write_bytes(random.Random(20).randbytes(1400))
    window = EncoderWindow()
    try:
        window.protocol.setCurrentIndex(1)
        assert window.chunk_size.value() == 1400 and not window.chunk_size.isEnabled()
        assert window.interval_ms.value() == 50 and window.correction.currentText() == "L"
        window.source.setText(str(source))
        window.output.setText(str(tmp_path / "png"))
        window.export_png()
        deadline = time.monotonic() + 10
        while window.jobs and time.monotonic() < deadline:
            qt.processEvents()
            QTest.qWait(10)
        assert not window.jobs
        assert (
            decode_qr_png((tmp_path / "png/00000000-data.png").read_bytes()).payload
            == source.read_bytes()
        )
    finally:
        window.close()


def test_qt_player_v2_repeats_and_lifecycle(tmp_path):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from qrft.encoder_gui.player import PlayerWindow

    qt = QApplication.instance() or QApplication([])
    source = tmp_path / "player.bin"
    source.write_bytes(b"\x00\xff")
    window = PlayerWindow(
        source, protocol_version=2, interval_ms=50, initial_delay_ms=0, fullscreen=False
    )
    seen = []
    maxima = []
    window.progress.connect(
        lambda packet, _: (seen.append(packet), maxima.append(window.bar.maximum()))
    )
    try:
        window.show()
        ready_deadline = time.monotonic() + 10
        while not window.ready and time.monotonic() < ready_deadline:
            qt.processEvents()
            QTest.qWait(5)
        assert window.ready
        window.toggle_pause()
        deadline = time.monotonic() + 10
        while not window.finished and time.monotonic() < deadline:
            qt.processEvents()
            QTest.qWait(5)
        assert window.finished and window.error is None
        assert seen == ["START"] * 20 + ["00000000"] + ["FINISH"] * 20
        assert set(maxima) == {41}
        assert window.bar.value() == 100
    finally:
        window.close()
    assert not window.thread.is_alive()


def test_invalid_md5_in_real_video_is_logged_and_dropped(tmp_path, caplog):
    import cv2
    import numpy as np
    import qrcode

    raw = encode_data_v2(0, b"abc")
    damaged = raw[:-48] + b"0" * 32 + raw[-16:]
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(damaged.decode())
    qr.make(fit=True)
    image = cv2.cvtColor(np.asarray(qr.make_image().convert("RGB")), cv2.COLOR_RGB2BGR)
    image = cv2.resize(image, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_NEAREST)
    canvas = np.full((926, 926, 3), 255, dtype=np.uint8)
    h, w = image.shape[:2]
    canvas[20 : 20 + h, 20 : 20 + w] = image
    video = tmp_path / "invalid.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 20, (926, 926))
    assert writer.isOpened()
    writer.write(canvas)
    writer.release()
    assert list(iter_video_frames(video)) == []
    assert "MD5 mismatch" in caplog.text


def test_truncated_video_does_not_publish(tmp_path):
    source = tmp_path / "truncated.bin"
    source.write_bytes(b"x" * 2801)
    frames = list(iter_encoded_frames(source, protocol_version=2))
    video = write_v2_video(frames[:21], tmp_path / "short.avi")
    directory = tmp_path / "task"
    assert restore_video(video, directory, protocol_version=2) is None
    assert (directory / "missing.txt").read_text().splitlines() == ["00000001", "00000002"]
    assert not (directory / "files/truncated.bin").exists()


def test_pre_v2_database_migration_is_v1(tmp_path, monkeypatch):
    import sqlite3

    database = tmp_path / "old.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,name TEXT,created_at REAL)")
        db.execute("INSERT INTO tasks VALUES (1,'legacy',0)")
    monkeypatch.setenv("QRFT_DB_PATH", str(database))
    with connection() as db:
        assert db.execute("SELECT version FROM task_protocols WHERE task_id=1").fetchone()[0] == 1
    with connection() as db:
        assert db.execute("SELECT COUNT(*) FROM task_protocols").fetchone()[0] == 1


def test_local_reports_do_not_overwrite_user_files(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    report = output / "missing.txt"
    report.write_text("user data")
    with pytest.raises(FileExistsError, match="已有文件"):
        restore_video(tmp_path / "unused.avi", output, protocol_version=2)
    assert report.read_text() == "user data"


@pytest.mark.parametrize("filename", ["missing.txt", "verification.json", "legacy.bin"])
def test_v1_output_location_and_report_filenames_preserved(tmp_path, filename):
    source = tmp_path / filename
    source.write_bytes(b"\x00\xff binary")
    video = export_video(source, tmp_path / "legacy.avi")
    directory = tmp_path / "output"
    restored = restore_video(video, directory)
    assert restored == directory / filename
    assert restored.read_bytes() == source.read_bytes()


@pytest.mark.parametrize("sample_fps", [20, 60])
def test_30fps_capture_phase_does_not_undersample_requested_rate(tmp_path, sample_fps):
    import cv2
    import numpy as np

    source = tmp_path / "phase.bin"
    source.write_bytes(b"z" * 1401)
    original = export_video(source, tmp_path / "20fps.avi", protocol_version=2)
    reader = cv2.VideoCapture(str(original))
    frames = []
    try:
        while True:
            ok, image = reader.read()
            if not ok:
                break
            frames.append(image)
    finally:
        reader.release()
    video = tmp_path / "30fps.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30, (926, 926))
    assert writer.isOpened()
    try:
        writer.write(np.full_like(frames[0], 255))  # Capture begins one frame before START.
        for index in range(len(frames) * 3 // 2):
            writer.write(frames[index * 2 // 3])
    finally:
        writer.release()
    ids = {f.packet_id for f in iter_video_frames(video, sample_fps=sample_fps) if f.kind == "data"}
    assert ids == {0, 1}
