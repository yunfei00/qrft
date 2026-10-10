"""分布式 worker 时间片请求与原始包提交测试。"""

from __future__ import annotations

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
        yield Frame("start", 88888888, b"", {"version": 1})
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
    assert observed == [("share/video.avi", 1.0, 3.0)]
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
