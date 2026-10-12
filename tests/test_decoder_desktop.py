"""Real MP4 -> HTTP -> independent Worker -> existing SQLite/hash recovery."""

import hashlib
import json
import random
import time
from pathlib import Path

import pytest

from qrft.core.qr_image import v2_image
from qrft.decoder_gui.service import ControlClient, ManagedSession, inspect_video
from qrft.encoder_cli.playback import iter_encoded_frames


def mp4(frames, path):
    import cv2
    import numpy as np

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (926, 926))
    assert writer.isOpened()
    last, canvas = None, None
    try:
        for _, raw in frames:
            if raw != last:
                image = v2_image(raw)
                canvas = np.full((926, 926, 3), 255, dtype=np.uint8)
                h, w = image.shape[:2]
                y, x = (926 - h) // 2, (926 - w) // 2
                canvas[y : y + h, x : x + w] = image
                last = raw
            writer.write(canvas)
    finally:
        writer.release()
    return path


def wait_for(operation, condition, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = operation()
        if condition(value):
            return value
        time.sleep(0.1)
    raise AssertionError(f"timeout, last value: {value}")


def register(session, task, video):
    info = inspect_video(video)
    return session.client.request(
        "/videos",
        {
            "task_id": task,
            "path": info["path"],
            "duration_seconds": info["duration_seconds"],
            "slice_seconds": 1,
        },
    )["id"]


def completed(session, task):
    return wait_for(
        lambda: session.client.request(f"/tasks/{task}/progress"),
        lambda progress: (
            progress["slices"] and all(s["state"] == "done" for s in progress["slices"])
        ),
    )


@pytest.mark.parametrize(
    "payload", [b"", b"small text", bytes(range(256)) * 6, random.Random(19).randbytes(2805)]
)
def test_managed_mp4_binary_md5_and_reopen(tmp_path, payload):
    source = tmp_path / "中文,原始.exe"
    source.write_bytes(payload)
    video = mp4(iter_encoded_frames(source, protocol_version=2), tmp_path / "真实编码.mp4")
    workspace = tmp_path / "tasks"
    session = ManagedSession(workspace)
    try:
        task = session.client.request("/tasks", {"name": "single MP4", "protocol_version": 2})["id"]
        register(session, task, video)
        session.start(task)
        progress = completed(session, task)
        assert progress["missing_count"] == 0
        result = session.client.request(f"/tasks/{task}/recover", {})
        assert result["status"] == "verified"
        assert result["md5"] == hashlib.md5(payload).hexdigest().upper()
        assert Path(result["path"]).read_bytes() == payload
        with pytest.raises(RuntimeError, match="409"):
            session.client.request(f"/tasks/{task}/recover", {})
        assert Path(result["path"]).read_bytes() == payload
    finally:
        session.close()
    reopened = ManagedSession(workspace)
    try:
        assert (
            reopened.client.request(f"/tasks/{task}/progress")["recovery"]["status"] == "verified"
        )
        assert Path(result["path"]).read_bytes() == payload
    finally:
        reopened.close()


def test_real_two_processes_mp4_missing_repair_and_fenced_pause(tmp_path):
    payload = random.Random(29).randbytes(2805)
    source = tmp_path / "repair.zip"
    source.write_bytes(payload)
    frames = list(iter_encoded_frames(source, protocol_version=2))
    partial = mp4((frame for frame in frames if frame[0] != "00000001"), tmp_path / "partial.mp4")
    repair = mp4(
        (frame for frame in frames if frame[0] != "00000000" and frame[0] != "00000002"),
        tmp_path / "repair.mp4",
    )
    session = ManagedSession(tmp_path / "workspace")
    try:
        client = session.client
        task = client.request("/tasks", {"name": "repair", "protocol_version": 2})["id"]
        video = register(session, task, partial)
        session.start(task, 2)
        assert len({p.pid for p in session.workers}) == 2
        completed(session, task)
        assert client.request(f"/tasks/{task}/missing")["missing_ids"] == [1]
        assert client.request(f"/tasks/{task}/recover", {})["status"] == "incomplete"
        missing = tmp_path / "missing.txt"
        client.request(f"/tasks/{task}/missing/download?format=txt", download=missing)
        assert missing.read_text().strip() == "00000001"
        receipts = client.request(f"/acceptance/slices?video_id={video}")
        assert len({row["node_id"] for row in receipts if row["completed_at"]}) == 2
        session.pause(task)
        assert client.request(f"/tasks/{task}/progress")["paused"]
        register(session, task, repair)
        session.start(task, 2)
        completed(session, task)
        result = client.request(f"/tasks/{task}/recover", {})
        assert result["md5"] == hashlib.md5(payload).hexdigest().upper()
        assert Path(result["path"]).read_bytes() == payload
        assert client.request(f"/tasks/{task}/progress")["duplicates"] > 0
    finally:
        session.close()


def test_pause_cancel_resume_task_scope_and_lease_fencing(tmp_path):
    session = ManagedSession(tmp_path / "workspace")
    try:
        client = session.client
        a, b = [
            client.request("/tasks", {"name": name, "protocol_version": 2})["id"]
            for name in ("a", "b")
        ]
        for task in (a, b):
            client.request(
                "/videos", {"task_id": task, "path": "unavailable-SMB.mp4", "duration_seconds": 3}
            )
        lease = client.request("/slices/claim", {"node_id": "old", "task_id": b})
        assert lease["task_id"] == b
        client.request(f"/tasks/{b}/pause", {})
        assert client.request("/slices/claim", {"node_id": "new", "task_id": b}) is None
        with pytest.raises(RuntimeError, match="409"):
            client.request(
                f"/slices/{lease['id']}/complete",
                {"node_id": "old", "lease_token": lease["lease_token"]},
            )
        client.request(f"/tasks/{b}/resume", {})
        reassigned = client.request("/slices/claim", {"node_id": "new", "task_id": b})
        assert reassigned["id"] == lease["id"] and reassigned["lease_token"] != lease["lease_token"]
        client.request(f"/tasks/{b}/cancel", {})
        assert client.request(f"/tasks/{b}/progress")["cancelled"]
        client.request(f"/tasks/{b}/resume", {})
        assert not client.request(f"/tasks/{b}/progress")["cancelled"]
        assert client.request(f"/tasks/{b}/progress")["total_packets"] is None
    finally:
        session.close()


def test_worker_crash_expiry_reassign_real_mp4(tmp_path):
    source = tmp_path / "crash.bin"
    source.write_bytes(b"crash\x00\xff")
    video = mp4(iter_encoded_frames(source, protocol_version=2), tmp_path / "crash.mp4")
    session = ManagedSession(tmp_path / "workspace")
    try:
        client = session.client
        task = client.request("/tasks", {"name": "crash", "protocol_version": 2})["id"]
        register(session, task, video)
        dead = client.request(
            "/slices/claim", {"node_id": "crashed-node", "lease_seconds": 1, "task_id": task}
        )
        time.sleep(1.1)
        session.start(task)
        completed(session, task)
        slices = client.request(f"/slices?video_id={dead['video_id']}")
        assert slices[0]["attempts"] == 2 and slices[0]["owner"] != "crashed-node"
        result = client.request(f"/tasks/{task}/recover", {})
        assert Path(result["path"]).read_bytes() == source.read_bytes()
    finally:
        session.close()


def test_worker_unreadable_video_never_done_and_error_visible(tmp_path):
    session = ManagedSession(tmp_path / "workspace")
    try:
        client = session.client
        task = client.request("/tasks", {"name": "SMB simulation", "protocol_version": 2})["id"]
        vid = client.request(
            "/videos",
            {"task_id": task, "path": str(tmp_path / "not-found.mp4"), "duration_seconds": 3},
        )["id"]
        session.start(task)
        slices = wait_for(
            lambda: client.request(f"/slices?video_id={vid}"), lambda rows: rows[0].get("error")
        )
        assert slices[0]["state"] != "done"
        assert session.token not in json.dumps(slices)
        assert client.request(f"/tasks/{task}/progress")["stored"] == 0
    finally:
        session.close()


def test_no_token_url_and_user_workspace_protection(tmp_path):
    with pytest.raises(ValueError):
        ControlClient("http://token@localhost:8787", "secret")
    state = tmp_path / ".qrft-decoder"
    state.mkdir()
    user_file = state / "control.sqlite3"
    user_file.write_bytes(b"user database")
    with pytest.raises(ValueError, match="所有权"):
        ManagedSession(tmp_path)
    assert user_file.read_bytes() == b"user database"


def test_actual_http_transient_failure_retries_without_token_logging():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from qrft.decoder.worker import request_json

    attempts = []

    class FaultServer(BaseHTTPRequestHandler):
        def do_POST(self):
            attempts.append(self.headers.get("Authorization"))
            self.rfile.read(int(self.headers["Content-Length"]))
            if len(attempts) == 1:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"temporary offline")
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), FaultServer)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        assert request_json(
            f"http://127.0.0.1:{server.server_port}", "test-only-token", "/packets/batch", {}
        ) == {"status": "ok"}
        assert len(attempts) == 2 and set(attempts) == {"Bearer test-only-token"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_failed_md5_persists_failure_over_previous_incomplete_evidence(tmp_path):
    import base64

    from qrft.core.manifest import inspect_file
    from qrft.core.protocol_v2 import encode_data_v2, encode_start_v2

    source = tmp_path / "hash.bin"
    source.write_bytes(b"a" * 1401)
    session = ManagedSession(tmp_path / "workspace")
    try:
        client = session.client
        task = client.request("/tasks", {"name": "wrong final hash", "protocol_version": 2})["id"]
        client.request(
            "/tasks/manifest",
            {
                "task_id": task,
                "start_base64": base64.b64encode(
                    encode_start_v2(inspect_file(source, 1400))
                ).decode(),
            },
        )
        for packet, payload in [(0, b"b" * 1400), (1, b"a")]:
            client.request(
                "/packets/batch",
                {
                    "task_id": task,
                    "frames_base64": [base64.b64encode(encode_data_v2(packet, payload)).decode()],
                },
            )
            if packet == 0:
                assert client.request(f"/tasks/{task}/recover", {})["status"] == "incomplete"
        with pytest.raises(RuntimeError, match="hash mismatch"):
            client.request(f"/tasks/{task}/recover", {})
        recovery = client.request(f"/tasks/{task}/progress")["recovery"]
        assert recovery["status"] == "failed" and "hash mismatch" in recovery["reason"]
        assert not (session.state / "outputs" / str(task) / "files" / source.name).exists()
    finally:
        session.close()


def test_actual_worker_process_exit_and_replacement_scans_mp4(tmp_path):
    from itertools import chain

    source = tmp_path / "node-exit.bin"
    source.write_bytes(b"actual process exit\x00\xff")
    frames = list(iter_encoded_frames(source, protocol_version=2))
    video = mp4(
        chain.from_iterable([frames[:20]] * 50 + [frames[20:]]), tmp_path / "long-start.mp4"
    )
    session = ManagedSession(tmp_path / "workspace")
    try:
        client = session.client
        task = client.request("/tasks", {"name": "actual exit", "protocol_version": 2})["id"]
        info = inspect_video(video)
        vid = client.request(
            "/videos",
            {"task_id": task, "path": info["path"], "duration_seconds": info["duration_seconds"]},
        )["id"]

        def spawn(node):
            process = session.spawn(
                node,
                "qrft.decoder.worker",
                "--server",
                client.server,
                "--node-id",
                node,
                "--task-id",
                str(task),
                "--poll-seconds",
                "0.1",
                "--lease-seconds",
                "2",
                "--maintenance-seconds",
                "0.5",
            )
            session.workers.append(process)
            return process

        dead = spawn("actual-crashed-worker")
        wait_for(
            lambda: client.request(f"/tasks/{task}/progress"),
            lambda p: p["total_packets"] is not None,
        )
        before = client.request(f"/slices?video_id={vid}")
        assert before[0]["state"] == "leased"
        dead.kill()
        dead.wait(timeout=5)
        successor = spawn("actual-replacement-worker")
        completed(session, task)
        after = client.request(f"/slices?video_id={vid}")
        assert after[0]["attempts"] >= 2 and after[0]["owner"] == "actual-replacement-worker"
        assert successor.poll() is None
        result = client.request(f"/tasks/{task}/recover", {})
        assert Path(result["path"]).read_bytes() == source.read_bytes()
    finally:
        session.close()


def test_gui_background_real_mp4_recovery_lifecycle(tmp_path):
    import os
    import subprocess
    import sys

    # Qt is a process-wide singleton. Keep this full lifecycle independent of
    # other acceptance/encoder windows; native source smoke is a separate CI step.
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("decoder_gui_driver.py")), str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
