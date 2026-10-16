"""分布式 worker 时间片请求与原始包提交测试。"""

from __future__ import annotations

import io
import threading
import urllib.error
from pathlib import Path

import pytest

from qrft.core.protocol import Frame
from qrft.decoder import worker


def test_process_slice_uses_video_range_and_batches(monkeypatch) -> None:
    calls = []
    observed = []

    def fake_request(base_url, token, route, payload):
        calls.append((route, payload))
        return {"status": "ok"}

    def fake_frames(path, *, sample_fps, start_seconds, end_seconds):
        observed.append((str(path), start_seconds, end_seconds))
        yield Frame(
            "start",
            88888888,
            b"",
            {
                "version": 2,
                "filename": "file.bin",
                "md5": "0" * 32,
                "total_packets": 2,
                "chunk_size": 2100,
            },
        )
        yield Frame("data", 0, b"\x00\xff")
        yield Frame("data", 1, b"binary")

    monkeypatch.setattr(worker, "request_json", fake_request)
    monkeypatch.setattr(worker, "iter_video_frames", fake_frames)
    lease = {
        "id": 7,
        "task_id": 3,
        "path": "share/video.avi",
        "start_ms": 1000,
        "end_ms": 3000,
    }
    assert worker.process_slice("http://localhost", "token", "node-a", lease, batch_size=1) == 2
    assert observed == [(str(Path("share/video.avi")), 1.0, 3.0)]
    assert [route for route, _ in calls] == [
        "/tasks/manifest",
        "/packets/batch",
        "/packets/batch",
        "/slices/7/complete",
    ]


def test_worker_heartbeat_and_claim(monkeypatch) -> None:
    calls = []

    def fake_request(base_url, token, route, payload):
        calls.append(route)

    monkeypatch.setattr(worker, "request_json", fake_request)
    worker.run_worker("http://localhost", "token", "node-a", once=True)
    assert calls == ["/nodes/heartbeat", "/slices/claim"]


def test_retry_network_and_no_retry_auth_or_claim(monkeypatch):
    calls = []
    sleeps = []

    def open_request(request, timeout):
        calls.append(request)
        if len(calls) < 3:
            raise urllib.error.URLError("offline")
        return io.BytesIO(b'{"status":"ok"}')

    monkeypatch.setattr(worker.urllib.request, "urlopen", open_request)
    monkeypatch.setattr(worker.time, "sleep", sleeps.append)
    assert worker.request_json("http://localhost", "token", "/packets/batch", {}) == {
        "status": "ok"
    }
    assert sleeps == [1, 2]
    calls.clear()
    with pytest.raises(urllib.error.URLError):
        worker.request_json("http://localhost", "token", "/slices/claim", {})
    assert len(calls) == 1

    def unauthorized(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(worker.urllib.request, "urlopen", unauthorized)
    with pytest.raises(urllib.error.HTTPError):
        worker.request_json("http://localhost", "token", "/packets/batch", {})


def test_renew_without_recognized_frames_and_finish(monkeypatch):
    renewed = threading.Event()
    calls = []

    def request(base_url, token, route, payload):
        calls.append(route)
        if route.endswith("/renew"):
            renewed.set()
        return {"status": "ok"}

    def frames(*args, **kwargs):
        assert renewed.wait(2)
        yield Frame("finish", 99999999, b"")

    monkeypatch.setattr(worker, "request_json", request)
    monkeypatch.setattr(worker, "iter_video_frames", frames)
    lease = {
        "id": 1,
        "task_id": 1,
        "path": r"\\server\share\recording.avi",
        "start_ms": 0,
        "end_ms": 1000,
    }
    worker.process_slice("http://localhost", "token", "node", lease, maintenance_seconds=0.01)
    assert "/nodes/heartbeat" in calls
    assert "/packets/batch" in calls
    assert calls[-1] == "/slices/1/complete"


def test_interrupted_scan_never_completes(monkeypatch):
    calls = []

    def frames(*args, **kwargs):
        yield Frame("data", 0, b"abc")
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "request_json", lambda *args: calls.append(args[2]))
    monkeypatch.setattr(worker, "iter_video_frames", frames)
    lease = {"id": 1, "task_id": 1, "path": "video.avi", "start_ms": 0, "end_ms": 1000}
    with pytest.raises(KeyboardInterrupt):
        worker.process_slice("http://localhost", "token", "node", lease, batch_size=1)
    assert calls == ["/packets/batch"]


def test_renew_failure_never_completes(monkeypatch):
    failed = threading.Event()
    calls = []

    def request(base_url, token, route, payload):
        calls.append(route)
        if route.endswith("/renew"):
            failed.set()
            raise OSError("lease lost")
        return {"status": "ok"}

    def frames(*args, **kwargs):
        assert failed.wait(2)
        yield Frame("data", 0, b"abc")

    monkeypatch.setattr(worker, "request_json", request)
    monkeypatch.setattr(worker, "iter_video_frames", frames)
    lease = {"id": 1, "task_id": 1, "path": "video.avi", "start_ms": 0, "end_ms": 1000}
    with pytest.raises(OSError, match="lease lost"):
        worker.process_slice("http://localhost", "token", "node", lease, maintenance_seconds=0.01)
    assert "/slices/1/complete" not in calls
